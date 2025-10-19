from __future__ import annotations

import hashlib

from fastapi import Cookie, Header, HTTPException, Request, status

from ..services.storage import StorageService


def _hash_identifier(value: int) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:12]


def enforce_webhook_secret(
    request: Request,
    token: str | None = Header(default=None, alias="X-Telegram-Bot-Api-Secret-Token"),
) -> None:
    """Validate Telegram secret header when configured."""

    settings = request.app.state.settings
    expected = getattr(settings, "webhook_secret_token", None)
    if expected and token != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid webhook token",
        )


async def resolve_authenticated_user(
    request: Request,
    tg_header: str | None = Header(default=None, alias="X-Soznai-Tg-Id"),
    session_token: str | None = Cookie(default=None, alias="soz_session"),
) -> int:
    storage: StorageService = request.app.state.storage_service
    user_id: int | None = None

    if tg_header:
        try:
            tg_id = int(tg_header)
        except ValueError as exc:  # pragma: no cover - defensive
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="invalid tg id",
            ) from exc
        user = await storage.ensure_user_by_telegram(tg_id)
        user_id = user.id
        request.state.telemetry_user = _hash_identifier(tg_id)
    elif session_token:
        user = await storage.get_user_by_session(session_token)
        if user:
            user_id = user.id
            if user.tg_id:
                request.state.telemetry_user = _hash_identifier(user.tg_id)
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication required",
        )

    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication required",
        )

    request.state.current_user_id = user_id
    return user_id


async def require_admin_token(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
    admin_header: str | None = Header(default=None, alias="X-Soznai-Admin-Token"),
) -> None:
    settings = request.app.state.settings
    expected = getattr(settings, "admin_api_token", None)
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="admin disabled",
        )
    token_value: str | None = None
    if authorization and authorization.lower().startswith("bearer "):
        token_value = authorization.split(" ", 1)[1].strip()
    elif admin_header:
        token_value = admin_header.strip()
    if token_value != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="admin token invalid")
