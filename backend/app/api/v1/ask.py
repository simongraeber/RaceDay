import time
import uuid
from collections import defaultdict

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_athlete
from app.api.v1.avatars import require_site_origin
from app.config import settings
from app.database import get_db
from app.models import Athlete, Membership, Team
from app.services import agent

router = APIRouter(tags=["ask"])

RATE_LIMIT = 5
RATE_WINDOW_S = 3600
_asked: dict[int, list[float]] = defaultdict(list)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=500)


class AskResponse(BaseModel):
    components: list[dict]
    remaining: int


def _remaining(athlete_id: int) -> int:
    cutoff = time.time() - RATE_WINDOW_S
    _asked[athlete_id] = [t for t in _asked[athlete_id] if t > cutoff]
    return RATE_LIMIT - len(_asked[athlete_id])


@router.post("/teams/{team_id}/ask", response_model=AskResponse)
async def ask(
    team_id: uuid.UUID,
    body: AskRequest,
    request: Request,
    athlete: Athlete = Depends(get_current_athlete),
    db: AsyncSession = Depends(get_db),
):
    """Members only. Answers from a read-only, pseudonymised copy of the team's runs."""
    require_site_origin(request)
    team = await db.get(Team, team_id)
    if team is None or await db.get(Membership, (team_id, athlete.id)) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not a member")
    if not settings.openai_api_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="AI is not configured")
    remaining = _remaining(athlete.id)
    if remaining <= 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"You've used your {RATE_LIMIT} questions this hour. Go for a run and try again later.",
        )
    _asked[athlete.id].append(time.time())

    sandbox = await agent.load_sandbox(db, team, athlete.id)
    try:
        components = await agent.answer(sandbox, body.question)
    except agent.AgentError as exc:
        components = [{"type": "callout", "emoji": "🤔", "text": str(exc)}]
    except (httpx.HTTPError, ValueError, KeyError):
        components = [{"type": "callout", "emoji": "⚠️", "text": "The AI is out of breath. Please try again."}]
    finally:
        sandbox.db.close()
    return AskResponse(components=components, remaining=remaining - 1)
