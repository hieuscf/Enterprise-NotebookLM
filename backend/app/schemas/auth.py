# =============================================================================
# File: auth.py
# Module/Service: Auth Service
# Layer: Schema
# Purpose: Pydantic request/response models for /auth/* (FR12).
# Responsibilities:
#   - Define LoginRequest, RefreshRequest, AuthToken, Unauthorized payloads
# Dependencies:
#   - Pydantic
# Public Exports:
#   - LoginRequest, RefreshRequest, AuthToken, Unauthorized
# Database/Table: N/A
# Related Modules: app.api.auth, Enterprise_notebooklm_openapi.yaml (AuthToken)
# Important Notes: OpenAPI YAML not in repo yet; fields match FR12 brief.
# =============================================================================

from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class AuthToken(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="Access token lifetime in seconds")


class Unauthorized(BaseModel):
    """OpenAPI Unauthorized error body (detail message)."""

    detail: str
