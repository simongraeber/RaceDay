import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_athlete, get_optional_athlete
from app.database import get_db
from app.models import Activity, Athlete, Avatar, Membership, Team

router = APIRouter(prefix="/teams", tags=["teams"])


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


class MemberOut(BaseModel):
    name: str
    avatar_url: str | None
    avatar_is_generated: bool
    goal_seconds: int | None
    runs: int
    total_km: float
    last_4_weeks_km: float
    longest_km: float
    week_km: float
    week_runs: int
    prediction_seconds: int | None
    recent_runs: list["RunOut"]


class RunOut(BaseModel):
    date: date
    distance_km: float
    pace_seconds_km: int | None


class HighlightsOut(BaseModel):
    week_start: date
    week_km: float
    week_time_s: int
    week_runs: int
    longest_run_km: float
    longest_runner: str | None
    fastest_pace_seconds_km: int | None
    fastest_runner: str | None
    most_runs: int
    most_runs_runner: str | None


class ViewerOut(BaseModel):
    visible: bool
    goal_seconds: int | None
    avatar_url: str | None
    has_avatar: bool


class TeamOut(BaseModel):
    name: str
    race_name: str
    race_date: date
    race_distance_m: int
    members: list[MemberOut]
    highlights: HighlightsOut
    viewer: ViewerOut | None


class MembershipUpdate(BaseModel):
    visible: bool | None = None
    goal_seconds: int | None = Field(default=None, gt=0, le=24 * 3600)


async def _get_team(db: AsyncSession, team_id: uuid.UUID) -> Team:
    team = await db.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    return team


async def _get_membership(db: AsyncSession, team_id: uuid.UUID, athlete: Athlete) -> Membership:
    membership = await db.get(Membership, (team_id, athlete.id))
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not a member")
    return membership


def pace_seconds_km(run: Activity) -> int | None:
    if run.distance_m < 1000 or run.moving_time_s <= 0:
        return None
    return round(run.moving_time_s * 1000 / run.distance_m)


def predict_finish(runs: list[Activity], distance_m: int, since: datetime) -> int | None:
    candidates = [
        round(run.moving_time_s * (distance_m / run.distance_m) ** 1.06)
        for run in runs
        if run.start_date >= since
        and run.distance_m >= min(5000, distance_m / 3)
        and run.distance_m <= distance_m * 1.5
        and distance_m / run.distance_m <= 4
        and run.moving_time_s > 0
    ]
    return min(candidates) if candidates else None


@router.post("", response_model=TeamCreated, status_code=status.HTTP_201_CREATED)
async def create_team(
    body: TeamCreate,
    athlete: Athlete = Depends(get_current_athlete),
    db: AsyncSession = Depends(get_db),
):
    team = Team(**body.model_dump(), created_by=athlete.id)
    db.add(team)
    await db.flush()
    db.add(Membership(team_id=team.id, athlete_id=athlete.id))
    await db.commit()
    return TeamCreated(id=team.id)


@router.get("/mine", response_model=list[MyTeamOut])
async def my_teams(
    athlete: Athlete = Depends(get_current_athlete),
    db: AsyncSession = Depends(get_db),
):
    teams = await db.scalars(
        select(Team)
        .join(Membership, Membership.team_id == Team.id)
        .where(Membership.athlete_id == athlete.id)
        .order_by(Team.race_date, Team.name)
    )
    return [MyTeamOut.model_validate(team, from_attributes=True) for team in teams]


