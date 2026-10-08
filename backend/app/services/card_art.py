"""AI artwork for highlight cards: the runner's avatar, restyled once per card and cached."""

import base64
import hashlib
import logging
import time
import uuid
import asyncio
from io import BytesIO

import httpx
from PIL import Image
from sqlalchemy import and_, select

from app.config import settings
from app.database import async_session
from app.models import Athlete, Avatar, CardImage, Membership, Team, TeamCardImage
from app.services import avatar as images
from app.services import team_cache
from app.services.team_stats import TeamView, load_team_view

log = logging.getLogger(__name__)

GROUP_PROMPTS = {
    "together": "a lively, slightly chaotic team portrait at the starting line",
    "time": "celebrating a comically tall stack of stopwatches after a long week",
    "climbed": "building a goofy human pyramid on a mountain summit, one runner on top of another",
    "prs": "celebrating a new record together around an oversized trophy",
    "average": "taking a cheerful group stretch and water break after a run",
    "race_multiple": "measuring out a long race course together with a comically long ribbon",
    "missing": "searching together for a teammate who skipped this week's runs",
}
SOLO_PROMPTS = {
    "longest": "completely drenched in sweat after a very long run, exhausted but grinning, thumbs up",
    "endurance": "still running after hours, legs wobbling, eyes half closed, comically tired but refusing to stop",
    "fastest_km": "sprinting at full speed, leaning far forward, cartoon speed lines and little flames at the shoes",
    "pace": "leading a fast training run, focused expression and playful speed lines",
    "most_runs": "proudly juggling running shoes and a week full of training dates",
    "consistency": "running confidently through changing weather, with a tiny sun and raincloud nearby",
    "volume": "proudly carrying a huge stack of kilometre road signs, worn-out running shoes, triumphant pose",
    "climber": "running steeply uphill, leaning forward, hands pushing on the thighs, cheeks puffed out",
    "kudos": "grinning beneath a shower of colorful heart-shaped confetti",
    "steady_rhythm": "running with an even, relaxed stride beside a playful metronome",
    "weekend": (
        "running with wildly exaggerated knees-up strides, balancing a wobbling tower of pancakes "
        "on a plate in one hand and a sloshing takeaway coffee in the other, a pancake flipping "
        "into the air, delighted wide-eyed grin: squeezing a run in before weekend brunch"
    ),
    "quick_escape": (
        "sneaking away from a tiny stopwatch with comically exaggerated tiptoe running strides, "
        "finger to lips and a mischievous grin, shoelaces flying: a hilariously quick getaway"
    ),
    "comeback": (
        "bursting out of an oversized pair of fluffy slippers left tumbling behind, running shoes "
        "firmly on, doing an exuberant superhero-style running leap, a few cartoon dust puffs "
        "shaking off the shoulders, proudly surprised expression: back after a sofa-powered break"
    ),
    "latest": (
        "skidding to a triumphant halt after a run, dramatically presenting a tiny steaming "
        "running shoe on an oversized silver serving platter, the other running shoe still on, "
        "one socked foot lifted and an absurdly proud chef-like grin: a freshly served run"
    ),
}
PROMPTS = {
    **SOLO_PROMPTS,
    "missing": "lounging lazily on a small sofa in running clothes, snack in hand, running shoes left unused",
}
MAX_PER_RUN = 3
RETRY_AFTER_S = 30 * 60
GROUP_IMAGE_CONCURRENCY = 3

_running: set[uuid.UUID] = set()
_last_attempt: dict[uuid.UUID, float] = {}
_group_running: set[uuid.UUID] = set()
_group_last_attempt: dict[tuple[uuid.UUID, str], float] = {}


def group_member_signature(members: list[tuple[int, uuid.UUID | None]]) -> str:
    roster = ":".join(f"{athlete_id}:{avatar_id or '-'}" for athlete_id, avatar_id in sorted(members))
    return hashlib.sha256(roster.encode()).hexdigest()


def team_card_subjects(view: TeamView) -> dict[str, int | None]:
    member_ids = {member.name: athlete_id for athlete_id, member in view.members}
    subjects = {"together": None}
    for card in view.highlights.cards:
        if card.key in GROUP_PROMPTS:
            subjects[card.key] = None
            continue
        detail = card.detail.removeprefix("Most loved: ") if card.key == "kudos" else card.detail
        if card.key in SOLO_PROMPTS:
            subjects[card.key] = member_ids.get(detail)
    return subjects


def _card_signature(member_signature: str, subject_id: int | None) -> str:
    subject = f"athlete:{subject_id}" if subject_id is not None else "team"
    return hashlib.sha256(f"{member_signature}:{subject}".encode()).hexdigest()


def _request_signature(member_signature: str, subjects: dict[str, int | None]) -> str:
    values = ":".join(f"{key}:{subject_id}" for key, subject_id in sorted(subjects.items()))
    return hashlib.sha256(f"{member_signature}:{values}".encode()).hexdigest()


