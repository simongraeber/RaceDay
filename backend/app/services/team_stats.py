from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Activity, ActivityDetail, Athlete, Avatar, Membership, Team
from app.schemas.teams import HighlightsOut, MemberOut, RunOut
from app.services import team_cache

PREDICTION_WINDOW = timedelta(days=84)
HISTORY_WINDOW = timedelta(days=365)
RIEGEL_EXPONENT = 1.06


@dataclass
class Run:
    start: datetime
    distance_m: float
    moving_time_s: int
    elevation_m: float
    kudos: int
    best_efforts: list[dict] = field(default_factory=list)


@dataclass
class TeamView:
    """Public team stats plus the athlete ids needed internally (never serialized)."""

    members: list[tuple[int, MemberOut]]
    highlights: HighlightsOut
    facts: dict[int, dict]


def pace_seconds_km(distance_m: float, seconds: int) -> int | None:
    if distance_m < 1000 or seconds <= 0:
        return None
    return round(seconds * 1000 / distance_m)


def best_km(run: Run) -> int | None:
    times = [e["elapsed_time"] for e in run.best_efforts if abs((e.get("distance") or 0) - 1000) < 1 and e.get("elapsed_time")]
    return min(times) if times else None


def predict_finish(efforts: list[tuple[float, int]], distance_m: int) -> int | None:
    """Riegel projection from the best qualifying effort (5 km+ and within 4x the race distance)."""
    candidates = [
        round(seconds * (distance_m / meters) ** RIEGEL_EXPONENT)
        for meters, seconds in efforts
        if seconds > 0
        and meters >= min(5000, distance_m / 3)
        and meters <= distance_m * 1.5
        and distance_m / meters <= 4
    ]
    return min(candidates) if candidates else None


def race_efforts(runs: list[Run], since: datetime) -> list[tuple[float, int]]:
    efforts = []
    for run in runs:
        if run.start < since:
            continue
        efforts.append((run.distance_m, run.moving_time_s))
        efforts.extend((e["distance"], e["elapsed_time"]) for e in run.best_efforts if e.get("distance") and e.get("elapsed_time"))
    return efforts


def _min_or_none(values):
    values = [v for v in values if v is not None]
    return min(values) if values else None


