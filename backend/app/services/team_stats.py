from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Activity, ActivityDetail, Athlete, Avatar, Membership, Team
from app.schemas.teams import HighlightsOut, MemberOut, RunOut, StatCardOut
from app.services import team_cache

WINDOW = timedelta(days=7)
PREDICTION_WINDOW = timedelta(days=84)
HISTORY_WINDOW = timedelta(days=365)
RIEGEL_EXPONENT = 1.06
EIFFEL_TOWER_M = 330


@dataclass
class Run:
    start: datetime
    distance_m: float
    moving_time_s: int
    elevation_m: float
    kudos: int
    best_efforts: list[dict] = field(default_factory=list)
    pr_count: int = 0


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


def fmt_duration(seconds: int) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _min_or_none(values):
    values = [v for v in values if v is not None]
    return min(values) if values else None


def stat_cards(window_runs: dict[str, list[Run]], race_distance_m: int) -> list[StatCardOut]:
    """Every card that has data for the window; the frontend shows a random selection."""
    runs = [(name, r) for name, rs in window_runs.items() for r in rs]
    if not runs:
        return []
    per_runner = {name: rs for name, rs in window_runs.items() if rs}
    cards: list[StatCardOut] = []

    def add(key, icon, label, value, detail):
        cards.append(StatCardOut(key=key, icon=icon, label=label, value=value, detail=detail))

    add("time", "clock", "Time on feet", fmt_duration(sum(r.moving_time_s for _, r in runs)), "All runners combined")

    name, run = max(runs, key=lambda item: item[1].distance_m)
    add("longest", "footprints", "Longest run", f"{run.distance_m / 1000:.1f} km", name)

    name, run = max(runs, key=lambda item: item[1].moving_time_s)
    add("endurance", "hourglass", "Longest time out", fmt_duration(run.moving_time_s), name)

    kms = [(n, best_km(r)) for n, r in runs if best_km(r)]
    if kms:
        name, seconds = min(kms, key=lambda item: item[1])
        add("fastest_km", "zap", "Fastest kilometre", fmt_duration(seconds), name)

    paced = [(n, pace_seconds_km(r.distance_m, r.moving_time_s)) for n, r in runs if r.distance_m >= 3000]
    paced = [(n, p) for n, p in paced if p]
    if paced:
        name, pace = min(paced, key=lambda item: item[1])
        add("pace", "gauge", "Quickest run pace", f"{fmt_duration(pace)} /km", name)

    name, rs = max(per_runner.items(), key=lambda item: len(item[1]))
    add("most_runs", "trophy", "Most outings", f"{len(rs)} runs", name)

    name, rs = max(per_runner.items(), key=lambda item: len({r.start.date() for r in item[1]}))
    add("consistency", "calendar", "Most consistent", f"{len({r.start.date() for r in rs})} of 7 days", name)

    name, rs = max(per_runner.items(), key=lambda item: sum(r.distance_m for r in item[1]))
    add("volume", "flame", "Biggest mileage", f"{sum(r.distance_m for r in rs) / 1000:.1f} km", name)

    climbed = sum(r.elevation_m for _, r in runs)
    if climbed >= 1:
        add("climbed", "mountain", "Climbed together", f"{round(climbed)} m", f"{climbed / EIFFEL_TOWER_M:.1f}\u00d7 the Eiffel Tower")
        name, rs = max(per_runner.items(), key=lambda item: sum(r.elevation_m for r in item[1]))
        add("climber", "mountain-snow", "Mountain goat", f"{round(sum(r.elevation_m for r in rs))} m", name)

    kudos = sum(r.kudos for _, r in runs)
    if kudos:
        name, rs = max(per_runner.items(), key=lambda item: sum(r.kudos for r in item[1]))
        add("kudos", "heart", "Kudos collected", str(kudos), f"Most loved: {name}")

    prs = sum(r.pr_count for _, r in runs)
    if prs:
        add("prs", "medal", "Personal records", str(prs), "Set on Strava")

    total_m = sum(r.distance_m for _, r in runs)
    add("average", "ruler", "Average run", f"{total_m / len(runs) / 1000:.1f} km", f"Across {len(runs)} runs")
    add("race_multiple", "flag", "Race distances covered", f"{total_m / race_distance_m:.1f}\u00d7", "Team total vs. race distance")

    missing = [n for n, rs in window_runs.items() if not rs]
    if missing and len(missing) < len(window_runs):
        add("missing", "ghost", "Missing in action", str(len(missing)), ", ".join(missing[:3]))
    return cards


def summarize(team: Team, rows: list[tuple], runs_by_athlete: dict[int, list[Run]], now: datetime) -> TeamView:
    window_start = now - WINDOW
    race_ahead = team.race_date >= now.date()
    members: list[tuple[int, MemberOut]] = []
    facts: dict[int, dict] = {}
    window_runs: dict[str, list[Run]] = {}

    for athlete, membership, avatar_id in rows:
        runs = runs_by_athlete.get(athlete.id, [])
        recent = [r for r in runs if r.start >= window_start]
        window_runs[athlete.display_name] = recent
        twelve_weeks = [r for r in runs if r.start >= now - PREDICTION_WINDOW]
        prediction = predict_finish(race_efforts(runs, now - PREDICTION_WINDOW), team.race_distance_m) if race_ahead else None
        member = MemberOut(
            name=athlete.display_name,
            avatar_url=f"/api/v1/teams/{team.id}/avatars/{avatar_id}" if avatar_id else athlete.avatar_url,
            avatar_is_generated=avatar_id is not None,
            goal_seconds=membership.goal_seconds,
            km_7d=round(sum(r.distance_m for r in recent) / 1000, 1),
            runs_7d=len(recent),
            last_4_weeks_km=round(sum(r.distance_m for r in runs if r.start >= now - timedelta(days=28)) / 1000, 1),
            prediction_seconds=prediction,
            best_km_seconds=_min_or_none(best_km(r) for r in twelve_weeks),
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
            "km_last_7_days": member.km_7d,
            "runs_last_7_days": member.runs_7d,
            "km_last_4_weeks": member.last_4_weeks_km,
            "longest_run_last_12_weeks_km": round(max((r.distance_m for r in twelve_weeks), default=0) / 1000, 1),
            "days_since_last_run": (now - runs[0].start).days if runs else None,
            "predicted_finish_s": prediction,
            "goal_finish_s": membership.goal_seconds,
            "best_1km_last_12_weeks_s": member.best_km_seconds,
        }

    all_recent = [r for rs in window_runs.values() for r in rs]
    highlights = HighlightsOut(
        window_days=WINDOW.days,
        total_km=round(sum(r.distance_m for r in all_recent) / 1000, 1),
        total_runs=len(all_recent),
        cards=stat_cards(window_runs, team.race_distance_m),
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
            ActivityDetail.pr_count,
        )
        .outerjoin(ActivityDetail, ActivityDetail.activity_id == Activity.id)
        .where(
            Activity.athlete_id.in_([a.id for a, _, _ in rows]),
            Activity.start_date >= now - HISTORY_WINDOW,
        )
        .order_by(Activity.start_date.desc())
    )
    for athlete_id, start, distance, moving, elevation, kudos, efforts, prs in result:
        runs_by_athlete[athlete_id].append(Run(start, distance, moving, elevation, kudos or 0, efforts or [], prs or 0))

    view = summarize(team, rows, runs_by_athlete, now)
    team_cache.put(team.id, view)
    return view
