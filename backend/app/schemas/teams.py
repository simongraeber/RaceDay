import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class TeamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    race_name: str = Field(min_length=1, max_length=120)
    race_date: date
    race_distance_m: int = Field(gt=0, le=500_000)


class TeamCreated(BaseModel):
    id: uuid.UUID


class MyTeamOut(BaseModel):
    id: uuid.UUID
    name: str
    race_name: str
    race_date: date
    race_distance_m: int


class RunOut(BaseModel):
    date: date
    distance_km: float
    pace_seconds_km: int | None


class MemberOut(BaseModel):
    name: str
    avatar_url: str | None
    avatar_is_generated: bool
    goal_seconds: int | None
    km_7d: float
    runs_7d: int
    last_4_weeks_km: float
    prediction_seconds: int | None
    best_km_seconds: int | None
    recent_runs: list[RunOut]


class StatCardOut(BaseModel):
    key: str
    icon: str
    label: str
    value: str
    detail: str
    image_url: str | None = None


class HighlightsOut(BaseModel):
    window_days: int
    total_km: float
    total_runs: int
    cards: list[StatCardOut]
    together_image_url: str | None = None


class CoachNoteOut(BaseModel):
    name: str
    text: str


class CoachOut(BaseModel):
    source: Literal["ai", "coach"]
    generated_at: datetime | None
    notes: list[CoachNoteOut]


class ViewerOut(BaseModel):
    visible: bool
    goal_seconds: int | None
    avatar_url: str | None
    has_avatar: bool
    needs_reconnect: bool


class TeamOut(BaseModel):
    name: str
    race_name: str
    race_date: date
    race_distance_m: int
    members: list[MemberOut]
    highlights: HighlightsOut
    coach: CoachOut
    viewer: ViewerOut | None


class MembershipUpdate(BaseModel):
    visible: bool | None = None
    goal_seconds: int | None = Field(default=None, gt=0, le=24 * 3600)
