import logging
import math
import time
from datetime import datetime, timezone

import polyline
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models import Activity, Athlete
from app.services import strava

log = logging.getLogger(__name__)

RUN_TYPES = {"Run", "TrailRun", "VirtualRun"}
BACKFILL_DAYS = 365
TRIM_METERS = 200


def _haversine(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6_371_000 * math.asin(math.sqrt(h))


def trim_polyline(encoded: str | None, meters: float = TRIM_METERS) -> str | None:
    """Drop the first and last `meters` of a route."""
    if not encoded:
        return None
    points = polyline.decode(encoded)
    if len(points) < 2:
        return None
    cumulative = [0.0]
    for a, b in zip(points, points[1:]):
        cumulative.append(cumulative[-1] + _haversine(a, b))
    total = cumulative[-1]
    kept = [p for p, d in zip(points, cumulative) if meters <= d <= total - meters]
    return polyline.encode(kept) if len(kept) >= 2 else None


async def upsert_activity(db: AsyncSession, athlete_id: int, activity_id: int, data: dict | None) -> None:
    """Store a public run, or remove it if it's gone, private, or not a run."""
    if (
        data is None
        or data.get("sport_type") not in RUN_TYPES
        or data.get("private")
        or data.get("athlete", {}).get("id") != athlete_id
    ):
        await db.execute(
            delete(Activity).where(Activity.id == activity_id, Activity.athlete_id == athlete_id)
        )
        return

    values = {
        "id": activity_id,
        "athlete_id": athlete_id,
        "name": data.get("name") or "",
        "sport_type": data["sport_type"],
        "start_date": datetime.fromisoformat(data["start_date"].replace("Z", "+00:00")),
        "distance_m": data.get("distance") or 0,
        "moving_time_s": data.get("moving_time") or 0,
        "elapsed_time_s": data.get("elapsed_time") or 0,
        "elevation_gain_m": data.get("total_elevation_gain") or 0,
        "summary_polyline": trim_polyline((data.get("map") or {}).get("summary_polyline")),
    }
    stmt = insert(Activity).values(**values)
    await db.execute(
        stmt.on_conflict_do_update(
            index_elements=[Activity.id],
            set_={k: stmt.excluded[k] for k in values if k not in ("id", "athlete_id")},
        )
    )


async def backfill(athlete_id: int) -> None:
    async with async_session() as db:
        athlete = await db.get(Athlete, athlete_id)
        if athlete is None:
            return
        after = int(time.time()) - BACKFILL_DAYS * 86_400
        try:
            token = await strava.get_access_token(db, athlete)
            page = 1
            while True:
                items = await strava.list_activities(token, after=after, page=page)
                for item in items:
                    await upsert_activity(db, athlete_id, item["id"], item)
                await db.commit()
                if len(items) < strava.PER_PAGE:
                    break
                page += 1
            athlete.last_synced_at = datetime.now(timezone.utc)
            await db.commit()
        except strava.StravaError:
            log.warning("Backfill for athlete %s stopped", athlete_id, exc_info=True)


async def _is_revoked(db: AsyncSession, athlete: Athlete) -> bool:
    try:
        token = await strava.get_access_token(db, athlete)
        await strava.get_athlete(token)
    except strava.Unauthorized:
        return True
    except strava.StravaError:
        return False
    return False


async def handle_event(event: dict) -> None:
    """Process a Strava webhook event.

    Webhook payloads are unsigned, so every change is re-verified against the Strava API
    instead of trusting the payload.
    """
    owner_id = event.get("owner_id")
    object_id = event.get("object_id")
    if not isinstance(owner_id, int) or not isinstance(object_id, int):
        return

    async with async_session() as db:
        athlete = await db.get(Athlete, owner_id)
        if athlete is None:
            return

        try:
            if event.get("object_type") == "athlete":
                if (event.get("updates") or {}).get("authorized") == "false" and await _is_revoked(db, athlete):
                    await db.delete(athlete)
                    await db.commit()
                return

            if event.get("object_type") == "activity":
                token = await strava.get_access_token(db, athlete)
                try:
                    data = await strava.get_activity(token, object_id)
                except strava.Unauthorized:
                    # Activity is no longer visible to us (e.g. switched to "Only Me")
                    data = None
                await upsert_activity(db, athlete.id, object_id, data)
                await db.commit()
        except strava.StravaError:
            log.warning("Webhook event for athlete %s failed", owner_id, exc_info=True)
