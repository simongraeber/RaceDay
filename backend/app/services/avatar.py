import base64
import logging
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import settings

log = logging.getLogger(__name__)
REFERENCE_IMAGE = Path(__file__).resolve().parents[1] / "resources" / "CaracterReferenceImage.png"
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 16_000_000


class InvalidImage(Exception):
    pass


class GenerationFailed(Exception):
    pass


def normalize_image(raw: bytes) -> bytes:
    try:
        with Image.open(BytesIO(raw)) as image:
            if image.format not in {"PNG", "JPEG", "WEBP"} or image.width * image.height > MAX_PIXELS:
                raise InvalidImage("Use a PNG, JPEG or WebP image under 16 megapixels")
            image = ImageOps.exif_transpose(image).convert("RGB")
            image.thumbnail((1024, 1024))
            output = BytesIO()
            image.save(output, format="PNG")
            return output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise InvalidImage("Could not read the image") from exc


def to_avatar(raw: bytes) -> bytes:
    try:
        with Image.open(BytesIO(raw)) as image:
            image = image.convert("RGB")
            image.thumbnail((768, 768))
            output = BytesIO()
            image.save(output, format="JPEG", quality=85, optimize=True)
            return output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise GenerationFailed("Image generation returned an invalid image") from exc


async def generate_avatar(photo: bytes, description: str) -> bytes:
    prompt = (
        "Create a single friendly 3D cartoon portrait of the runner in the FIRST image. "
        "Preserve their recognizable facial features, hair and skin tone; render them in running clothes. "
        "Use the SECOND image only as the visual style reference: match its character proportions, "
        "material, lighting and level of detail. Center the character against a clean neutral background. "
        "No text, logos or other people. "
        f"Optional runner details: {description.strip()[:300]}"
    )
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(
                "https://api.openai.com/v1/images/edits",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                data={
                    "model": "gpt-image-2.5-flare",
                    "prompt": prompt,
                    "size": "1024x1024",
                    "quality": "medium",
                    "output_format": "jpeg",
                },
                files=[
                    ("image[]", ("runner.png", photo, "image/png")),
                    ("image[]", ("style.png", REFERENCE_IMAGE.read_bytes(), "image/png")),
                ],
            )
            response.raise_for_status()
            encoded = response.json()["data"][0]["b64_json"]
            return to_avatar(base64.b64decode(encoded, validate=True))
    except (httpx.HTTPError, KeyError, IndexError, ValueError, OSError) as exc:
        log.warning("Avatar image edit failed: %s", type(exc).__name__)
        raise GenerationFailed("Could not generate an avatar. Please try again later") from exc