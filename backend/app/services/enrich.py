import asyncio
import logging
import math
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from app.database import async_session
from app.models import Activity, ActivityDetail, Athlete
from app.services import strava, team_cache
from app.services.heart_rate import usable_heart_rate
from app.services.sync import TRIM_METERS, can_share_route

log = logging.getLogger(__name__)

BATCH = 15
INTERVAL_S = 5 * 60
MAX_STREAM_POINTS = 600
EFFORT_FIELDS = ("name", "distance", "elapsed_time", "moving_time", "pr_rank")
SPLIT_FIELDS = ("split", "distance", "elapsed_time", "moving_time", "elevation_difference")


def trim_streams(raw: dict | None, meters: float = TRIM_METERS, max_points: int = MAX_STREAM_POINTS) -> dict | None:
    """Cut the first/last `meters` like summary polylines, then downsample."""
    if not raw:
        return None
    distance = (raw.get("distance") or {}).get("data")
    if not distance:
        return None
    total = distance[-1]
    keep = [i for i, d in enumerate(distance) if meters <= d <= total - meters]
    if len(keep) < 2:
        return None
    keep = keep[:: max(1, math.ceil(len(keep) / max_points))]
    streams = {}
    for key in ("latlng", "altitude", "distance", "time"):
        values = (raw.get(key) or {}).get("data")
        if values and len(values) == len(distance):
            streams[key] = [values[i] for i in keep]
    return streams


def detail_values(detail: dict | None, streams: dict | None) -> dict:
    detail = detail or {}
    average = detail.get("average_heartrate")
    peak = detail.get("max_heartrate")
    valid_hr = usable_heart_rate(average, peak)
    if (average is not None or peak is not None) and not valid_hr:
        log.warning("Ignoring incomplete or invalid activity heart-rate summary")
    return {
        "best_efforts": [{k: e.get(k) for k in EFFORT_FIELDS} for e in detail.get("best_efforts") or []] or None,
        "splits": [{k: s.get(k) for k in SPLIT_FIELDS} for s in detail.get("splits_metric") or []] or None,
        "kudos_count": detail.get("kudos_count") or 0,
        "pr_count": detail.get("pr_count") or 0,
        "average_heartrate": average if valid_hr else None,
        "max_heartrate": peak if valid_hr else None,
        "heart_rate_checked": True,
        "streams": trim_streams(streams),
    }


async def enrich_batch(limit: int = BATCH) -> int:
    """Fetch details + streams for the newest activities that don't have them yet."""
    stored = 0
    async with async_session() as db:
        pending = (
            await db.execute(
                select(Activity.id, Activity.athlete_id)
                .outerjoin(ActivityDetail, ActivityDetail.activity_id == Activity.id)
                .where(or_(
                    ActivityDetail.activity_id.is_(None),
                    and_(
                        ActivityDetail.heart_rate_checked.is_(False),
                        Activity.start_date >= datetime.now(timezone.utc) - timedelta(days=84),
                    ),
                ))
                .order_by(Activity.start_date.desc())
                .limit(limit)
            )
        ).all()
        tokens: dict[int, str] = {}
        for activity_id, athlete_id in pending:
            if not strava.read_budget_ok():
                break
            try:
                if athlete_id not in tokens:
                    tokens[athlete_id] = await strava.get_access_token(db, await db.get(Athlete, athlete_id))
                try:
                    detail = await strava.get_activity(tokens[athlete_id], activity_id)
                    # Respect the same route-sharing policy as summary polylines.
                    streams = (
                        await strava.get_activity_streams(tokens[athlete_id], activity_id)
                        if detail and can_share_route(detail)
                        else None
                    )
                except strava.Unauthorized:
                    detail = streams = None
            except strava.RateLimited:
                break
            except strava.StravaError:
                log.warning("Enriching activity %s failed", activity_id, exc_info=True)
                continue
            try:
                values = detail_values(detail, streams)
                stmt = insert(ActivityDetail).values(activity_id=activity_id, **values)
                await db.execute(stmt.on_conflict_do_update(
                    index_elements=[ActivityDetail.activity_id],
                    set_={key: stmt.excluded[key] for key in (
                        "average_heartrate", "max_heartrate", "heart_rate_checked",
                    )},
                ))
                await db.commit()
                stored += 1
            except IntegrityError:
                # Activity was deleted by a webhook while we were fetching it
                await db.rollback()
    if stored:
        team_cache.clear()
    return stored


async def run_forever(interval_s: int = INTERVAL_S) -> None:
    await asyncio.sleep(30)
    while True:
        try:
            await enrich_batch()
        except Exception:
            log.exception("Activity enrichment cycle failed")
        await asyncio.sleep(interval_s)
