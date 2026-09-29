import asyncio
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import httpx

from app.config import settings
from app.models import TeamCoachNote
from app.schemas.teams import HighlightsOut, MemberOut
from app.services import coach
from app.services.team_stats import TeamView


def view() -> TeamView:
    def member(name: str, km: float) -> MemberOut:
        return MemberOut(
            name=name, avatar_url=None, avatar_is_generated=False, goal_seconds=None, km_7d=km,
            runs_7d=1 if km else 0, last_4_weeks_km=km, prediction_seconds=None,
            best_km_seconds=None, recent_runs=[],
        )

    highlights = HighlightsOut(window_days=7, total_km=0, total_runs=0, cards=[])
    facts = {
        1: {"km_last_4_weeks": 30, "runs_last_7_days": 1, "goal_finish_s": None, "predicted_finish_s": None},
        2: {"km_last_4_weeks": 0, "runs_last_7_days": 0, "goal_finish_s": None, "predicted_finish_s": None},
    }
    return TeamView(members=[(1, member("Simon G.", 30)), (2, member("Anna M.", 0))], highlights=highlights, facts=facts)


class CoachTests(unittest.TestCase):
    def test_fallback_notes_cover_every_runner(self):
        notes = coach.fallback_notes(view())
        self.assertEqual([n.name for n in notes], ["Simon G.", "Anna M."])
        self.assertIn("stealth mode", notes[1].text)

    def test_placeholders_render_current_names_and_drop_hidden_members(self):
        stored = coach.to_stored_notes(
            {"R1": "R1 thinks they are the Flash.", "R2": "R2 and R9 skipped leg day."},
            {"R1": 1, "R2": 2},
        )
        self.assertEqual(stored[0], {"athlete_id": 1, "text": "{athlete:1} thinks they are the Flash."})
        self.assertEqual(stored[1]["text"], "{athlete:2} and someone skipped leg day.")
        note = TeamCoachNote(generated_at=datetime.now(timezone.utc), notes=stored + [{"athlete_id": 99, "text": "gone"}])
        out = coach.coach_view(view(), note)
        self.assertEqual(out.source, "ai")
        self.assertEqual(out.notes[0].text, "Simon G. thinks they are the Flash.")
        self.assertEqual(len(out.notes), 2)

    def test_model_request_is_pseudonymous_and_parsed(self):
        sent = []

        def respond(request: httpx.Request) -> httpx.Response:
            sent.append(json.loads(request.content))
            body = {"notes": [{"runner": "R1", "text": " R1 never rests. "}, {"runner": "R7", "text": "ghost"}]}
            return httpx.Response(200, json={"output": [
                {"type": "reasoning"},
                {"type": "message", "content": [{"type": "output_text", "text": json.dumps(body)}]},
            ]})

        real_client = httpx.AsyncClient
        with patch.object(settings, "openai_api_key", "test"), patch.object(
            coach.httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(respond))
        ):
            texts = asyncio.run(coach.ask_model({"R1": {"km_last_7_days": 3}}))

        self.assertEqual(texts, {"R1": "R1 never rests."})
        self.assertEqual(json.loads(sent[0]["input"]), {"R1": {"km_last_7_days": 3}})
        self.assertEqual(sent[0]["text"]["format"]["type"], "json_schema")

    def test_refresh_gate(self):
        team_id = object()
        with patch.object(settings, "openai_api_key", ""):
            self.assertFalse(coach.should_refresh(team_id, view(), None))
        with patch.object(settings, "openai_api_key", "k"):
            self.assertTrue(coach.should_refresh(team_id, view(), None))
            fresh = TeamCoachNote(generated_at=datetime.now(timezone.utc), notes=[])
            self.assertFalse(coach.should_refresh(team_id, view(), fresh))


if __name__ == "__main__":
    unittest.main()
