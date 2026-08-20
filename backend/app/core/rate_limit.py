# =============================================================================
# File: rate_limit.py
# Module/Service: API Gateway / Auth Middleware
# Layer: Adapter
# Purpose: Per-workspace API request rate limiting backed by Redis.
# Responsibilities:
#   - Atomic fixed-window counter (Lua INCR + EXPIRE) per workspace_id
#   - In-memory backend for unit tests / CI without Redis
# Dependencies:
#   - redis, app.core.config
# Public Exports:
#   - RateLimitResult, WorkspaceRateLimiter
#   - InMemoryWorkspaceRateLimiter, RedisWorkspaceRateLimiter
#   - get_workspace_rate_limiter
# Database/Table: N/A (Redis key ratelimit:workspace:{id}:{window})
# Related Modules: app.dependencies.rate_limit
# Important Notes:
#   - This is the general API-layer rate limit (FR12). It is NOT the LLM call
#     quota (message_generations / query_logs cost controls) — that lands in
#     phase 2 when those tables are wired. Do not conflate the two.
# =============================================================================

from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import lru_cache

import redis

from app.core.config import Settings, get_settings

# Atomic fixed-window: INCR then EXPIRE on first hit; return allowed + TTL.
_FIXED_WINDOW_LUA = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local current = redis.call('INCR', key)
if current == 1 then
  redis.call('EXPIRE', key, window)
end
local ttl = redis.call('TTL', key)
if ttl < 0 then
  ttl = window
end
if current > limit then
  return {0, ttl, current}
end
return {1, ttl, current}
"""


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    allowed: bool
    retry_after: int
    remaining: int


class WorkspaceRateLimiter(ABC):
    @abstractmethod
    def hit(
        self,
        workspace_id: uuid.UUID,
        *,
        limit: int,
        window_seconds: int,
    ) -> RateLimitResult: ...

    @abstractmethod
    def reset(self, workspace_id: uuid.UUID) -> None:
        """Clear counters for a workspace (tests / admin)."""


def _window_key(workspace_id: uuid.UUID, window_seconds: int, now: float | None = None) -> str:
    ts = int(now if now is not None else time.time())
    bucket = ts // window_seconds
    return f"ratelimit:workspace:{workspace_id}:{bucket}"


class InMemoryWorkspaceRateLimiter(WorkspaceRateLimiter):
    """Process-local fixed-window counter for tests (not multi-process safe)."""

    def __init__(self) -> None:
        self._counts: dict[str, int] = {}
        self._expiry: dict[str, float] = {}

    def hit(
        self,
        workspace_id: uuid.UUID,
        *,
        limit: int,
        window_seconds: int,
    ) -> RateLimitResult:
        now = time.time()
        key = _window_key(workspace_id, window_seconds, now)
        # Drop expired keys
        exp = self._expiry.get(key)
        if exp is not None and exp <= now:
            self._counts.pop(key, None)
            self._expiry.pop(key, None)

        count = self._counts.get(key, 0) + 1
        self._counts[key] = count
        if key not in self._expiry:
            self._expiry[key] = (now // window_seconds + 1) * window_seconds

        retry_after = max(1, int(self._expiry[key] - now))
        if count > limit:
            return RateLimitResult(allowed=False, retry_after=retry_after, remaining=0)
        return RateLimitResult(
            allowed=True,
            retry_after=retry_after,
            remaining=max(0, limit - count),
        )

    def reset(self, workspace_id: uuid.UUID) -> None:
        prefix = f"ratelimit:workspace:{workspace_id}:"
        for key in list(self._counts):
            if key.startswith(prefix):
                self._counts.pop(key, None)
                self._expiry.pop(key, None)


class RedisWorkspaceRateLimiter(WorkspaceRateLimiter):
    def __init__(self, redis_url: str) -> None:
        # Short timeouts — sync Redis must not stall the async event loop.
        self._client = redis.Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        self._script = self._client.register_script(_FIXED_WINDOW_LUA)

    def hit(
        self,
        workspace_id: uuid.UUID,
        *,
        limit: int,
        window_seconds: int,
    ) -> RateLimitResult:
        key = _window_key(workspace_id, window_seconds)
        allowed, ttl, current = self._script(keys=[key], args=[limit, window_seconds])
        allowed_i = int(allowed)
        ttl_i = max(1, int(ttl))
        current_i = int(current)
        if allowed_i == 0:
            return RateLimitResult(allowed=False, retry_after=ttl_i, remaining=0)
        return RateLimitResult(
            allowed=True,
            retry_after=ttl_i,
            remaining=max(0, limit - current_i),
        )

    def reset(self, workspace_id: uuid.UUID) -> None:
        pattern = f"ratelimit:workspace:{workspace_id}:*"
        for key in self._client.scan_iter(match=pattern, count=100):
            self._client.delete(key)


@lru_cache
def get_workspace_rate_limiter() -> WorkspaceRateLimiter:
    settings: Settings = get_settings()
    if settings.app_env == "test":
        return InMemoryWorkspaceRateLimiter()
    return RedisWorkspaceRateLimiter(settings.redis_url)
