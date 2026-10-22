"""Core data models for BeeBridge memory."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TodoKind(str, Enum):
    MEDICATION = "medication"
    APPOINTMENT = "appointment"
    SHOPPING = "shopping"
    CALL = "call"
    DELIVERY = "delivery"
    GENERAL = "general"


class Conversation(BaseModel):
    """One conversation captured by a Bee device (or Bee on Apple Watch)."""
    id: str
    title: str
    transcript: str
    source: str = "bee"  # bee | bee-watch | sample | manual
    participants: list[str] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=utcnow)
    location: Optional[str] = None


class Fact(BaseModel):
    id: str
    conversation_id: str
    text: str
    category: str = "general"  # health | family | personal | general
    created_at: datetime = Field(default_factory=utcnow)


class Todo(BaseModel):
    id: str
    conversation_id: Optional[str] = None
    text: str
    kind: TodoKind = TodoKind.GENERAL
    due_text: Optional[str] = None  # human phrase as spoken, e.g. "tomorrow at 10am"
    done: bool = False
    created_at: datetime = Field(default_factory=utcnow)


class Alert(BaseModel):
    id: str
    text: str
    source: str  # ring | beebridge
    created_at: datetime = Field(default_factory=utcnow)
    spoken: bool = False  # whether an Alexa announcement was queued
