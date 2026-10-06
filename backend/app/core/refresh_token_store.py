# =============================================================================
# File: refresh_token_store.py
# Module/Service: API Gateway / Auth Middleware
# Layer: Adapter
# Purpose: Persist the single active refresh-token jti per user (revocation).
# Responsibilities:
#   - Save / validate / rotate refresh token jti (one active session minimum)
#   - Redis implementation for runtime; in-memory for unit tests
# Dependencies:
#   - redis (sync client), app.core.config
# Public Exports:
#   - RefreshTokenStore, InMemoryRefreshTokenStore, RedisRefreshTokenStore
#   - get_refresh_token_store
# Database/Table: N/A (Redis key auth:refresh:{user_id})
# Related Modules: app.services.auth
# Important Notes: Phase 1.2 — single active refresh jti per user; no device list.
#   Keep previous jti valid briefly (grace) so concurrent BFF refreshes do not
#   401 each other after rotation.
# =============================================================================

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from functools import lru_cache

import redis

from app.core.config import Settings, get_settings

# Concurrent proxy refreshes (e.g. document + PDF content) may present the
# pre-rotation refresh token for a short window after a successful rotate.
_PREV_JTI_GRACE_SECONDS = 30


class RefreshTokenStore(ABC):
    """Minimal single-active-refresh-token store (no multi-device revoke list)."""

    @abstractmethod
    def save(self, user_id: uuid.UUID, jti: str, ttl_seconds: int) -> None: ...

    @abstractmethod
    def get(self, user_id: uuid.UUID) -> str | None: ...

    @abstractmethod
    def delete(self, user_id: uuid.UUID) -> None: ...

    def matches(self, user_id: uuid.UUID, jti: str) -> bool:
        current = self.get(user_id)
        if current is not None and current == jti:
            return True
        previous = self.get_previous(user_id)
        return previous is not None and previous == jti

    def get_previous(self, user_id: uuid.UUID) -> str | None:
        """Optional previous jti still accepted during rotation grace."""
        return None


class InMemoryRefreshTokenStore(RefreshTokenStore):
    """Process-local store for tests / offline CI (not multi-process safe)."""

    def __init__(self) -> None:
        self._data: dict[str, str] = {}
        self._prev: dict[str, str] = {}

    def save(self, user_id: uuid.UUID, jti: str, ttl_seconds: int) -> None:
        del ttl_seconds  # TTL not enforced in-memory; tests control expiry via JWT
        key = str(user_id)
        old = self._data.get(key)
        if old and old != jti:
            self._prev[key] = old
        self._data[key] = jti

    def get(self, user_id: uuid.UUID) -> str | None:
        return self._data.get(str(user_id))

    def get_previous(self, user_id: uuid.UUID) -> str | None:
        return self._prev.get(str(user_id))

    def delete(self, user_id: uuid.UUID) -> None:
        key = str(user_id)
        self._data.pop(key, None)
        self._prev.pop(key, None)


class RedisRefreshTokenStore(RefreshTokenStore):
    def __init__(self, redis_url: str) -> None:
        # Short timeouts — a hung Redis must not freeze the FastAPI event loop
        # (sync client runs inline on request threads / async loop).
        self._client = redis.Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )

    @staticmethod
    def _key(user_id: uuid.UUID) -> str:
        return f"auth:refresh:{user_id}"

    @staticmethod
    def _prev_key(user_id: uuid.UUID) -> str:
        return f"auth:refresh:prev:{user_id}"

    def save(self, user_id: uuid.UUID, jti: str, ttl_seconds: int) -> None:
        old = self.get(user_id)
        if old and old != jti:
            self._client.set(
                self._prev_key(user_id),
                old,
                ex=min(_PREV_JTI_GRACE_SECONDS, max(1, ttl_seconds)),
            )
        self._client.set(self._key(user_id), jti, ex=ttl_seconds)

    def get(self, user_id: uuid.UUID) -> str | None:
        value = self._client.get(self._key(user_id))
        return value if isinstance(value, str) else None

    def get_previous(self, user_id: uuid.UUID) -> str | None:
        value = self._client.get(self._prev_key(user_id))
        return value if isinstance(value, str) else None

    def delete(self, user_id: uuid.UUID) -> None:
        self._client.delete(self._key(user_id), self._prev_key(user_id))


@lru_cache
def get_refresh_token_store() -> RefreshTokenStore:
    settings: Settings = get_settings()
    if settings.app_env == "test":
        return InMemoryRefreshTokenStore()
    return RedisRefreshTokenStore(settings.redis_url)
