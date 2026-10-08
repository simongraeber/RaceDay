import asyncio
import base64
import unittest
import uuid
from datetime import date
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import BackgroundTasks, HTTPException
from PIL import Image
from starlette.requests import Request

from app.api.v1.avatars import require_site_origin
from app.api.v1 import teams
from app.config import settings
from app.schemas.teams import CoachOut, HighlightsOut, MemberOut, StatCardCandidateOut, StatCardOut
from app.services import avatar
from app.services import card_art
from app.services.team_stats import TeamView


def image_bytes(format: str = "PNG") -> bytes:
    output = BytesIO()
    Image.new("RGB", (64, 64), "#e85d2a").save(output, format=format)
    return output.getvalue()


def transparent_avatar() -> bytes:
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    image.paste((232, 93, 42, 255), (16, 12, 48, 56))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


class AvatarTests(unittest.TestCase):
    def test_team_response_keeps_tied_candidates_art_separate_and_cache_unchanged(self):
        team_id = uuid.uuid4()
        card = StatCardOut(
            key="consistency", icon="calendar", label="Most consistent", value="3 of 7 days", detail="Simon",
            image_url="/simon-solo",
            candidates=[
                StatCardCandidateOut(name="Simon", detail="Simon", image_url="/simon-solo"),
                StatCardCandidateOut(name="Theo", detail="Theo", image_url="/theo-solo"),
            ],
        )
        view = TeamView(members=[], highlights=HighlightsOut(window_days=7, total_km=10, total_runs=6, cards=[card]), facts={})
        team = SimpleNamespace(id=team_id, name="Crew", race_name="Half",
                               race_date=date(2027, 4, 4), race_distance_m=21097)
        database = SimpleNamespace(get=AsyncMock(return_value=None))
        with patch.object(teams, "_get_team", AsyncMock(return_value=team)), patch.object(
            teams, "load_team_view", AsyncMock(return_value=view)
        ), patch.object(teams.coach, "should_refresh", return_value=False), patch.object(
            teams.coach, "coach_view", return_value=CoachOut(source="coach", generated_at=None, notes=[])
        ), patch.object(teams.card_art, "should_refresh", return_value=False), patch.object(
            teams.card_art, "group_art_status",
            AsyncMock(return_value=({"consistency": "/simon-group"}, "signature", {})),
        ), patch.object(teams.card_art, "should_refresh_group", return_value=False), patch.object(
            teams.rig, "should_backfill", return_value=False
        ):
            response = asyncio.run(teams.get_team(team_id, BackgroundTasks(), None, database))
        candidates = response.highlights.cards[0].candidates
        self.assertEqual([c.image_url for c in candidates], ["/simon-group", "/theo-solo"])
        self.assertEqual([c.image_url for c in card.candidates], ["/simon-solo", "/theo-solo"])

    def test_team_card_art_endpoint_serves_a_current_subject_image(self):
        team_id = uuid.uuid4()
        image_id = uuid.uuid4()
        image = b"\x89PNG image bytes"
        database = SimpleNamespace(scalar=AsyncMock(return_value=image))
        url = f"/api/v1/teams/{team_id}/group-art/{image_id}"

        with patch.object(teams, "_get_team", AsyncMock(return_value=object())), patch.object(
            teams, "load_team_view", AsyncMock(return_value=object())
        ), patch.object(teams.card_art, "team_card_subjects", return_value={"pace": 1}), patch.object(
            teams.card_art, "group_art_status", AsyncMock(return_value=({"pace": url}, "signature", {"pace": True}))
        ):
            response = asyncio.run(teams.group_art_image(team_id, image_id, database))

        self.assertEqual(response.body, image)
        self.assertEqual(response.media_type, "image/png")

    def test_team_reference_composites_every_runner(self):
        composite = card_art.compose_team_reference([transparent_avatar(), transparent_avatar(), transparent_avatar()])
        with Image.open(BytesIO(composite)) as result:
            self.assertEqual(result.mode, "RGBA")
            self.assertEqual(result.size, (1024, 768))
            self.assertGreater(sum(result.getchannel("A").histogram()[1:]), 0)
        self.assertNotEqual(
            card_art.group_member_signature([(1, None), (2, None)]),
            card_art.group_member_signature([(1, None), (2, None), (3, None)]),
        )
        self.assertNotEqual(card_art.group_art_prompt("climbed", 3), card_art.group_art_prompt("prs", 3))
        signature = card_art.group_member_signature([(1, None), (2, None)])
        self.assertNotEqual(
            card_art._request_signature(signature, {"pace": 1}),
            card_art._request_signature(signature, {"pace": 2}),
        )

    def test_team_and_solo_cards_select_the_right_art_subject(self):
        def member(name: str) -> MemberOut:
            return MemberOut(
                name=name,
                avatar_url=None,
                avatar_is_generated=True,
                goal_seconds=None,
                km_7d=1,
                runs_7d=1,
                last_4_weeks_km=1,
                prediction_seconds=None,
                best_km_seconds=None,
                recent_runs=[],
            )

        cards = [
            StatCardOut(key="time", icon="clock", label="Time on feet", value="1:10", detail="All runners combined"),
            StatCardOut(key="climbed", icon="mountain", label="Climbed together", value="200 m", detail="0.6x"),
            StatCardOut(key="prs", icon="medal", label="Personal records", value="2", detail="Set on Strava"),
            StatCardOut(key="pace", icon="gauge", label="Quickest run pace", value="4:30 /km", detail="Joni"),
            StatCardOut(key="kudos", icon="heart", label="Kudos collected", value="5", detail="Most loved: Anna"),
        ]
        view = TeamView(
            members=[(1, member("Joni")), (2, member("Anna"))],
            highlights=HighlightsOut(window_days=7, total_km=10, total_runs=2, cards=cards),
            facts={},
        )
        self.assertEqual(
            card_art.team_card_subjects(view),
            {"together": None, "time": None, "climbed": None, "prs": None, "pace": 1, "kudos": 2},
        )

    def test_avatar_writes_require_site_origin(self):
        def request(origin: str) -> Request:
            return Request({
                "type": "http",
                "method": "POST",
                "path": "/api/v1/avatars/me",
                "headers": [(b"origin", origin.encode())],
            })

        with patch.object(settings, "app_base_url", "https://raceday.example"):
            require_site_origin(request("https://raceday.example"))
            with self.assertRaises(HTTPException) as error:
                require_site_origin(request("https://outside.example"))
            self.assertEqual(error.exception.status_code, 403)

    def test_normalize_removes_metadata_and_limits_dimensions(self):
        png = avatar.normalize_image(image_bytes("JPEG"))
        with Image.open(BytesIO(png)) as result:
            self.assertEqual(result.format, "PNG")
            self.assertEqual(result.size, (64, 64))

    def test_bad_file_is_rejected(self):
        with self.assertRaises(avatar.InvalidImage):
            avatar.normalize_image(b"not an image")

    def test_iphone_heic_photo_is_converted_to_png(self):
        output = BytesIO()
        Image.new("RGB", (80, 60), "#3366aa").save(output, format="HEIF")
        with Image.open(BytesIO(avatar.normalize_image(output.getvalue()))) as result:
            self.assertEqual((result.format, result.size), ("PNG", (80, 60)))

    def test_generated_avatar_must_have_a_transparent_background(self):
        with self.assertRaises(avatar.GenerationFailed):
            avatar.to_avatar(image_bytes())
        opaque = Image.new("RGBA", (64, 64), (232, 93, 42, 255))
        for point in [(0, 0), (0, 63), (63, 0), (63, 63)]:
            opaque.putpixel(point, (0, 0, 0, 0))
        output = BytesIO()
        opaque.save(output, format="PNG")
        with self.assertRaises(avatar.GenerationFailed):
            avatar.to_avatar(output.getvalue())
        with Image.open(BytesIO(avatar.to_avatar(transparent_avatar()))) as image:
            self.assertEqual(image.getpixel((0, 0))[3], 0)
            self.assertEqual(image.getpixel((32, 32))[3], 255)

    def test_generation_sends_photo_and_style_as_separate_images(self):
        requests = []

        def respond(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(transparent_avatar()).decode()}]})

        real_client = httpx.AsyncClient

        def client(*args, **kwargs):
            return real_client(transport=httpx.MockTransport(respond))

        with patch.object(settings, "openai_api_key", "test-key"), patch.object(avatar.httpx, "AsyncClient", client):
            result = asyncio.run(avatar.generate_avatar(avatar.normalize_image(image_bytes()), "blue headband"))

        self.assertTrue(result.startswith(b"\x89PNG"))
        body = requests[0].content
        self.assertEqual(body.count(b'name="image[]"'), 2)
        self.assertIn(b"runner.png", body)
        self.assertIn(b"style.png", body)
        self.assertIn(b"SECOND image as the fixed pose reference", body)
        self.assertIn(b"head position and angle", body)
        self.assertIn(b"direction of gaze", body)
        self.assertIn(b"Do not copy the FIRST image's pose", body)
        self.assertIn(b"blue headband", body)
        self.assertIn(b"gpt-image-2.5-flare", body)
        self.assertIn(b"transparent", body)


if __name__ == "__main__":
    unittest.main()