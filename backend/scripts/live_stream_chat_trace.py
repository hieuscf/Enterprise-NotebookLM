# =============================================================================
# File: live_stream_chat_trace.py
# Module/Service: Chat Service (diagnostic)
# Layer: Worker
# Purpose: One-shot live SSE trace for chat streaming + citation UUID check.
# Responsibilities:
#   - Mint a short-lived access JWT for an existing workspace member
#   - POST .../messages with Accept: text/event-stream
#   - Print event sequence and assert no raw UUIDs in streamed answer
# Dependencies:
#   - httpx, PyJWT, app settings via env inside container
# Public Exports:
#   - N/A (script)
# Database/Table: users, workspace_members, chat_sessions (read ids only)
# Related Modules: message_service.stream_answer_events
# Important Notes: Run inside backend-api container against live stack.
# =============================================================================

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import jwt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
BRACKETED_UUID = re.compile(
    r"\[\s*[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\s*\]"
)

WORKSPACE_ID = os.environ.get("TRACE_WORKSPACE_ID", "54b30d4b-e4e9-42f8-b8b0-6807c00418b9")
SESSION_ID = os.environ.get("TRACE_SESSION_ID", "018e715c-7819-4698-90ee-b23188bd5825")
QUESTION = os.environ.get(
    "TRACE_QUESTION",
    "Quyền và nghĩa vụ của Bên A là gì?",
)
BASE = os.environ.get("TRACE_BASE_URL", "http://127.0.0.1:8000")


async def _load_session_owner() -> str:
    engine = create_async_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        row = (
            await session.execute(
                text(
                    """
                    SELECT cs.user_id::text
                    FROM chat_sessions cs
                    WHERE cs.id = :sid AND cs.workspace_id = :ws
                    LIMIT 1
                    """
                ),
                {"sid": SESSION_ID, "ws": WORKSPACE_ID},
            )
        ).first()
    await engine.dispose()
    if row is None:
        raise RuntimeError("Chat session not found for TRACE_SESSION_ID")
    return str(row[0])


def _mint_token(user_id: str) -> str:
    secret = os.environ.get(
        "JWT_SECRET_KEY",
        "dev-only-change-me-enterprise-notebooklm-jwt",
    )
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "type": "access",
        "workspaces": [{"workspace_id": WORKSPACE_ID, "role": "editor"}],
        "iat": now,
        "exp": now + timedelta(minutes=15),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


async def main() -> int:
    user_id = await _load_session_owner()
    token = _mint_token(user_id)
    url = f"{BASE}/workspaces/{WORKSPACE_ID}/chat/sessions/{SESSION_ID}/messages"
    print(f"request_id: (from response headers if present)")
    print(f"session_id: {SESSION_ID}")
    print(f"user_id: {user_id}")
    print(f"POST {url}")
    print(f"question: {QUESTION}")
    print("--- SSE TRACE ---")

    events: list[dict] = []
    streamed_content = ""
    final_message: dict | None = None

    async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=30.0)) as client:
        async with client.stream(
            "POST",
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "text/event-stream",
                "Content-Type": "application/json",
            },
            json={"content": QUESTION},
        ) as resp:
            print(f"HTTP {resp.status_code} content-type={resp.headers.get('content-type')}")
            if resp.status_code != 200:
                body = await resp.aread()
                print(body.decode("utf-8", errors="replace")[:500])
                return 1
            buffer = ""
            async for chunk in resp.aiter_text():
                buffer += chunk
                while "\n\n" in buffer:
                    frame, buffer = buffer.split("\n\n", 1)
                    data_line = next(
                        (ln for ln in frame.split("\n") if ln.startswith("data:")),
                        None,
                    )
                    if not data_line:
                        continue
                    payload = json.loads(data_line[5:].strip())
                    etype = payload.get("type")
                    events.append(payload)
                    print(f"event #{len(events)}: type={etype}")
                    if etype == "token":
                        streamed_content += payload.get("text") or ""
                    elif etype == "generation":
                        final_message = payload.get("message")
                        if final_message and final_message.get("content"):
                            streamed_content = final_message["content"]
                    elif etype == "error":
                        print("ERROR frame:", payload)
                        return 1

    print("--- SUMMARY ---")
    print(f"event_count={len(events)}")
    print(f"event_types={[e.get('type') for e in events]}")
    print(f"streamed_content_len={len(streamed_content)}")
    print(f"assistant_message_id={(final_message or {}).get('id')}")
    print("content_preview:")
    print(streamed_content[:400])
    print("---")

    if not events:
        print("FAIL: no SSE events")
        return 1
    if events[-1].get("type") != "done":
        print("FAIL: last event is not done")
        return 1
    if not streamed_content.strip():
        print("FAIL: empty streamed content (BUG 1)")
        return 1
    if BRACKETED_UUID.search(streamed_content):
        print("FAIL: bracketed UUID still in answer (BUG 2)")
        print(BRACKETED_UUID.findall(streamed_content)[:5])
        return 1
    # Bare UUIDs should not appear as citation markers either.
    leaked = [u for u in UUID_RE.findall(streamed_content) if u.lower() in streamed_content.lower()]
    # Allow none — display indexes only.
    if any(f"[{u}]" in streamed_content for u in UUID_RE.findall(streamed_content)):
        print("FAIL: UUID markers remain")
        return 1

    citations = (final_message or {}).get("citations") or []
    print(f"citations={len(citations)}")
    for c in citations[:5]:
        snip = (c.get("text_snippet") or "")[:80]
        print(f"  [{c.get('order_index')}] verified={c.get('verified')} snippet={snip!r}")
        if UUID_RE.fullmatch((c.get("text_snippet") or "").replace("Cited chunk ", "").strip()):
            print("FAIL: citation snippet is raw UUID")
            return 1
        if (c.get("text_snippet") or "").startswith("Cited chunk "):
            print("FAIL: citation snippet still uses Cited chunk UUID fallback")
            return 1

    print("PASS: live stream has content and no citation UUID leak")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
