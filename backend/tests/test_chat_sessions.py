# =============================================================================
# File: test_chat_sessions.py
# Module/Service: Chat Service — Conversation Memory (Phase 2.4 Part 1)
# Layer: Service / Presentation
# Purpose: Unit + HTTP tests for session CRUD, soft-delete, message history, RBAC.
# Responsibilities:
#   - Service: create/list/pagination/sort/detail/delete/messages nesting
#   - API: viewer/editor/admin read; owner/admin delete; editor/viewer deny others
# Dependencies:
#   - pytest, httpx, app.main, ChatSessionService fakes
# Public Exports:
#   - N/A
# Database/Table: N/A (in-memory fakes; no Postgres)
# Related Modules: app.api.chat, app.services.chat.session_service
# Important Notes: Does not cover POST .../messages (Part 2).
# =============================================================================

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.chat import get_chat_session_service
from app.core.rate_limit import InMemoryWorkspaceRateLimiter, get_workspace_rate_limiter
from app.db.session import get_db_session
from app.dependencies.auth import CurrentUser, get_current_user
from app.main import app
from app.models.chat import ChatMessage, ChatSession, MessageGeneration
from app.models.enums import (
    ConfidenceLevel,
    FinishReason,
    MessageRole,
    RoleName,
    RouteType,
)
from app.models.retrieval import Citation
from app.repositories.chat_messages import CitationWithDocument, MessageWithRelations
from app.repositories.workspace_members import WorkspaceMemberRepository
from app.schemas.chat import ChatMessageResponse, ChatSessionResponse
from app.services.chat.session_service import ChatServiceError, ChatSessionService

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeSessionRepo:
    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, ChatSession] = {}

    async def create(
        self,
        *,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        title: str | None = None,
    ) -> ChatSession:
        now = datetime.now(UTC)
        row = ChatSession(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            user_id=user_id,
            title=title,
            created_at=now,
            updated_at=now,
            deleted_at=None,
            deleted_by=None,
        )
        self.rows[row.id] = row
        return row

    async def get(
        self,
        *,
        session_id: uuid.UUID,
        workspace_id: uuid.UUID,
        include_deleted: bool = False,
    ) -> ChatSession | None:
        row = self.rows.get(session_id)
        if row is None or row.workspace_id != workspace_id:
            return None
        if not include_deleted and row.deleted_at is not None:
            return None
        return row

    async def list(
        self,
        *,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        page: int,
        page_size: int,
    ) -> tuple[list[ChatSession], int]:
        items = [
            r
            for r in self.rows.values()
            if r.workspace_id == workspace_id
            and r.user_id == user_id
            and r.deleted_at is None
        ]
        items.sort(key=lambda r: r.updated_at, reverse=True)
        total = len(items)
        start = (page - 1) * page_size
        return items[start : start + page_size], total

    async def exists(
        self,
        *,
        session_id: uuid.UUID,
        workspace_id: uuid.UUID,
        include_deleted: bool = False,
    ) -> bool:
        return (
            await self.get(
                session_id=session_id,
                workspace_id=workspace_id,
                include_deleted=include_deleted,
            )
            is not None
        )

    async def touch(self, session_id: uuid.UUID) -> bool:
        row = self.rows.get(session_id)
        if row is None or row.deleted_at is not None:
            return False
        row.updated_at = datetime.now(UTC)
        return True

    async def soft_delete(
        self,
        *,
        session_id: uuid.UUID,
        workspace_id: uuid.UUID,
        deleted_by: uuid.UUID,
    ) -> bool:
        row = await self.get(
            session_id=session_id,
            workspace_id=workspace_id,
            include_deleted=False,
        )
        if row is None:
            return False
        row.deleted_at = datetime.now(UTC)
        row.deleted_by = deleted_by
        return True


