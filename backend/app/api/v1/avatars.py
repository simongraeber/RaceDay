import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_athlete
from app.config import settings
from app.database import get_db
from app.models import Athlete, Avatar, Membership
from app.services import avatar as images
from app.services import team_cache

router = APIRouter(tags=["avatars"])


@router.get("/avatars/style")
async def style_reference():
    return Response(
        images.REFERENCE_IMAGE.read_bytes(),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


class AvatarOut(BaseModel):
    url: str


def require_site_origin(request: Request) -> None:
    if request.headers.get("origin") != settings.app_base_url.rstrip("/"):
        raise HTTPException(status_code=403, detail="Invalid origin")


@router.post("/avatars/me", response_model=AvatarOut)
async def create_avatar(
    request: Request,
    photo: UploadFile = File(...),
    description: str = Form("", max_length=300),
    athlete: Athlete = Depends(get_current_athlete),
    db: AsyncSession = Depends(get_db),
):
    require_site_origin(request)
    if not settings.openai_api_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Avatar generation is unavailable")
    if not await db.scalar(select(Membership.athlete_id).where(Membership.athlete_id == athlete.id).limit(1)):
        raise HTTPException(status_code=403, detail="Join a team first")

    existing = await db.get(Avatar, athlete.id)
    if existing and existing.created_at and existing.created_at > datetime.now(timezone.utc) - timedelta(minutes=5):
        raise HTTPException(status_code=429, detail="Please wait before generating another avatar")

    raw = await photo.read(images.MAX_UPLOAD_BYTES + 1)
    await photo.close()
    if len(raw) > images.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Image must be under 5 MB")
    try:
        normalized = images.normalize_image(raw)
        generated = await images.generate_avatar(normalized, description)
    except images.InvalidImage as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except images.GenerationFailed as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    avatar = existing or Avatar(athlete_id=athlete.id)
    avatar.id = uuid.uuid4()
    avatar.image = generated
    avatar.created_at = datetime.now(timezone.utc)
    db.add(avatar)
    await db.commit()
    team_cache.clear()
    return AvatarOut(url="/api/v1/avatars/me")


@router.get("/avatars/me")
async def own_avatar(athlete: Athlete = Depends(get_current_athlete), db: AsyncSession = Depends(get_db)):
    avatar = await db.get(Avatar, athlete.id)
    if not avatar or avatar.image is None:
        raise HTTPException(status_code=404, detail="No avatar")
    media_type = "image/png" if avatar.image.startswith(b"\x89PNG") else "image/jpeg"
    return Response(avatar.image, media_type=media_type, headers={"Cache-Control": "no-store"})


@router.delete("/avatars/me", status_code=204)
async def delete_avatar(request: Request, athlete: Athlete = Depends(get_current_athlete), db: AsyncSession = Depends(get_db)):
    require_site_origin(request)
    avatar = await db.get(Avatar, athlete.id)
    if avatar:
        avatar.image = None
        await db.commit()
        team_cache.clear()


@router.get("/teams/{team_id}/avatars/{avatar_id}")
async def team_avatar(team_id: uuid.UUID, avatar_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    image = await db.scalar(
        select(Avatar.image)
        .join(Membership, Membership.athlete_id == Avatar.athlete_id)
        .where(
            Membership.team_id == team_id,
            Membership.visible.is_(True),
            Avatar.id == avatar_id,
            Avatar.image.is_not(None),
        )
    )
    if image is None:
        raise HTTPException(status_code=404, detail="Avatar not found")
    media_type = "image/png" if image.startswith(b"\x89PNG") else "image/jpeg"
    return Response(image, media_type=media_type, headers={"Cache-Control": "no-store"})