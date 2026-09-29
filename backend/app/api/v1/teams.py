import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_athlete, get_optional_athlete
from app.database import get_db
from app.models import Athlete, Avatar, CardImage, Membership, Team, TeamCoachNote
from app.schemas.teams import MembershipUpdate, MyTeamOut, TeamCreate, TeamCreated, TeamOut, ViewerOut
from app.services import card_art, coach, rig, team_cache
from app.services.team_stats import load_team_view

router = APIRouter(prefix="/teams", tags=["teams"])


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


async def _viewer_out(db: AsyncSession, athlete: Athlete, membership: Membership) -> ViewerOut:
    avatar_id = await db.scalar(
        select(Avatar.id).where(Avatar.athlete_id == athlete.id, Avatar.image.is_not(None))
    )
    return ViewerOut(
        visible=membership.visible,
        goal_seconds=membership.goal_seconds,
        avatar_url="/api/v1/avatars/me" if avatar_id else athlete.avatar_url,
        has_avatar=avatar_id is not None,
        needs_reconnect="activity:read_all" not in (athlete.scope or "").split(","),
    )


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
    background: BackgroundTasks,
    viewer: Athlete | None = Depends(get_optional_athlete),
    db: AsyncSession = Depends(get_db),
):
    """Public: anyone with the link can view. Only visible members are listed."""
    team = await _get_team(db, team_id)
    view = await load_team_view(db, team)

    note = await db.get(TeamCoachNote, team.id)
    if coach.should_refresh(team.id, view, note):
        background.add_task(coach.refresh, team.id)
    if card_art.should_refresh(team.id, view):
        background.add_task(card_art.refresh, team.id)
    if rig.should_backfill(team.id):
        background.add_task(rig.backfill, team.id)

    viewer_out = None
    if viewer is not None:
        own = await db.get(Membership, (team.id, viewer.id))
        if own is not None:
            viewer_out = await _viewer_out(db, viewer, own)

    return TeamOut(
        name=team.name,
        race_name=team.race_name,
        race_date=team.race_date,
        race_distance_m=team.race_distance_m,
        members=[member for _, member in view.members],
        highlights=view.highlights,
        coach=coach.coach_view(view, note),
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
    team_cache.clear()
    return await _viewer_out(db, athlete, membership)


@router.delete("/{team_id}/me", status_code=status.HTTP_204_NO_CONTENT)
async def leave_team(
    team_id: uuid.UUID,
    athlete: Athlete = Depends(get_current_athlete),
    db: AsyncSession = Depends(get_db),
):
    await db.delete(await _get_membership(db, team_id, athlete))
    await db.commit()
    team_cache.clear()


@router.get("/{team_id}/cards/{image_id}")
async def card_image(team_id: uuid.UUID, image_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    image = await db.scalar(
        select(CardImage.image)
        .join(Membership, Membership.athlete_id == CardImage.athlete_id)
        .where(Membership.team_id == team_id, Membership.visible.is_(True), CardImage.id == image_id)
    )
    if image is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
    return Response(image, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})
