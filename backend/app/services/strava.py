import time
from urllib.parse import urlencode

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Athlete
from app.security import decrypt, encrypt

AUTHORIZE_URL = "https://www.strava.com/oauth/authorize"
TOKEN_URL = "https://www.strava.com/oauth/token"
REVOKE_URL = "https://www.strava.com/oauth/revoke"
API_URL = "https://www.strava.com/api/v3"

# read_all also covers "Only You" and followers-only runs; Strava then stops masking privacy zones,
# so routes are trimmed harder on our side and kept only for runs visible to everyone.
SCOPE = "read,activity:read_all"
PER_PAGE = 200
STREAM_KEYS = "latlng,altitude,distance,time"
_TIMEOUT = 15.0
_RATE_WINDOW_S = 15 * 60

# Last seen read-rate usage: (seen_at, (15min_used, daily_used), (15min_limit, daily_limit))
_read_rate: tuple[float, tuple[int, ...], tuple[int, ...]] | None = None


class StravaError(Exception):
    pass


class RateLimited(StravaError):
    pass


class Unauthorized(StravaError):
    pass


def redirect_uri() -> str:
    return f"{settings.app_base_url}/api/v1/auth/strava/callback"


def authorize_url(state: str) -> str:
    params = {
        "client_id": settings.strava_client_id,
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "approval_prompt": "auto",
        "scope": SCOPE,
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def _raise_for(resp: httpx.Response) -> None:
    if resp.status_code == 429:
        raise RateLimited("Strava rate limit reached")
    if resp.status_code in (400, 401, 403):
        raise Unauthorized(f"Strava rejected request: {resp.status_code}")
    if resp.status_code >= 400:
        raise StravaError(f"Strava error: {resp.status_code}")


async def _token_request(data: dict) -> dict:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            TOKEN_URL,
            data={
                "client_id": settings.strava_client_id,
                "client_secret": settings.strava_client_secret,
                **data,
            },
        )
    _raise_for(resp)
    return resp.json()


async def exchange_code(code: str) -> dict:
    return await _token_request({"code": code, "grant_type": "authorization_code"})


def store_tokens(athlete: Athlete, data: dict) -> None:
    athlete.access_token_enc = encrypt(data["access_token"])
    athlete.refresh_token_enc = encrypt(data["refresh_token"])
    athlete.expires_at = int(data["expires_at"])


async def get_access_token(db: AsyncSession, athlete: Athlete) -> str:
    """Return a valid access token, refreshing and persisting rotated tokens if needed."""
    if athlete.expires_at - 300 > time.time():
        return decrypt(athlete.access_token_enc)
    data = await _token_request(
        {"grant_type": "refresh_token", "refresh_token": decrypt(athlete.refresh_token_enc)}
    )
    store_tokens(athlete, data)
    await db.commit()
    return data["access_token"]


async def revoke(athlete: Athlete) -> None:
    """Revoke our access at Strava. Revoking the refresh token also kills the access token."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            REVOKE_URL,
            auth=(settings.strava_client_id, settings.strava_client_secret),
            data={"token": decrypt(athlete.refresh_token_enc), "token_type_hint": "refresh_token"},
        )
    _raise_for(resp)


def _track_rate(resp: httpx.Response) -> None:
    global _read_rate
    usage = resp.headers.get("x-readratelimit-usage") or resp.headers.get("x-ratelimit-usage")
    limit = resp.headers.get("x-readratelimit-limit") or resp.headers.get("x-ratelimit-limit")
    try:
        if usage and limit:
            _read_rate = (
                time.monotonic(),
                tuple(int(v) for v in usage.split(",")),
                tuple(int(v) for v in limit.split(",")),
            )
    except ValueError:
        pass


def read_budget_ok(share: float = 0.6) -> bool:
    """True while background work may spend read requests without starving webhooks."""
    if _read_rate is None or time.monotonic() - _read_rate[0] > _RATE_WINDOW_S:
        return True
    _, used, limits = _read_rate
    return all(u < lim * share for u, lim in zip(used, limits))


async def _get(token: str, path: str, params: dict | None = None) -> dict | list | None:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(
            f"{API_URL}{path}",
            params=params,
            headers={"Authorization": f"Bearer {token}"},
        )
    _track_rate(resp)
    if resp.status_code == 404:
        return None
    _raise_for(resp)
    return resp.json()


async def get_athlete(token: str) -> dict:
    return await _get(token, "/athlete")  # type: ignore[return-value]


async def list_activities(token: str, after: int, page: int) -> list[dict]:
    result = await _get(
        token, "/athlete/activities", {"after": after, "page": page, "per_page": PER_PAGE}
    )
    return result or []  # type: ignore[return-value]


async def get_activity(token: str, activity_id: int) -> dict | None:
    return await _get(token, f"/activities/{activity_id}")  # type: ignore[return-value]


async def get_activity_streams(token: str, activity_id: int) -> dict | None:
    return await _get(  # type: ignore[return-value]
        token, f"/activities/{activity_id}/streams", {"keys": STREAM_KEYS, "key_by_type": "true"}
    )
