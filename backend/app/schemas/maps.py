from datetime import date, datetime

from pydantic import BaseModel


class TrackOut(BaseModel):
    name: str
    avatar_url: str | None
    avatar_is_generated: bool
    # Character sheet for the running rig; falls back to the plain avatar when missing
    rig_url: str | None
    date: date
    distance_km: float
    duration_s: int
    pace_seconds_km: int | None
    # Runs sharing a group started together, so their avatars run side by side
    group: int
    path: list[tuple[float, float]]


class MapOut(BaseModel):
    days: int
    generated_at: datetime
    heat: list[list[tuple[float, float]]]
    tracks: list[TrackOut]


class MapTokenOut(BaseModel):
    token: str