class FakeMessageRepo:
    def __init__(self) -> None:
        self.by_session: dict[uuid.UUID, list[MessageWithRelations]] = {}
        self.by_id: dict[uuid.UUID, MessageWithRelations] = {}
        self.workspace_of: dict[uuid.UUID, uuid.UUID] = {}

    async def list(
        self,
        *,
        session_id: uuid.UUID,
        page: int,
        page_size: int,
    ) -> list[MessageWithRelations]:
        items = list(self.by_session.get(session_id, []))
        items.sort(key=lambda r: r.message.created_at)
        start = (page - 1) * page_size
        return items[start : start + page_size]

    async def get_with_relations_for_workspace(
        self,
        *,
        workspace_id: uuid.UUID,
        message_id: uuid.UUID,
    ) -> MessageWithRelations | None:
        row = self.by_id.get(message_id)
        if row is None:
            return None
        if self.workspace_of.get(message_id) != workspace_id:
            return None
        return row

    async def count(self, *, session_id: uuid.UUID) -> int:
        return len(self.by_session.get(session_id, []))

    async def latest(self, *, session_id: uuid.UUID) -> ChatMessage | None:
        items = self.by_session.get(session_id, [])
        if not items:
            return None
        return max(items, key=lambda r: r.message.created_at).message


def _service(
    sessions: FakeSessionRepo | None = None,
    messages: FakeMessageRepo | None = None,
) -> tuple[ChatSessionService, FakeSessionRepo, FakeMessageRepo]:
    s = sessions or FakeSessionRepo()
    m = messages or FakeMessageRepo()
    return ChatSessionService(s, m), s, m


def _store_message(
    msgs: FakeMessageRepo,
    *,
    workspace_id: uuid.UUID,
    row: MessageWithRelations,
) -> None:
    msgs.by_id[row.message.id] = row
    msgs.workspace_of[row.message.id] = workspace_id
    bucket = msgs.by_session.setdefault(row.message.session_id, [])
    if row not in bucket:
        bucket.append(row)


# ---------------------------------------------------------------------------
# Service unit tests — sessions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_session_without_title() -> None:
    svc, repo, _ = _service()
    ws, user = uuid.uuid4(), uuid.uuid4()
    out = await svc.create_session(workspace_id=ws, user_id=user, title=None)
    assert out.workspace_id == ws
    assert out.title is None
    assert repo.rows[out.id].deleted_at is None


@pytest.mark.asyncio
async def test_create_session_with_title() -> None:
    svc, _, _ = _service()
    out = await svc.create_session(
        workspace_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        title="  Hello  ",
    )
    assert out.title == "Hello"


@pytest.mark.asyncio
async def test_list_sessions_sorted_updated_at_desc() -> None:
    svc, repo, _ = _service()
    ws, user = uuid.uuid4(), uuid.uuid4()
    older = await repo.create(workspace_id=ws, user_id=user, title="old")
    newer = await repo.create(workspace_id=ws, user_id=user, title="new")
    older.updated_at = datetime.now(UTC) - timedelta(hours=2)
    newer.updated_at = datetime.now(UTC)

    items = await svc.list_sessions(
        workspace_id=ws, user_id=user, page=1, page_size=20
    )
    assert [i.id for i in items] == [newer.id, older.id]


@pytest.mark.asyncio
async def test_list_sessions_pagination() -> None:
    svc, repo, _ = _service()
    ws, user = uuid.uuid4(), uuid.uuid4()
    created: list[ChatSession] = []
    for i in range(5):
        row = await repo.create(workspace_id=ws, user_id=user, title=f"s{i}")
        row.updated_at = datetime.now(UTC) - timedelta(minutes=5 - i)
        created.append(row)

    page1 = await svc.list_sessions(
        workspace_id=ws, user_id=user, page=1, page_size=2
    )
    page2 = await svc.list_sessions(
        workspace_id=ws, user_id=user, page=2, page_size=2
    )
    assert len(page1) == 2
    assert len(page2) == 2
    assert {p.id for p in page1}.isdisjoint({p.id for p in page2})


@pytest.mark.asyncio
async def test_list_excludes_other_users_and_deleted() -> None:
    svc, repo, _ = _service()
    ws, owner, other = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    mine = await repo.create(workspace_id=ws, user_id=owner, title="mine")
    await repo.create(workspace_id=ws, user_id=other, title="theirs")
    gone = await repo.create(workspace_id=ws, user_id=owner, title="gone")
    await repo.soft_delete(
        session_id=gone.id, workspace_id=ws, deleted_by=owner
    )

    items = await svc.list_sessions(
        workspace_id=ws, user_id=owner, page=1, page_size=20
    )
    assert [i.id for i in items] == [mine.id]


@pytest.mark.asyncio
async def test_get_session_success() -> None:
    svc, repo, _ = _service()
    ws, user = uuid.uuid4(), uuid.uuid4()
    row = await repo.create(workspace_id=ws, user_id=user, title="t")
    out = await svc.get_session(
        workspace_id=ws, session_id=row.id, user_id=user
    )
    assert out.id == row.id
    assert out.title == "t"


