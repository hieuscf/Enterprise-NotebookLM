# =============================================================================
# File: auth.py
# Module/Service: Auth Service
# Layer: Presentation
# Purpose: FastAPI routes for POST /auth/login, /auth/refresh, GET /auth/me.
# Responsibilities:
#   - Validate request bodies, call AuthService, map AuthError → 401
# Dependencies:
#   - FastAPI, app.services.auth, app.dependencies.auth, app.schemas.*
# Public Exports:
#   - router
# Database/Table: users, workspace_members, roles
# Related Modules: Enterprise_notebooklm_openapi.yaml (auth paths)
# Important Notes: login/refresh are public; /me requires Bearer access token.
# =============================================================================

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies.auth import CurrentUser, get_auth_service, get_current_user
from app.schemas.auth import AuthToken, LoginRequest, RefreshRequest, Unauthorized
from app.schemas.users import UserResponse
from app.services.auth import AuthError, AuthService

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post(
    "/login",
    response_model=AuthToken,
    responses={status.HTTP_401_UNAUTHORIZED: {"model": Unauthorized}},
)
async def login(
    body: LoginRequest,
    auth: AuthService = Depends(get_auth_service),
) -> AuthToken:
    try:
        return await auth.login(body.email, body.password)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=exc.detail,
        ) from exc


@router.post(
    "/refresh",
    response_model=AuthToken,
    responses={status.HTTP_401_UNAUTHORIZED: {"model": Unauthorized}},
)
async def refresh(
    body: RefreshRequest,
    auth: AuthService = Depends(get_auth_service),
) -> AuthToken:
    try:
        return await auth.refresh(body.refresh_token)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=exc.detail,
        ) from exc


@router.get(
    "/me",
    response_model=UserResponse,
    responses={status.HTTP_401_UNAUTHORIZED: {"model": Unauthorized}},
)
async def me(
    current_user: CurrentUser = Depends(get_current_user),
    auth: AuthService = Depends(get_auth_service),
) -> UserResponse:
    try:
        return await auth.get_me(current_user.id)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=exc.detail,
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
