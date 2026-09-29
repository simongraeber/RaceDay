from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Athlete
from app.security import SESSION_COOKIE, read_session_token


async def get_optional_athlete(
    session: str | None = Cookie(None, alias=SESSION_COOKIE),
    db: AsyncSession = Depends(get_db),
) -> Athlete | None:
    athlete_id = read_session_token(session) if session else None
    if athlete_id is None:
        return None
    return await db.get(Athlete, athlete_id)


async def get_current_athlete(
    athlete: Athlete | None = Depends(get_optional_athlete),
) -> Athlete:
    if athlete is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not logged in")
    return athlete
