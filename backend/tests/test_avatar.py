import asyncio
import base64
import unittest
from io import BytesIO
from unittest.mock import patch

import httpx
from fastapi import HTTPException
from PIL import Image
from starlette.requests import Request

from app.api.v1.avatars import require_site_origin
from app.config import settings
from app.services import avatar


def image_bytes(format: str = "PNG") -> bytes:
    output = BytesIO()
    Image.new("RGB", (64, 64), "#e85d2a").save(output, format=format)
    return output.getvalue()


class AvatarTests(unittest.TestCase):
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

    def test_generation_sends_photo_and_style_as_separate_images(self):
        requests = []

        def respond(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(image_bytes("JPEG")).decode()}]})

        real_client = httpx.AsyncClient

        def client(*args, **kwargs):
            return real_client(transport=httpx.MockTransport(respond))

        with patch.object(settings, "openai_api_key", "test-key"), patch.object(avatar.httpx, "AsyncClient", client):
            result = asyncio.run(avatar.generate_avatar(avatar.normalize_image(image_bytes()), "blue headband"))

        self.assertTrue(result.startswith(b"\xff\xd8"))
        body = requests[0].content
        self.assertEqual(body.count(b'name="image[]"'), 2)
        self.assertIn(b"runner.png", body)
        self.assertIn(b"style.png", body)
        self.assertIn(b"blue headband", body)
        self.assertIn(b"gpt-image-2.5-flare", body)


if __name__ == "__main__":
    unittest.main()