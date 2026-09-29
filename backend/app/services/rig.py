"""Cut-up character sheet: the avatar redrawn as separate body parts for the running rig."""

import base64
import logging
import time
import uuid
from io import BytesIO

import httpx
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.models import Avatar, AvatarRig, Membership
from app.services import team_cache
from app.services.avatar import REFERENCE_IMAGE, GenerationFailed

log = logging.getLogger(__name__)

TEMPLATE = REFERENCE_IMAGE.parent / "ReferenceDecomposed.png"
# The frontend rig slices the sheet by fixed pixel boxes, so the size is part of the contract
SHEET_SIZE = (682, 1024)
BACKFILL_PER_RUN = 3
RETRY_AFTER_S = 10 * 60

_running: set[uuid.UUID] = set()
_last_attempt: dict[uuid.UUID, float] = {}

PROMPT = (
    "The FIRST image is a character sheet: one cartoon runner already cut into separate body parts "
    "(head, torso, upper arm, two lower arms, upper leg, lower leg) laid out on a transparent background. "
    "Redraw that sheet for the character shown in the SECOND image. "
    "CRITICAL: keep the layout identical. Every part must stay in exactly the same position, at exactly the "
    "same scale, rotation and orientation as in the FIRST image, with the same silhouette and the same joint "
    "ends, so the parts still fit together. Do not move, resize, rotate, mirror, add or remove parts. "
    "Only restyle them: head, hair, face and accessories of the SECOND character, its skin tone, its running "
    "clothes and shoes, and a matching torso shape. Keep the same 3D cartoon look and lighting. "
    "Parts must not touch or overlap. Fully transparent background, no shadows, no text, no extra drawings."
)


def to_sheet(raw: bytes) -> bytes:
    """Validate transparency and scale the generation down to the exact sheet size."""
    try:
        with Image.open(BytesIO(raw)) as image:
            image = image.convert("RGBA")
            alpha = image.getchannel("A")
            corners = [(0, 0), (image.width - 1, 0), (0, image.height - 1), (image.width - 1, image.height - 1)]
            if (
                any(alpha.getpixel(point) > 16 for point in corners)
                or sum(alpha.histogram()[:128]) < image.width * image.height * 0.4
                or alpha.getextrema()[1] < 128
            ):
                raise GenerationFailed("The character sheet had no transparent background")
            output = BytesIO()
            image.resize(SHEET_SIZE, Image.LANCZOS).save(output, format="PNG", optimize=True)
            return output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise GenerationFailed("Character sheet generation returned an invalid image") from exc


async def generate(avatar_png: bytes) -> bytes:
    async with httpx.AsyncClient(timeout=240) as client:
        response = await client.post(
            "https://api.openai.com/v1/images/edits",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            data={
                "model": "gpt-image-2.5-flare",
                "prompt": PROMPT,
                "size": "1024x1536",
                "quality": "high",
                "output_format": "png",
                "background": "transparent",
            },
            files=[
                ("image[]", ("parts.png", TEMPLATE.read_bytes(), "image/png")),
                ("image[]", ("runner.png", avatar_png, "image/png")),
            ],
        )
    response.raise_for_status()
    return to_sheet(base64.b64decode(response.json()["data"][0]["b64_json"], validate=True))


async def refresh(athlete_id: int) -> None:
    """Rebuild the character sheet for an athlete's current avatar."""
    if not settings.openai_api_key:
        return
    try:
        async with async_session() as db:
            avatar = await db.scalar(
                select(Avatar).where(Avatar.athlete_id == athlete_id, Avatar.image.is_not(None))
            )
            if avatar is None:
                return
            sheet = await generate(avatar.image)
            rig = await db.get(AvatarRig, athlete_id) or AvatarRig(athlete_id=athlete_id)
            rig.id = uuid.uuid4()
            rig.image = sheet
            db.add(rig)
            await db.commit()
            team_cache.clear()
    except (httpx.HTTPError, GenerationFailed, ValueError, KeyError):
        log.warning("Character sheet for athlete %s failed", athlete_id, exc_info=True)


def should_backfill(team_id: uuid.UUID) -> bool:
    if not settings.openai_api_key or team_id in _running:
        return False
    return time.monotonic() - _last_attempt.get(team_id, -RETRY_AFTER_S) >= RETRY_AFTER_S


async def backfill(team_id: uuid.UUID) -> None:
    """Draw sheets for team members whose avatar predates the rig."""
    if team_id in _running:
        return
    _running.add(team_id)
    _last_attempt[team_id] = time.monotonic()
    try:
        async with async_session() as db:
            pending = (
                await db.execute(
                    select(Avatar.athlete_id)
                    .join(Membership, Membership.athlete_id == Avatar.athlete_id)
                    .outerjoin(AvatarRig, AvatarRig.athlete_id == Avatar.athlete_id)
                    .where(
                        Membership.team_id == team_id,
                        Membership.visible.is_(True),
                        Avatar.image.is_not(None),
                        AvatarRig.athlete_id.is_(None),
                    )
                    .limit(BACKFILL_PER_RUN)
                )
            ).scalars().all()
        for athlete_id in pending:
            await refresh(athlete_id)
    finally:
        _running.discard(team_id)
