import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Team
from app.schemas.maps import MapOut, MapTokenOut
from app.services import map_data

router = APIRouter(tags=["maps"])


@router.get("/maps/token", response_model=MapTokenOut)
async def maps_token():
    token = map_data.map_token()
    if not token:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Maps are not configured")
    return MapTokenOut(token=token)


@router.get("/teams/{team_id}/map", response_model=MapOut)
async def team_map(team_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Public like the team page: routes of visible members, already trimmed."""
    team = await db.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    return await map_data.load(db, team)
