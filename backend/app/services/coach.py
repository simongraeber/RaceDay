import asyncio
import json
import logging
import re
import time
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import or_, select

from app.config import settings
from app.database import async_session
from app.models import Membership, Team, TeamCoachNote
from app.schemas.teams import CoachNoteOut, CoachOut
from app.services import team_cache
from app.services.team_stats import TeamView, load_team_view

log = logging.getLogger(__name__)

REFRESH_AFTER = timedelta(hours=8)
RETRY_AFTER_S = 30 * 60
SCAN_INTERVAL_S = 15 * 60
MAX_CHARS = 140

INSTRUCTIONS = """You write the "Unfiltered Coach" card on a running team's race countdown page.
Write exactly one short roast per runner (max 110 characters) based ONLY on the JSON training stats.
Tone: cheeky, sarcastic, a little mean, like a grumpy coach who secretly cares.
Example: "R1 seems to think they are the Flash and don't need to train."
Data: *_km are kilometres, *_s are seconds (lower finish time = faster), null means unknown.
Pace facts are already formatted as m:ss /km. Treat them as pace, never as seconds per kilometre.
Rules:
- Refer to runners only by their id (R1, R2, ...). Use "they" or the id, never gendered pronouns.
- Give each runner one short roast with a specific focus; vary the focus across runners and refreshes.
- Pick from the available evidence: last run distance or pace, average weekly pace, fastest kilometre,
    weekly or monthly volume, consistency or rest, longest run, or race prediction vs goal.
- Do not default to distance or mileage. Do not repeat the same angle for every runner, and never
    invent missing stats. If a value is null, pick another angle.
- Only mock training behaviour: volume, consistency, rest days, pace, predicted time vs goal.
- Never mention body, weight, looks, health, injuries, age, gender, or anything not in the data.
- No profanity, slurs or threats. Write in English."""

