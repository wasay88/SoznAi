from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr


class MagicLinkRequest(BaseModel):
    email: EmailStr


class MagicLinkResponse(BaseModel):
    ok: bool = True


class AuthSessionInfo(BaseModel):
    ok: bool = True
    token: str
    expires_at: datetime