@router.get("/{team_id}", response_model=TeamOut)
async def get_team(
    team_id: uuid.UUID,
    viewer: Athlete | None = Depends(get_optional_athlete),
    db: AsyncSession = Depends(get_db),
):
    """Public: anyone with the link can view. Only visible members are listed."""
    team = await _get_team(db, team_id)

    rows = (
        await db.execute(
            select(Athlete, Membership, Avatar.id)
            .join(Membership, Membership.athlete_id == Athlete.id)
            .outerjoin(Avatar, (Avatar.athlete_id == Athlete.id) & Avatar.image.is_not(None))
            .where(Membership.team_id == team.id, Membership.visible.is_(True))
            .order_by(Membership.joined_at)
        )
    ).all()

    four_weeks_ago = datetime.now(timezone.utc) - timedelta(days=28)
    stats = {
        row.athlete_id: row
        for row in await db.execute(
            select(
                Activity.athlete_id,
                func.count(Activity.id).label("runs"),
                func.coalesce(func.sum(Activity.distance_m), 0).label("total"),
                func.coalesce(func.max(Activity.distance_m), 0).label("longest"),
                func.coalesce(
                    func.sum(Activity.distance_m).filter(Activity.start_date >= four_weeks_ago), 0
                ).label("recent"),
            )
            .where(Activity.athlete_id.in_([a.id for a, _, _ in rows]))
            .group_by(Activity.athlete_id)
        )
    }

    now = datetime.now(timezone.utc)
    week_start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=now.weekday())
    recent = await db.scalars(
        select(Activity)
        .where(
            Activity.athlete_id.in_([a.id for a, _, _ in rows]),
            Activity.start_date >= now - timedelta(days=365),
        )
        .order_by(Activity.start_date.desc())
    )
    runs_by_athlete: dict[int, list[Activity]] = defaultdict(list)
    for run in recent:
        runs_by_athlete[run.athlete_id].append(run)

    members = []
    longest = (0.0, None)
    quickest = (None, None)
    most_runs = (0, None)
    week_meters = 0.0
    week_seconds = 0
    week_runs_total = 0
    for athlete, membership, avatar_id in rows:
        s = stats.get(athlete.id)
        runs = runs_by_athlete[athlete.id]
        this_week = [run for run in runs if run.start_date >= week_start]
        meters = sum(run.distance_m for run in this_week)
        week_meters += meters
        week_seconds += sum(run.moving_time_s for run in this_week)
        week_runs_total += len(this_week)
        for run in this_week:
            if run.distance_m > longest[0]:
                longest = (run.distance_m, athlete.display_name)
            pace = pace_seconds_km(run)
            if pace is not None and (quickest[0] is None or pace < quickest[0]):
                quickest = (pace, athlete.display_name)
        if len(this_week) > most_runs[0]:
            most_runs = (len(this_week), athlete.display_name)
        members.append(
            MemberOut(
                name=athlete.display_name,
                avatar_url=(f"/api/v1/teams/{team.id}/avatars/{avatar_id}" if avatar_id else athlete.avatar_url),
                avatar_is_generated=avatar_id is not None,
                goal_seconds=membership.goal_seconds,
                runs=s.runs if s else 0,
                total_km=round(s.total / 1000, 1) if s else 0,
                last_4_weeks_km=round(s.recent / 1000, 1) if s else 0,
                longest_km=round(s.longest / 1000, 1) if s else 0,
                week_km=round(meters / 1000, 1),
                week_runs=len(this_week),
                prediction_seconds=(
                    predict_finish(runs, team.race_distance_m, now - timedelta(days=84))
                    if team.race_date >= now.date() else None
                ),
                recent_runs=[
                    RunOut(
                        date=run.start_date.date(),
                        distance_km=round(run.distance_m / 1000, 1),
                        pace_seconds_km=pace_seconds_km(run),
                    ) for run in runs[:3]
                ],
            )
        )

    viewer_out = None
    if viewer is not None:
        own = await db.get(Membership, (team.id, viewer.id))
        if own is not None:
            avatar_id = await db.scalar(
                select(Avatar.id).where(Avatar.athlete_id == viewer.id, Avatar.image.is_not(None))
            )
            viewer_out = ViewerOut(
                visible=own.visible,
                goal_seconds=own.goal_seconds,
                avatar_url="/api/v1/avatars/me" if avatar_id else viewer.avatar_url,
                has_avatar=avatar_id is not None,
            )

    return TeamOut(
        name=team.name,
        race_name=team.race_name,
        race_date=team.race_date,
        race_distance_m=team.race_distance_m,
        members=members,
        highlights=HighlightsOut(
            week_start=week_start.date(),
            week_km=round(week_meters / 1000, 1),
            week_time_s=week_seconds,
            week_runs=week_runs_total,
            longest_run_km=round(longest[0] / 1000, 1),
            longest_runner=longest[1],
            fastest_pace_seconds_km=quickest[0],
            fastest_runner=quickest[1],
            most_runs=most_runs[0],
            most_runs_runner=most_runs[1],
        ),
        viewer=viewer_out,
    )


@router.patch("/{team_id}/me", response_model=ViewerOut)
async def update_membership(
    team_id: uuid.UUID,
    body: MembershipUpdate,
    athlete: Athlete = Depends(get_current_athlete),
    db: AsyncSession = Depends(get_db),
):
    membership = await _get_membership(db, team_id, athlete)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(membership, field, value)
    await db.commit()
    avatar_id = await db.scalar(
        select(Avatar.id).where(Avatar.athlete_id == athlete.id, Avatar.image.is_not(None))
    )
    return ViewerOut(
        visible=membership.visible,
        goal_seconds=membership.goal_seconds,
        avatar_url="/api/v1/avatars/me" if avatar_id else athlete.avatar_url,
        has_avatar=avatar_id is not None,
    )


@router.delete("/{team_id}/me", status_code=status.HTTP_204_NO_CONTENT)
async def leave_team(
    team_id: uuid.UUID,
    athlete: Athlete = Depends(get_current_athlete),
    db: AsyncSession = Depends(get_db),
):
    await db.delete(await _get_membership(db, team_id, athlete))
    await db.commit()