SCHEMA = {
    "type": "object",
    "properties": {
        "notes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"runner": {"type": "string"}, "text": {"type": "string"}},
                "required": ["runner", "text"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["notes"],
    "additionalProperties": False,
}

_running: set[uuid.UUID] = set()
_last_attempt: dict[uuid.UUID, float] = {}


def fallback_notes(view: TeamView) -> list[CoachNoteOut]:
    """Rule-based roasts for when AI is off or hasn't run yet."""
    top_km = max((m.km_7d for _, m in view.members), default=0)
    notes = []
    for athlete_id, member in view.members:
        f = view.facts[athlete_id]
        if not f["km_last_4_weeks"]:
            text = f"{member.name} has entered stealth mode. Nobody has seen a single run."
        elif not f["runs_last_7_days"]:
            text = f"{member.name} apparently believes last week's runs still count."
        elif f["goal_finish_s"] and f["predicted_finish_s"] and f["predicted_finish_s"] > f["goal_finish_s"]:
            text = f"{member.name}'s goal time and current form are not on speaking terms."
        elif member.km_7d == top_km:
            text = f"{member.name} is training like the race is tomorrow. Save some for race day."
        else:
            text = f"{member.name} is doing fine. Suspiciously fine."
        notes.append(CoachNoteOut(name=member.name, text=text))
    return notes


def coach_view(view: TeamView, note: TeamCoachNote | None) -> CoachOut:
    names = {athlete_id: m.name for athlete_id, m in view.members}

    def render(text: str) -> str:
        return re.sub(r"\{athlete:(\d+)\}", lambda m: names.get(int(m[1]), "someone"), text)

    if note and {athlete_id for athlete_id, _ in view.members} <= {
        entry["athlete_id"] for entry in note.notes
    }:
        ai_notes = [
            CoachNoteOut(name=names[n["athlete_id"]], text=render(n["text"]))
            for n in note.notes
            if n["athlete_id"] in names
        ]
        if ai_notes:
            return CoachOut(source="ai", generated_at=note.generated_at, notes=ai_notes)
    return CoachOut(source="coach", generated_at=None, notes=fallback_notes(view))


def should_refresh(team_id: uuid.UUID, view: TeamView, note: TeamCoachNote | None) -> bool:
    if not settings.openai_api_key or not view.members or team_id in _running:
        return False
    if time.monotonic() - _last_attempt.get(team_id, -RETRY_AFTER_S) < RETRY_AFTER_S:
        return False
    covered = {entry["athlete_id"] for entry in note.notes} if note else set()
    missing_members = bool(note and note.notes) and not {athlete_id for athlete_id, _ in view.members} <= covered
    return missing_members or note is None or note.generated_at < datetime.now(timezone.utc) - REFRESH_AFTER


def _output_text(data: dict) -> str:
    for item in data.get("output", []):
        if item.get("type") == "message":
            for part in item.get("content", []):
                if part.get("type") == "output_text":
                    return part["text"]
    raise ValueError("No text in response")


async def ask_model(facts: dict[str, dict]) -> dict[str, str]:
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            json={
                "model": settings.openai_text_model,
                "instructions": INSTRUCTIONS,
                "input": json.dumps(facts),
                "max_output_tokens": 2000,
                "text": {"format": {"type": "json_schema", "name": "coach_notes", "strict": True, "schema": SCHEMA}},
            },
        )
    resp.raise_for_status()
    notes = json.loads(_output_text(resp.json()))["notes"]
    return {n["runner"]: n["text"].strip()[:MAX_CHARS] for n in notes if n["runner"] in facts and n["text"].strip()}


def to_stored_notes(texts: dict[str, str], aliases: dict[str, int]) -> list[dict]:
    """Swap pseudonyms for stable placeholders so renamed runners stay correct."""

    def placeholder(match: re.Match) -> str:
        return f"{{athlete:{aliases[match[0]]}}}" if match[0] in aliases else "someone"

    return [
        {"athlete_id": aliases[alias], "text": re.sub(r"\bR\d+\b", placeholder, text)}
        for alias, text in texts.items()
    ]


async def refresh(team_id: uuid.UUID) -> None:
    """Regenerate AI roasts. Only pseudonymous ids and numbers leave the server."""
    if team_id in _running:
        return
    _running.add(team_id)
    _last_attempt[team_id] = time.monotonic()
    try:
        async with async_session() as db:
            team = await db.get(Team, team_id)
            if team is None:
                return
            view = await load_team_view(db, team, use_cache=False)
            aliases = {f"R{i}": athlete_id for i, (athlete_id, _) in enumerate(view.members, start=1)}
            texts = await ask_model({alias: view.facts[athlete_id] for alias, athlete_id in aliases.items()})
            note = await db.get(TeamCoachNote, team_id) or TeamCoachNote(team_id=team_id)
            note.generated_at = datetime.now(timezone.utc)
            note.notes = to_stored_notes(texts, aliases)
            db.add(note)
            await db.commit()
            team_cache.clear()
    except (httpx.HTTPError, ValueError, KeyError, json.JSONDecodeError):
        log.warning("Coach notes for team %s failed", team_id, exc_info=True)
    finally:
        _running.discard(team_id)


async def refresh_due_teams() -> int:
    cutoff = datetime.now(timezone.utc) - REFRESH_AFTER
    async with async_session() as db:
        team_ids = await db.scalars(
            select(Team.id)
            .join(Membership, Membership.team_id == Team.id)
            .outerjoin(TeamCoachNote, TeamCoachNote.team_id == Team.id)
            .where(
                Membership.visible.is_(True),
                or_(TeamCoachNote.team_id.is_(None), TeamCoachNote.generated_at < cutoff),
            )
            .distinct()
        )
        due = list(team_ids)

    for team_id in due:
        await refresh(team_id)
    return len(due)


async def run_forever(interval_s: int = SCAN_INTERVAL_S) -> None:
    await asyncio.sleep(30)
    while True:
        try:
            if settings.openai_api_key:
                await refresh_due_teams()
        except Exception:
            log.exception("Coach refresh cycle failed")
        await asyncio.sleep(interval_s)
