# =============================================================================
# File: conftest.py
# Module/Service: Auth Service (tests)
# Layer: Presentation
# Purpose: Shared pytest fixtures for auth unit/API tests (no Postgres/Redis).
# Responsibilities:
#   - Provide in-memory refresh store for API tests
# Dependencies:
#   - pytest, app.core.refresh_token_store
# Public Exports:
#   - fixture: refresh_store
# Database/Table: N/A
# Related Modules: tests/test_auth.py
# Important Notes: CI has no Postgres/Redis — auth tests use fakes + overrides.
# =============================================================================

import pytest

from app.core.refresh_token_store import InMemoryRefreshTokenStore, get_refresh_token_store


@pytest.fixture
def refresh_store() -> InMemoryRefreshTokenStore:
    get_refresh_token_store.cache_clear()
    return InMemoryRefreshTokenStore()