def summarize(team: Team, rows: list[tuple], runs_by_athlete: dict[int, list[Run]], now: datetime) -> TeamView:
    week_start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=now.weekday())
    race_ahead = team.race_date >= now.date()
    members: list[tuple[int, MemberOut]] = []
    facts: dict[int, dict] = {}
    week_runs_all: list[tuple[str, Run]] = []
    most_runs = (0, None)

    for athlete, membership, avatar_id in rows:
        runs = runs_by_athlete.get(athlete.id, [])
        week = [r for r in runs if r.start >= week_start]
        week_runs_all.extend((athlete.display_name, r) for r in week)
        if len(week) > most_runs[0]:
            most_runs = (len(week), athlete.display_name)
        recent_window = [r for r in runs if r.start >= now - PREDICTION_WINDOW]
        prediction = predict_finish(race_efforts(runs, now - PREDICTION_WINDOW), team.race_distance_m) if race_ahead else None
        member = MemberOut(
            name=athlete.display_name,
            avatar_url=f"/api/v1/teams/{team.id}/avatars/{avatar_id}" if avatar_id else athlete.avatar_url,
            avatar_is_generated=avatar_id is not None,
            goal_seconds=membership.goal_seconds,
            week_km=round(sum(r.distance_m for r in week) / 1000, 1),
            week_runs=len(week),
            last_4_weeks_km=round(sum(r.distance_m for r in runs if r.start >= now - timedelta(days=28)) / 1000, 1),
            prediction_seconds=prediction,
            best_km_seconds=_min_or_none(best_km(r) for r in recent_window),
            recent_runs=[
                RunOut(
                    date=r.start.date(),
                    distance_km=round(r.distance_m / 1000, 1),
                    pace_seconds_km=pace_seconds_km(r.distance_m, r.moving_time_s),
                )
                for r in runs[:3]
            ],
        )
        members.append((athlete.id, member))
        facts[athlete.id] = {
            "km_this_week": member.week_km,
            "runs_this_week": member.week_runs,
            "km_last_4_weeks": member.last_4_weeks_km,
            "longest_run_last_12_weeks_km": round(max((r.distance_m for r in recent_window), default=0) / 1000, 1),
            "days_since_last_run": (now - runs[0].start).days if runs else None,
            "predicted_finish_s": prediction,
            "goal_finish_s": membership.goal_seconds,
            "best_1km_last_12_weeks_s": member.best_km_seconds,
        }

    longest = max(week_runs_all, key=lambda item: item[1].distance_m, default=(None, None))
    paced = [(name, pace_seconds_km(r.distance_m, r.moving_time_s)) for name, r in week_runs_all]
    quickest = min(((n, p) for n, p in paced if p is not None), key=lambda item: item[1], default=(None, None))
    kms = [(name, best_km(r)) for name, r in week_runs_all]
    fastest_km = min(((n, s) for n, s in kms if s is not None), key=lambda item: item[1], default=(None, None))

    highlights = HighlightsOut(
        week_start=week_start.date(),
        week_km=round(sum(r.distance_m for _, r in week_runs_all) / 1000, 1),
        week_time_s=sum(r.moving_time_s for _, r in week_runs_all),
        week_runs=len(week_runs_all),
        week_elevation_m=round(sum(r.elevation_m for _, r in week_runs_all)),
        week_kudos=sum(r.kudos for _, r in week_runs_all),
        longest_run_km=round(longest[1].distance_m / 1000, 1) if longest[1] else 0,
        longest_runner=longest[0],
        fastest_km_seconds=fastest_km[1],
        fastest_km_runner=fastest_km[0],
        fastest_pace_seconds_km=quickest[1],
        fastest_runner=quickest[0],
        most_runs=most_runs[0],
        most_runs_runner=most_runs[1],
    )
    return TeamView(members=members, highlights=highlights, facts=facts)


async def load_team_view(db: AsyncSession, team: Team, use_cache: bool = True) -> TeamView:
    """Aggregate visible members' stored runs. Never calls Strava."""
    cached = team_cache.get(team.id) if use_cache else None
    if cached is not None:
        return cached

    rows = (
        await db.execute(
            select(Athlete, Membership, Avatar.id)
            .join(Membership, Membership.athlete_id == Athlete.id)
            .outerjoin(Avatar, (Avatar.athlete_id == Athlete.id) & Avatar.image.is_not(None))
            .where(Membership.team_id == team.id, Membership.visible.is_(True))
            .order_by(Membership.joined_at)
        )
    ).all()

    now = datetime.now(timezone.utc)
    runs_by_athlete: dict[int, list[Run]] = defaultdict(list)
    result = await db.execute(
        select(
            Activity.athlete_id,
            Activity.start_date,
            Activity.distance_m,
            Activity.moving_time_s,
            Activity.elevation_gain_m,
            ActivityDetail.kudos_count,
            ActivityDetail.best_efforts,
        )
        .outerjoin(ActivityDetail, ActivityDetail.activity_id == Activity.id)
        .where(
            Activity.athlete_id.in_([a.id for a, _, _ in rows]),
            Activity.start_date >= now - HISTORY_WINDOW,
        )
        .order_by(Activity.start_date.desc())
    )
    for athlete_id, start, distance, moving, elevation, kudos, efforts in result:
        runs_by_athlete[athlete_id].append(Run(start, distance, moving, elevation, kudos or 0, efforts or []))

    view = summarize(team, rows, runs_by_athlete, now)
    team_cache.put(team.id, view)
    return view
