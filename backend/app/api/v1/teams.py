import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_athlete, get_optional_athlete
from app.database import get_db
from app.models import Activity, Athlete, Membership, Team

router = APIRouter(prefix="/teams", tags=["teams"])


class TeamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    race_name: str = Field(min_length=1, max_length=120)
    race_date: date
    race_distance_m: int = Field(gt=0, le=500_000)


class TeamCreated(BaseModel):
    id: uuid.UUID


class MemberOut(BaseModel):
    name: str
    avatar_url: str | None
    goal_seconds: int | None
    runs: int
    total_km: float
    last_4_weeks_km: float
    longest_km: float


class ViewerOut(BaseModel):
    visible: bool
    goal_seconds: int | None


class TeamOut(BaseModel):
    name: str
    race_name: str
    race_date: date
    race_distance_m: int
    members: list[MemberOut]
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
            select(Athlete, Membership)
            .join(Membership, Membership.athlete_id == Athlete.id)
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
            .where(Activity.athlete_id.in_([a.id for a, _ in rows]))
            .group_by(Activity.athlete_id)
        )
    }

    members = []
    for athlete, membership in rows:
        s = stats.get(athlete.id)
        members.append(
            MemberOut(
                name=athlete.display_name,
                avatar_url=athlete.avatar_url,
                goal_seconds=membership.goal_seconds,
                runs=s.runs if s else 0,
                total_km=round(s.total / 1000, 1) if s else 0,
                last_4_weeks_km=round(s.recent / 1000, 1) if s else 0,
                longest_km=round(s.longest / 1000, 1) if s else 0,
            )
        )

    viewer_out = None
    if viewer is not None:
        own = await db.get(Membership, (team.id, viewer.id))
        if own is not None:
            viewer_out = ViewerOut(visible=own.visible, goal_seconds=own.goal_seconds)

    return TeamOut(
        name=team.name,
        race_name=team.race_name,
        race_date=team.race_date,
        race_distance_m=team.race_distance_m,
        members=members,
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
    return ViewerOut(visible=membership.visible, goal_seconds=membership.goal_seconds)


@router.delete("/{team_id}/me", status_code=status.HTTP_204_NO_CONTENT)
async def leave_team(
    team_id: uuid.UUID,
    athlete: Athlete = Depends(get_current_athlete),
    db: AsyncSession = Depends(get_db),
):
    await db.delete(await _get_membership(db, team_id, athlete))
    await db.commit()
