"""AI artwork for highlight cards: the runner's avatar, restyled once per card and cached."""

import base64
import logging
import time
import uuid

import httpx
from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.models import Avatar, CardImage, Team
from app.services import avatar as images
from app.services import team_cache
from app.services.team_stats import TeamView, load_team_view

log = logging.getLogger(__name__)

PROMPTS = {
    "longest": "completely drenched in sweat after a very long run, exhausted but grinning, thumbs up",
    "endurance": "still running after hours, legs wobbling, eyes half closed, comically tired but refusing to stop",
    "fastest_km": "sprinting at full speed, leaning far forward, cartoon speed lines and little flames at the shoes",
    "climber": "running steeply uphill, leaning forward, hands pushing on the thighs, cheeks puffed out",
    "volume": "proudly carrying a huge stack of kilometre road signs, worn-out running shoes, triumphant pose",
    "missing": "lounging lazily on a small sofa in running clothes, snack in hand, running shoes left unused",
}
MAX_PER_RUN = 3
RETRY_AFTER_S = 30 * 60

_running: set[uuid.UUID] = set()
_last_attempt: dict[uuid.UUID, float] = {}


def should_refresh(team_id: uuid.UUID, view: TeamView) -> bool:
    if not settings.openai_api_key or team_id in _running:
        return False
    if not any(key in PROMPTS for _, key in view.art_wanted):
        return False
    return time.monotonic() - _last_attempt.get(team_id, -RETRY_AFTER_S) >= RETRY_AFTER_S


async def generate(avatar_png: bytes, prompt: str) -> bytes:
    full_prompt = (
        f"Redraw the character from the image: {prompt}. "
        "Keep the same character, face, hair, skin tone, outfit style and 3D cartoon look. "
        "Full body, head to toe, centered with a small margin. "
        "Cut out on a fully transparent background: no scenery, no landscape, no floor, no ground, "
        "no shadow plate, no text, no logos, no other people."
    )
    async with httpx.AsyncClient(timeout=180) as client:
        response = await client.post(
            "https://api.openai.com/v1/images/edits",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            data={
                "model": "gpt-image-2.5-flare",
                "prompt": full_prompt,
                "size": "1024x1536",
                "quality": "medium",
                "output_format": "png",
                "background": "transparent",
            },
            files=[("image[]", ("runner.png", avatar_png, "image/png"))],
        )
    response.raise_for_status()
    encoded = response.json()["data"][0]["b64_json"]
    return images.to_avatar(base64.b64decode(encoded, validate=True))


async def refresh(team_id: uuid.UUID) -> None:
    """Fill in missing card artwork for runners who have a generated avatar."""
    if team_id in _running:
        return
    _running.add(team_id)
    _last_attempt[team_id] = time.monotonic()
    stored = 0
    try:
        async with async_session() as db:
            team = await db.get(Team, team_id)
            if team is None:
                return
            view = await load_team_view(db, team, use_cache=False)
            for athlete_id, key in view.art_wanted:
                if key not in PROMPTS or stored >= MAX_PER_RUN:
                    continue
                if await db.get(CardImage, (athlete_id, key)):
                    continue
                source = await db.scalar(
                    select(Avatar.image).where(Avatar.athlete_id == athlete_id, Avatar.image.is_not(None))
                )
                if source is None:
                    continue
                try:
                    image = await generate(source, PROMPTS[key])
                except (httpx.HTTPError, images.GenerationFailed, ValueError, KeyError):
                    log.warning("Card art %s for athlete %s failed", key, athlete_id, exc_info=True)
                    continue
                db.add(CardImage(athlete_id=athlete_id, card_key=key, image=image))
                await db.commit()
                stored += 1
    finally:
        _running.discard(team_id)
        if stored:
            team_cache.clear()