@pytest.mark.asyncio
async def test_get_session_not_found() -> None:
    svc, _, _ = _service()
    with pytest.raises(ChatServiceError) as exc:
        await svc.get_session(
            workspace_id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_session_wrong_workspace() -> None:
    svc, repo, _ = _service()
    ws, other_ws, user = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    row = await repo.create(workspace_id=ws, user_id=user)
    with pytest.raises(ChatServiceError) as exc:
        await svc.get_session(
            workspace_id=other_ws, session_id=row.id, user_id=user
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_soft_delete_hides_from_list_and_detail() -> None:
    svc, repo, _ = _service()
    ws, user = uuid.uuid4(), uuid.uuid4()
    row = await repo.create(workspace_id=ws, user_id=user)
    await svc.delete_session(
        workspace_id=ws,
        session_id=row.id,
        actor_user_id=user,
        actor_role=RoleName.viewer,
    )
    assert repo.rows[row.id].deleted_at is not None
    assert repo.rows[row.id].deleted_by == user
    items = await svc.list_sessions(
        workspace_id=ws, user_id=user, page=1, page_size=20
    )
    assert items == []
    with pytest.raises(ChatServiceError) as exc:
        await svc.get_session(
            workspace_id=ws, session_id=row.id, user_id=user
        )
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# Service unit tests — RBAC delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_owner_can_delete() -> None:
    svc, repo, _ = _service()
    ws, owner = uuid.uuid4(), uuid.uuid4()
    row = await repo.create(workspace_id=ws, user_id=owner)
    await svc.delete_session(
        workspace_id=ws,
        session_id=row.id,
        actor_user_id=owner,
        actor_role=RoleName.editor,
    )
    assert repo.rows[row.id].deleted_at is not None


@pytest.mark.asyncio
async def test_admin_can_delete_others_session() -> None:
    svc, repo, _ = _service()
    ws, owner, admin = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    row = await repo.create(workspace_id=ws, user_id=owner)
    await svc.delete_session(
        workspace_id=ws,
        session_id=row.id,
        actor_user_id=admin,
        actor_role=RoleName.admin,
    )
    assert repo.rows[row.id].deleted_by == admin


@pytest.mark.asyncio
async def test_editor_cannot_delete_others_session() -> None:
    svc, repo, _ = _service()
    ws, owner, editor = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    row = await repo.create(workspace_id=ws, user_id=owner)
    with pytest.raises(ChatServiceError) as exc:
        await svc.delete_session(
            workspace_id=ws,
            session_id=row.id,
            actor_user_id=editor,
            actor_role=RoleName.editor,
        )
    assert exc.value.status_code == 403
    assert repo.rows[row.id].deleted_at is None


@pytest.mark.asyncio
async def test_viewer_cannot_delete_others_session() -> None:
    svc, repo, _ = _service()
    ws, owner, viewer = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    row = await repo.create(workspace_id=ws, user_id=owner)
    with pytest.raises(ChatServiceError) as exc:
        await svc.delete_session(
            workspace_id=ws,
            session_id=row.id,
            actor_user_id=viewer,
            actor_role=RoleName.viewer,
        )
    assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# Service unit tests — messages
# ---------------------------------------------------------------------------


def _msg(
    *,
    session_id: uuid.UUID,
    role: MessageRole,
    content: str,
    created_at: datetime,
    generation: MessageGeneration | None = None,
    citations: list[CitationWithDocument] | None = None,
) -> MessageWithRelations:
    message = ChatMessage(
        id=uuid.uuid4(),
        session_id=session_id,
        role=role,
        content=content,
        created_at=created_at,
    )
    return MessageWithRelations(
        message=message,
        generation=generation,
        citations=citations or [],
    )


@pytest.mark.asyncio
async def test_list_messages_empty_session() -> None:
    svc, repo, msgs = _service()
    ws, user = uuid.uuid4(), uuid.uuid4()
    session = await repo.create(workspace_id=ws, user_id=user)
    out = await svc.list_messages(
        workspace_id=ws,
        session_id=session.id,
        user_id=user,
        page=1,
        page_size=20,
    )
    assert out == []
    assert msgs.by_session.get(session.id) is None or True


@pytest.mark.asyncio
async def test_list_messages_nested_generation_and_citations() -> None:
    svc, repo, msgs = _service()
    ws, user = uuid.uuid4(), uuid.uuid4()
    session = await repo.create(workspace_id=ws, user_id=user)
    t0 = datetime.now(UTC) - timedelta(minutes=2)
    t1 = datetime.now(UTC) - timedelta(minutes=1)

    user_row = _msg(
        session_id=session.id,
        role=MessageRole.user,
        content="What is X?",
        created_at=t0,
    )
    citation = Citation(
        id=uuid.uuid4(),
        message_id=uuid.uuid4(),
        retrieval_id=uuid.uuid4(),
        text_snippet="snippet",
        verified=True,
        order_index=0,
    )
    doc_id = uuid.uuid4()
    assistant_id = uuid.uuid4()
    citation.message_id = assistant_id
    generation = MessageGeneration(
        id=uuid.uuid4(),
        message_id=assistant_id,
        route_type=RouteType.complex,
        confidence_level=ConfidenceLevel.high,
        confidence_score=0.9,
        agent_triggered=False,
        model_used="claude-sonnet",
        prompt_tokens=10,
        completion_tokens=20,
        total_tokens=30,
        cost_usd=Decimal("0.001"),
        latency_ms=100,
        finish_reason=FinishReason.stop,
        created_at=t1,
    )
    assistant = MessageWithRelations(
        message=ChatMessage(
            id=assistant_id,
            session_id=session.id,
            role=MessageRole.assistant,
            content="X is …",
            created_at=t1,
        ),
        generation=generation,
        citations=[CitationWithDocument(citation=citation, document_id=doc_id)],
    )
    msgs.by_session[session.id] = [assistant, user_row]  # wrong order on purpose
    _store_message(msgs, workspace_id=ws, row=assistant)
    _store_message(msgs, workspace_id=ws, row=user_row)

    out = await svc.list_messages(
        workspace_id=ws,
        session_id=session.id,
        user_id=user,
        page=1,
        page_size=20,
    )
    assert len(out) == 2
    assert out[0].role == "user"
    assert out[0].generation is None
    assert out[0].citations == []
    assert out[1].role == "assistant"
    assert out[1].generation is not None
    assert out[1].generation.route_type == "complex"
    assert out[1].generation.agent_triggered is False
    assert len(out[1].citations) == 1
    assert out[1].citations[0].document_id == doc_id
    assert out[1].citations[0].verified is True


@pytest.mark.asyncio
async def test_get_message_detail_by_id() -> None:
    svc, repo, msgs = _service()
    ws, user = uuid.uuid4(), uuid.uuid4()
    session = await repo.create(workspace_id=ws, user_id=user)
    now = datetime.now(UTC)
    citation = Citation(
        id=uuid.uuid4(),
        message_id=uuid.uuid4(),
        retrieval_id=uuid.uuid4(),
        text_snippet="snippet",
        verified=True,
        order_index=0,
    )
    assistant_id = uuid.uuid4()
    citation.message_id = assistant_id
    generation = MessageGeneration(
        id=uuid.uuid4(),
        message_id=assistant_id,
        route_type=RouteType.complex,
        confidence_level=ConfidenceLevel.high,
        confidence_score=0.91,
        agent_triggered=False,
        model_used="claude-sonnet",
        prompt_tokens=1,
        completion_tokens=2,
        total_tokens=3,
        cost_usd=Decimal("0.001"),
        latency_ms=50,
        finish_reason=FinishReason.stop,
        created_at=now,
    )
    assistant = MessageWithRelations(
        message=ChatMessage(
            id=assistant_id,
            session_id=session.id,
            role=MessageRole.assistant,
            content="Answer",
            created_at=now,
        ),
        generation=generation,
        citations=[
            CitationWithDocument(citation=citation, document_id=uuid.uuid4())
        ],
    )
    _store_message(msgs, workspace_id=ws, row=assistant)

    out = await svc.get_message(workspace_id=ws, message_id=assistant_id)
    assert out.id == assistant_id
    assert out.role == "assistant"
    assert out.generation is not None
    assert out.generation.route_type == "complex"
    assert len(out.citations) == 1

    with pytest.raises(ChatServiceError) as exc:
        await svc.get_message(workspace_id=uuid.uuid4(), message_id=assistant_id)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_list_message_citations_verified_only() -> None:
    svc, repo, msgs = _service()
    ws, user = uuid.uuid4(), uuid.uuid4()
    session = await repo.create(workspace_id=ws, user_id=user)
    now = datetime.now(UTC)
    message_id = uuid.uuid4()
    verified = Citation(
        id=uuid.uuid4(),
        message_id=message_id,
        retrieval_id=uuid.uuid4(),
        text_snippet="ok",
        verified=True,
        order_index=0,
    )
    unverified = Citation(
        id=uuid.uuid4(),
        message_id=message_id,
        retrieval_id=uuid.uuid4(),
        text_snippet="no",
        verified=False,
        order_index=1,
    )
    row = MessageWithRelations(
        message=ChatMessage(
            id=message_id,
            session_id=session.id,
            role=MessageRole.assistant,
            content="Answer",
            created_at=now,
        ),
        generation=None,
        citations=[
            CitationWithDocument(citation=verified, document_id=uuid.uuid4()),
            CitationWithDocument(citation=unverified, document_id=uuid.uuid4()),
        ],
    )
    _store_message(msgs, workspace_id=ws, row=row)

    citations = await svc.list_message_citations(
        workspace_id=ws, message_id=message_id
    )
    assert len(citations) == 1
    assert citations[0].id == verified.id
    assert citations[0].verified is True

    user_msg = _msg(
        session_id=session.id,
        role=MessageRole.user,
        content="Q",
        created_at=now,
    )
    _store_message(msgs, workspace_id=ws, row=user_msg)
    empty = await svc.list_message_citations(
        workspace_id=ws, message_id=user_msg.message.id
    )
    assert empty == []


# ---------------------------------------------------------------------------
# API tests — RBAC read roles
# ---------------------------------------------------------------------------


class FakeChatService:
    """Minimal stub for HTTP RBAC smoke tests."""

    def __init__(self) -> None:
        self.deleted: list[dict[str, Any]] = []
        self.listed_by: list[uuid.UUID] = []
        self.message_detail: ChatMessageResponse | None = None
        self.citations: list[Any] = []
        self.missing_message = False

    async def list_sessions(self, **kwargs: Any) -> list[ChatSessionResponse]:
        self.listed_by.append(kwargs["user_id"])
        return []

    async def create_session(self, **kwargs: Any) -> ChatSessionResponse:
        now = datetime.now(UTC)
        return ChatSessionResponse(
            id=uuid.uuid4(),
            workspace_id=kwargs["workspace_id"],
            title=kwargs.get("title"),
            created_at=now,
            updated_at=now,
        )

    async def get_session(self, **kwargs: Any) -> ChatSessionResponse:
        now = datetime.now(UTC)
        return ChatSessionResponse(
            id=kwargs["session_id"],
            workspace_id=kwargs["workspace_id"],
            title=None,
            created_at=now,
            updated_at=now,
        )

    async def delete_session(self, **kwargs: Any) -> None:
        self.deleted.append(kwargs)

    async def list_messages(self, **kwargs: Any) -> list[ChatMessageResponse]:
        return []

    async def get_message(self, **kwargs: Any) -> ChatMessageResponse:
        if self.missing_message or self.message_detail is None:
            raise ChatServiceError(
                "not_found",
                "Chat message not found in this workspace",
                status_code=404,
            )
        return self.message_detail

    async def list_message_citations(self, **kwargs: Any) -> list[Any]:
        if self.missing_message:
            raise ChatServiceError(
                "not_found",
                "Chat message not found in this workspace",
                status_code=404,
            )
        return list(self.citations)

async def _api_client(
    *,
    user_id: uuid.UUID,
    role: RoleName,
    service: FakeChatService,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncClient:
    async def _user() -> CurrentUser:
        return CurrentUser(id=user_id, email="u@ex.com", full_name="U")

    async def _db():
        yield object()

    async def _role(self: Any, *, user_id: uuid.UUID, workspace_id: uuid.UUID) -> RoleName | None:
        return role

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_db_session] = _db
    app.dependency_overrides[get_chat_session_service] = lambda: service
    app.dependency_overrides[get_workspace_rate_limiter] = (
        lambda: InMemoryWorkspaceRateLimiter()
    )
    monkeypatch.setattr(WorkspaceMemberRepository, "get_role_for_user", _role)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [RoleName.viewer, RoleName.editor, RoleName.admin])
async def test_api_member_roles_can_list(
    role: RoleName, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws, user = uuid.uuid4(), uuid.uuid4()
    svc = FakeChatService()
    client = await _api_client(
        user_id=user, role=role, service=svc, monkeypatch=monkeypatch
    )
    try:
        async with client:
            resp = await client.get(f"/workspaces/{ws}/chat/sessions")
        assert resp.status_code == 200
        assert resp.json() == []
        assert svc.listed_by == [user]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_create_and_get(monkeypatch: pytest.MonkeyPatch) -> None:
    ws, user = uuid.uuid4(), uuid.uuid4()
    svc = FakeChatService()
    client = await _api_client(
        user_id=user, role=RoleName.editor, service=svc, monkeypatch=monkeypatch
    )
    try:
        async with client:
            created = await client.post(
                f"/workspaces/{ws}/chat/sessions", json={"title": "T"}
            )
            assert created.status_code == 201
            body = created.json()
            assert body["title"] == "T"
            assert body["workspace_id"] == str(ws)

            detail = await client.get(
                f"/workspaces/{ws}/chat/sessions/{body['id']}"
            )
            assert detail.status_code == 200
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_owner_delete_204(monkeypatch: pytest.MonkeyPatch) -> None:
    ws, user, session_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    svc = FakeChatService()
    client = await _api_client(
        user_id=user, role=RoleName.viewer, service=svc, monkeypatch=monkeypatch
    )
    try:
        async with client:
            resp = await client.delete(
                f"/workspaces/{ws}/chat/sessions/{session_id}"
            )
        assert resp.status_code == 204
        assert svc.deleted[0]["actor_user_id"] == user
        assert svc.deleted[0]["actor_role"] is RoleName.viewer
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_delete_forbidden_maps_403(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class DenyService(FakeChatService):
        async def delete_session(self, **kwargs: Any) -> None:
            raise ChatServiceError(
                "forbidden",
                "Only the session owner or a workspace admin can delete this session",
                status_code=403,
            )

    ws, user, session_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    client = await _api_client(
        user_id=user,
        role=RoleName.editor,
        service=DenyService(),
        monkeypatch=monkeypatch,
    )
    try:
        async with client:
            resp = await client.delete(
                f"/workspaces/{ws}/chat/sessions/{session_id}"
            )
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "forbidden"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_list_messages_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    ws, user, session_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    client = await _api_client(
        user_id=user,
        role=RoleName.admin,
        service=FakeChatService(),
        monkeypatch=monkeypatch,
    )
    try:
        async with client:
            resp = await client.get(
                f"/workspaces/{ws}/chat/sessions/{session_id}/messages"
            )
        assert resp.status_code == 200
        assert resp.json() == []
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_get_message_and_citations(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.schemas.chat import CitationResponse

    ws, user, message_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    now = datetime.now(UTC)
    svc = FakeChatService()
    svc.message_detail = ChatMessageResponse(
        id=message_id,
        session_id=uuid.uuid4(),
        role="assistant",
        content="Hello",
        generation=None,
        citations=[],
        created_at=now,
    )
    citation_id = uuid.uuid4()
    svc.citations = [
        CitationResponse(
            id=citation_id,
            message_id=message_id,
            retrieval_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            chunk_id=None,
            document_version_id=None,
            text_snippet="snippet",
            verified=True,
            order_index=0,
            location=None,
            locator=None,
        )
    ]
    client = await _api_client(
        user_id=user,
        role=RoleName.viewer,
        service=svc,
        monkeypatch=monkeypatch,
    )
    try:
        async with client:
            detail = await client.get(
                f"/workspaces/{ws}/chat/messages/{message_id}"
            )
            citations = await client.get(
                f"/workspaces/{ws}/chat/messages/{message_id}/citations"
            )
        assert detail.status_code == 200
        assert detail.json()["id"] == str(message_id)
        assert detail.json()["role"] == "assistant"
        assert citations.status_code == 200
        body = citations.json()
        assert len(body) == 1
        assert body[0]["id"] == str(citation_id)
        assert body[0]["verified"] is True
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_get_message_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    ws, user, message_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    svc = FakeChatService()
    svc.missing_message = True
    client = await _api_client(
        user_id=user,
        role=RoleName.editor,
        service=svc,
        monkeypatch=monkeypatch,
    )
    try:
        async with client:
            detail = await client.get(
                f"/workspaces/{ws}/chat/messages/{message_id}"
            )
            citations = await client.get(
                f"/workspaces/{ws}/chat/messages/{message_id}/citations"
            )
        assert detail.status_code == 404
        assert citations.status_code == 404
    finally:
        app.dependency_overrides.clear()
