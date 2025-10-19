from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field


class JournalCreate(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)
    source: str | None = Field(default="web")


class JournalEntryModel(BaseModel):
    id: int
    user_id: int | None
    entry_text: str = Field(exclude=True)
    source: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @computed_field(return_type=str)
    def text(self) -> str:
        return self.entry_text


class JournalListResponse(BaseModel):
    items: list[JournalEntryModel]


class JournalCreateResponse(BaseModel):
    ok: bool = True
    id: int
