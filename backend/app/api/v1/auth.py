import logging
import uuid
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, HTTPException, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_athlete
from app.config import settings
from app.database import get_db
from app.models import Athlete, Avatar, Membership, Team
from app.security import (
    SESSION_COOKIE,
    STATE_COOKIE,
    create_oauth_state,
    create_session_token,
    read_oauth_state,
)
from app.services import strava, sync, team_cache

log = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

_STATE_COOKIE_PATH = "/api/v1/auth"


def _redirect(path: str) -> RedirectResponse:
    return RedirectResponse(f"{settings.app_base_url}{path}", status_code=status.HTTP_302_FOUND)


@router.get("/strava/login")
async def strava_login(
    intent: Literal["create", "join"],
    team: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
):
    if intent == "join" and (team is None or await db.get(Team, team) is None):
        raise HTTPException(status_code=404, detail="Team not found")

    state, nonce = create_oauth_state(intent, str(team) if team else None)
    resp = RedirectResponse(strava.authorize_url(state), status_code=status.HTTP_302_FOUND)
    resp.set_cookie(
        STATE_COOKIE,
        nonce,
        max_age=600,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path=_STATE_COOKIE_PATH,
    )
    return resp


@router.get("/strava/callback")
async def strava_callback(
    background: BackgroundTasks,
    state: str = "",
    code: str | None = None,
    scope: str = "",
    error: str | None = None,
    nonce: str | None = Cookie(None, alias=STATE_COOKIE),
    db: AsyncSession = Depends(get_db),
):
    payload = read_oauth_state(state, nonce or "")
    if payload is None:
        return _redirect("/?error=login_failed")

    team_id = payload.get("team")
    back = f"/t/{team_id}" if team_id else "/"
    if error or not code:
        return _redirect(f"{back}?error=access_denied")
    if "activity:read_all" not in scope.split(","):
        return _redirect(f"{back}?error=missing_scope")

    try:
        tokens = await strava.exchange_code(code)
    except strava.StravaError:
        log.warning("Strava code exchange failed", exc_info=True)
        return _redirect(f"{back}?error=login_failed")

    profile = tokens["athlete"]
    athlete = await db.get(Athlete, profile["id"])
    if athlete is None:
        athlete = Athlete(id=profile["id"])
        db.add(athlete)
    athlete.firstname = profile.get("firstname") or ""
    athlete.lastname = profile.get("lastname") or ""
    avatar = profile.get("profile_medium") or ""
    athlete.avatar_url = avatar if avatar.startswith("https://") else None
    scope_upgraded = "activity:read_all" not in (athlete.scope or "").split(",")
    athlete.scope = scope
    strava.store_tokens(athlete, tokens)

    target = "/new"
    if payload["intent"] == "create":
        existing_team = await db.scalar(
            select(Membership.team_id).where(Membership.athlete_id == athlete.id).limit(1)
        )
        if existing_team is not None:
            target = "/teams"
    if payload["intent"] == "join":
        team = await db.get(Team, uuid.UUID(team_id))
        if team is None:
            target = "/"
        else:
            if await db.get(Membership, (team.id, athlete.id)) is None:
                db.add(Membership(team_id=team.id, athlete_id=athlete.id))
                target = f"/t/{team.id}?joined=1"
            else:
                target = f"/t/{team.id}"
    await db.commit()
    team_cache.clear()

    # A scope upgrade makes previously invisible runs readable, so re-import the history
    if athlete.last_synced_at is None or scope_upgraded:
        background.add_task(sync.backfill, athlete.id)

    resp = _redirect(target)
    resp.set_cookie(
        SESSION_COOKIE,
        create_session_token(athlete.id),
        max_age=settings.session_expire_days * 86_400,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
    )
    resp.delete_cookie(STATE_COOKIE, path=_STATE_COOKIE_PATH)
    return resp


class MeOut(BaseModel):
    name: str
    avatar_url: str | None
    teams: list[uuid.UUID]


@router.get("/me", response_model=MeOut)
async def me(
    athlete: Athlete = Depends(get_current_athlete),
    db: AsyncSession = Depends(get_db),
):
    team_ids = await db.scalars(
        select(Membership.team_id).where(Membership.athlete_id == athlete.id)
    )
    avatar_id = await db.scalar(
        select(Avatar.id).where(Avatar.athlete_id == athlete.id, Avatar.image.is_not(None))
    )
    return MeOut(
        name=athlete.display_name,
        avatar_url="/api/v1/avatars/me" if avatar_id else athlete.avatar_url,
        teams=list(team_ids),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    response: Response,
    athlete: Athlete = Depends(get_current_athlete),
    db: AsyncSession = Depends(get_db),
):
    """Revoke Strava access and delete all stored data for this athlete."""
    try:
        await strava.revoke(athlete)
    except strava.StravaError:
        log.warning("Strava revoke failed for athlete %s", athlete.id, exc_info=True)
    await db.delete(athlete)
    await db.commit()
    team_cache.clear()
    response.delete_cookie(SESSION_COOKIE, path="/")
