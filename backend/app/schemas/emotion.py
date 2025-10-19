from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class EmotionCreate(BaseModel):
    emotion_code: str = Field(..., min_length=1, max_length=50)
    intensity: int = Field(..., ge=1, le=5)
    note: str | None = Field(default=None, max_length=500)
    source: str | None = Field(default="web")


class EmotionEntryModel(BaseModel):
    id: int
    user_id: int | None
    emotion_code: str
    intensity: int
    note: str | None
    source: str
    created_at: datetime

    model_config = {
        "from_attributes": True,
    }


class EmotionListResponse(BaseModel):
    items: list[EmotionEntryModel]


class EmotionCreateResponse(BaseModel):
    ok: bool = True
    id: int
