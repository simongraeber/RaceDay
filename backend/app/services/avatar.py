import base64
import logging
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener

from app.config import settings

register_heif_opener()

log = logging.getLogger(__name__)
REFERENCE_IMAGE = Path(__file__).resolve().parents[1] / "resources" / "CaracterReferenceImage.png"
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
# iPhone main cameras shoot 24-48 MP
MAX_PIXELS = 50_000_000
FORMATS = {"PNG", "JPEG", "WEBP", "HEIF"}


class InvalidImage(Exception):
    pass


class GenerationFailed(Exception):
    pass


def normalize_image(raw: bytes) -> bytes:
    try:
        with Image.open(BytesIO(raw)) as image:
            if image.format not in FORMATS or image.width * image.height > MAX_PIXELS:
                raise InvalidImage("Use a PNG, JPEG, WebP or HEIC photo under 50 megapixels")
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
            image = image.convert("RGBA")
            alpha = image.getchannel("A")
            corners = [(0, 0), (image.width - 1, 0), (0, image.height - 1), (image.width - 1, image.height - 1)]
            transparent_pixels = sum(alpha.histogram()[:128])
            if (
                any(alpha.getpixel(point) > 16 for point in corners)
                or transparent_pixels < image.width * image.height * 0.05
                or alpha.getextrema()[1] < 128
            ):
                raise GenerationFailed("The generated avatar had no transparent background. Please try again")
            image.thumbnail((768, 1152))
            output = BytesIO()
            image.save(output, format="PNG", optimize=True)
            return output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise GenerationFailed("Image generation returned an invalid image") from exc


async def generate_avatar(photo: bytes, description: str) -> bytes:
    prompt = (
        "Create a single friendly 3D cartoon character of the runner in the FIRST image. "
        "FULL BODY, head to toe: the entire figure including both feet and running shoes must be visible, "
        "standing in a relaxed, confident running pose, centered with a small margin on all sides. "
        "Never crop at the waist, knees or ankles. "
        "Preserve their recognizable facial features, hair and skin tone; dress them in running clothes. "
        "Use the SECOND image only as the visual style reference: match its character proportions, "
        "material, lighting and level of detail. Clean studio lighting. "
        "Transparent background, no floor, no shadow plate, no rectangular backdrop. "
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
                    "size": "1024x1536",
                    "quality": "medium",
                    "output_format": "png",
                    "background": "transparent",
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