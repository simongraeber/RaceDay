"""Team map data: a heat trace of every stored route plus the newest run per runner."""

import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import asin, cos, radians, sin, sqrt

import jwt
import polyline
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Activity, Athlete, Avatar, AvatarRig, Membership, Team
from app.schemas.maps import MapOut, RouteOut, TrackOut

HISTORY = timedelta(days=365)
TRACK_WINDOW = timedelta(days=7)
HEAT_RUNS = 200
HEAT_POINTS = 6_000
TRACK_POINTS = 150
TOGETHER_WINDOW = timedelta(minutes=20)
TOGETHER_METERS = 500
CACHE_TTL_S = 300
TOKEN_TTL = timedelta(minutes=30)

_cache: dict[str, tuple[float, MapOut]] = {}


def map_token() -> str:
    """Short-lived MapKit JS token, signed from the .p8 key when configured."""
    if settings.apple_maps_private_key and settings.apple_maps_key_id and settings.apple_maps_team_id:
        now = datetime.now(timezone.utc)
        return jwt.encode(
            {
                "iss": settings.apple_maps_team_id,
                "iat": int(now.timestamp()),
                "exp": int((now + TOKEN_TTL).timestamp()),
                "origin": settings.app_base_url.rstrip("/"),
            },
            settings.apple_maps_private_key.replace("\\n", "\n"),
            algorithm="ES256",
            headers={"kid": settings.apple_maps_key_id, "typ": "JWT"},
        )
    return settings.apple_maps_token


def thin(points: list, limit: int) -> list:
    if len(points) <= limit:
        return points
    step = (len(points) - 1) / (limit - 1)
    return [points[round(i * step)] for i in range(limit)]


def meters_between(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(radians, (*a, *b))
    h = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * 6_371_000 * asin(sqrt(h))


@dataclass
class _Run:
    athlete_id: int
    start: datetime
    distance_m: float
    moving_time_s: int
    path: list[tuple[float, float]]


def group_runs(runs: list[_Run]) -> dict[int, int]:
    """Runs that started at the same time and place were run together."""
    groups: dict[int, int] = {}
    for i, run in enumerate(runs):
        for j in range(i):
            other = runs[j]
            if (
                abs(run.start - other.start) <= TOGETHER_WINDOW
                and meters_between(run.path[0], other.path[0]) <= TOGETHER_METERS
            ):
                groups[i] = groups.get(j, j)
                break
        groups.setdefault(i, i)
    return groups


def build(team_id: uuid.UUID, rows: list[tuple], runs: list[_Run], now: datetime) -> MapOut:
    heat = [thin(r.path, max(2, HEAT_POINTS // max(1, len(runs)))) for r in runs]
    names = {
        athlete.id: (athlete.display_name, avatar_id, rig_id, athlete.avatar_url) for athlete, avatar_id, rig_id in rows
    }
    recent = [run for run in runs if run.start >= now - TRACK_WINDOW]
    groups = group_runs(recent)
    candidates: dict[int, list[tuple[_Run, int]]] = {}
    for index, run in enumerate(recent):
        candidates.setdefault(run.athlete_id, []).append((run, groups[index]))

    tracks = []
    for athlete_id, routes in candidates.items():
        routes.sort(key=lambda item: item[0].start, reverse=True)
        run, group = routes[0]
        name, avatar_id, rig_id, profile_url = names.get(athlete_id, ("Runner", None, None, None))
        route_data = [
            RouteOut(
                date=route.start.date(),
                distance_km=round(route.distance_m / 1000, 1),
                duration_s=route.moving_time_s,
                pace_seconds_km=round(route.moving_time_s * 1000 / route.distance_m)
                if route.distance_m >= 1000
                else None,
                group=route_group,
                path=thin(route.path, TRACK_POINTS),
            )
            for route, route_group in routes
        ]
        tracks.append(
            TrackOut(
                name=name,
                avatar_url=f"/api/v1/teams/{team_id}/avatars/{avatar_id}" if avatar_id else profile_url,
                avatar_is_generated=avatar_id is not None,
                rig_url=f"/api/v1/teams/{team_id}/rigs/{rig_id}" if rig_id else None,
                date=run.start.date(),
                distance_km=route_data[0].distance_km,
                duration_s=run.moving_time_s,
                pace_seconds_km=route_data[0].pace_seconds_km,
                group=group,
                path=route_data[0].path,
                routes=route_data,
            )
        )
    return MapOut(heat=heat, tracks=tracks, days=HISTORY.days, generated_at=now)


async def load(db: AsyncSession, team: Team) -> MapOut:
    cached = _cache.get(str(team.id))
    if cached and cached[0] > time.monotonic():
        return cached[1]

    rows = (
        await db.execute(
            select(Athlete, Avatar.id, AvatarRig.id)
            .join(Membership, Membership.athlete_id == Athlete.id)
            .outerjoin(Avatar, (Avatar.athlete_id == Athlete.id) & Avatar.image.is_not(None))
            .outerjoin(AvatarRig, AvatarRig.athlete_id == Athlete.id)
            .where(Membership.team_id == team.id, Membership.visible.is_(True))
        )
    ).all()

    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(Activity.athlete_id, Activity.start_date, Activity.distance_m, Activity.moving_time_s, Activity.summary_polyline)
        .where(
            Activity.athlete_id.in_([a.id for a, _, _ in rows]),
            Activity.start_date >= now - HISTORY,
            Activity.summary_polyline.is_not(None),
        )
        .order_by(Activity.start_date.desc())
        .limit(HEAT_RUNS)
    )
    runs = []
    for athlete_id, start, distance, moving, encoded in result:
        path = [(round(lat, 5), round(lng, 5)) for lat, lng in polyline.decode(encoded)]
        if len(path) >= 2:
            runs.append(_Run(athlete_id, start, distance, moving, path))

    view = build(team.id, rows, runs, now)
    _cache[str(team.id)] = (time.monotonic() + CACHE_TTL_S, view)
    return view


def clear() -> None:
    _cache.clear()