def should_refresh(team_id: uuid.UUID, view: TeamView) -> bool:
    if not settings.openai_api_key or team_id in _running:
        return False
    if not any(key in PROMPTS for _, key in view.art_wanted):
        return False
    return time.monotonic() - _last_attempt.get(team_id, -RETRY_AFTER_S) >= RETRY_AFTER_S


async def generate(avatar_png: bytes, prompt: str) -> bytes:
    full_prompt = (
        f"Redraw the character from the image: {prompt}. "
        "Keep the same character, face, hair, skin tone, outfit style and 3D cartoon look with slightly exaggerated head. "
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


def compose_team_reference(avatars: list[bytes]) -> bytes:
    canvas = Image.new("RGBA", (1024, 768), (0, 0, 0, 0))
    count = len(avatars)
    sprite_width = min(560, int(1024 / (1 + 0.66 * (count - 1))))
    step = int(sprite_width * 0.66)
    total_width = sprite_width + step * (count - 1)
    left = (canvas.width - total_width) // 2
    for index, raw in enumerate(avatars):
        with Image.open(BytesIO(raw)) as source:
            sprite = source.convert("RGBA")
            sprite.thumbnail((sprite_width, 690), Image.Resampling.LANCZOS)
        x = left + index * step
        y = canvas.height - sprite.height - (24 if index % 2 else 0)
        canvas.alpha_composite(sprite, (x, y))
    output = BytesIO()
    canvas.save(output, format="PNG", optimize=True)
    return output.getvalue()


def group_art_prompt(card_key: str, runner_count: int) -> str:
    scene = GROUP_PROMPTS[card_key]
    runners = f"all {runner_count} distinct cartoon runners" if runner_count > 1 else "the cartoon runner"
    return (
        f"Redraw {runners} from the supplied image as one playful team scene: {scene}. "
        "Keep every runner visible and recognizable. Preserve each character's face, hair, skin tone and running outfit. "
        "Full bodies, lively expressions, clean 3D cartoon look. Transparent background, no floor, scenery, text, logos, or extra people."
    )


async def generate_team_art(reference_png: bytes, runner_count: int, card_key: str) -> bytes:
    prompt = group_art_prompt(card_key, runner_count)
    async with httpx.AsyncClient(timeout=180) as client:
        response = await client.post(
            "https://api.openai.com/v1/images/edits",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            data={
                "model": "gpt-image-2.5-flare",
                "prompt": prompt,
                "size": "1024x1024",
                "quality": "medium",
                "output_format": "png",
                "background": "transparent",
            },
            files=[("image[]", ("team.png", reference_png, "image/png"))],
        )
    response.raise_for_status()
    encoded = response.json()["data"][0]["b64_json"]
    return images.to_avatar(base64.b64decode(encoded, validate=True))


async def generate_solo_team_art(avatar_png: bytes, card_key: str) -> bytes:
    return await generate(avatar_png, SOLO_PROMPTS[card_key])


async def group_art_status(
    db, team_id: uuid.UUID, card_subjects: dict[str, int | None]
) -> tuple[dict[str, str], str, dict[str, bool]]:
    rows = (
        await db.execute(
            select(Membership.athlete_id, Avatar.id)
            .join(Athlete, Athlete.id == Membership.athlete_id)
            .outerjoin(Avatar, and_(Avatar.athlete_id == Athlete.id, Avatar.image.is_not(None)))
            .where(Membership.team_id == team_id, Membership.visible.is_(True))
            .order_by(Membership.athlete_id)
        )
    ).all()
    signature = group_member_signature([(athlete_id, avatar_id) for athlete_id, avatar_id in rows])
    avatar_ids = {athlete_id for athlete_id, avatar_id in rows if avatar_id is not None}
    group_ready = bool(rows) and len(avatar_ids) == len(rows)
    ready = {
        key: group_ready if key in GROUP_PROMPTS else subject_id in avatar_ids
        for key, subject_id in card_subjects.items()
    }
    signatures = {key: _card_signature(signature, subject_id) for key, subject_id in card_subjects.items()}
    records = (
        await db.execute(
            select(TeamCardImage.card_key, TeamCardImage.id, TeamCardImage.member_signature).where(
                TeamCardImage.team_id == team_id, TeamCardImage.card_key.in_(list(card_subjects))
            )
        )
    ).all()
    urls = {
        key: f"/api/v1/teams/{team_id}/group-art/{image_id}"
        for key, image_id, stored_signature in records
        if ready.get(key) and stored_signature == signatures[key]
    }
    return urls, signature, ready


def should_refresh_group(
    team_id: uuid.UUID,
    signature: str,
    ready: dict[str, bool],
    image_urls: dict[str, str],
    card_subjects: dict[str, int | None],
) -> bool:
    missing = any(
        ready.get(key) and key not in image_urls and (key in GROUP_PROMPTS or key in SOLO_PROMPTS)
        for key in card_subjects
    )
    if not settings.openai_api_key or not missing or team_id in _group_running:
        return False
    attempt = (team_id, _request_signature(signature, card_subjects))
    return time.monotonic() - _group_last_attempt.get(attempt, -RETRY_AFTER_S) >= RETRY_AFTER_S


async def refresh_group(team_id: uuid.UUID, card_subjects: dict[str, int | None]) -> None:
    if team_id in _group_running:
        return
    _group_running.add(team_id)
    try:
        async with async_session() as db:
            rows = (
                await db.execute(
                    select(Membership.athlete_id, Avatar.id, Avatar.image)
                    .join(Athlete, Athlete.id == Membership.athlete_id)
                    .outerjoin(Avatar, and_(Avatar.athlete_id == Athlete.id, Avatar.image.is_not(None)))
                    .where(Membership.team_id == team_id, Membership.visible.is_(True))
                    .order_by(Membership.athlete_id)
                )
            ).all()
            if not rows:
                return
            card_subjects = {
                key: subject_id
                for key, subject_id in card_subjects.items()
                if key in GROUP_PROMPTS or (key in SOLO_PROMPTS and subject_id is not None)
            }
            member_signature = group_member_signature([(athlete_id, avatar_id) for athlete_id, avatar_id, _ in rows])
            attempt = (team_id, _request_signature(member_signature, card_subjects))
            _group_last_attempt[attempt] = time.monotonic()
            group_ready = all(avatar_id is not None for _, avatar_id, _ in rows)
            avatar_images = {athlete_id: image for athlete_id, avatar_id, image in rows if avatar_id is not None}
            card_ready = {
                key: group_ready if key in GROUP_PROMPTS else subject_id in avatar_images
                for key, subject_id in card_subjects.items()
            }
            records = (
                await db.execute(
                    select(TeamCardImage.card_key, TeamCardImage.member_signature).where(
                        TeamCardImage.team_id == team_id, TeamCardImage.card_key.in_(list(card_subjects))
                    )
                )
            ).all()
            expected = {key: _card_signature(member_signature, subject_id) for key, subject_id in card_subjects.items()}
            covered = {key for key, stored_signature in records if stored_signature == expected.get(key)}
            missing = [key for key in card_subjects if card_ready.get(key) and key not in covered]
            if not missing:
                return
            reference = compose_team_reference([image for _, avatar_id, image in rows if avatar_id is not None and image]) if any(
                key in GROUP_PROMPTS for key in missing
            ) else None
            semaphore = asyncio.Semaphore(GROUP_IMAGE_CONCURRENCY)

            async def generate_card(card_key: str) -> tuple[str, bytes | None]:
                async with semaphore:
                    try:
                        subject_id = card_subjects[card_key]
                        if card_key in GROUP_PROMPTS:
                            if reference is None:
                                return card_key, None
                            image = await generate_team_art(reference, len(rows), card_key)
                        else:
                            image = await generate_solo_team_art(avatar_images[subject_id], card_key)
                        return card_key, image
                    except (httpx.HTTPError, images.GenerationFailed, ValueError, KeyError, IndexError, OSError):
                        log.warning("Team artwork %s for %s failed", card_key, team_id, exc_info=True)
                        return card_key, None

            generated = await asyncio.gather(*(generate_card(key) for key in missing))
            current_members = (
                await db.execute(
                    select(Membership.athlete_id, Avatar.id)
                    .join(Athlete, Athlete.id == Membership.athlete_id)
                    .outerjoin(Avatar, and_(Avatar.athlete_id == Athlete.id, Avatar.image.is_not(None)))
                    .where(Membership.team_id == team_id, Membership.visible.is_(True))
                    .order_by(Membership.athlete_id)
                )
            ).all()
            if member_signature != group_member_signature(
                [(athlete_id, avatar_id) for athlete_id, avatar_id in current_members]
            ):
                return
            team = await db.get(Team, team_id)
            if team is None:
                return
            latest_view = await load_team_view(db, team, use_cache=False)
            latest_subjects = team_card_subjects(latest_view)
            if any(latest_subjects.get(key) != subject_id for key, subject_id in card_subjects.items()):
                return
            for card_key, image in generated:
                if image is None:
                    continue
                record = await db.get(TeamCardImage, (team_id, card_key))
                if record is None:
                    record = TeamCardImage(team_id=team_id, card_key=card_key)
                record.id = uuid.uuid4()
                record.member_signature = expected[card_key]
                record.image = image
                db.add(record)
            await db.commit()
            team_cache.clear()
    except (httpx.HTTPError, images.GenerationFailed, ValueError, KeyError, IndexError, OSError):
        log.warning("Team artwork for %s failed", team_id, exc_info=True)
    finally:
        _group_running.discard(team_id)


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
