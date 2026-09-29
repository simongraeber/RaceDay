import secrets
from datetime import datetime, timedelta, timezone

import jwt
from cryptography.fernet import Fernet

from app.config import settings

SESSION_COOKIE = "rd_session"
STATE_COOKIE = "rd_oauth_state"
_ALG = "HS256"

_fernet = Fernet(settings.token_encryption_key)


def encrypt(value: str) -> str:
    return _fernet.encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    return _fernet.decrypt(value.encode()).decode()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_session_token(athlete_id: int) -> str:
    return jwt.encode(
        {
            "sub": str(athlete_id),
            "typ": "session",
            "exp": _now() + timedelta(days=settings.session_expire_days),
        },
        settings.session_secret,
        algorithm=_ALG,
    )


def read_session_token(token: str) -> int | None:
    try:
        payload = jwt.decode(token, settings.session_secret, algorithms=[_ALG])
    except jwt.PyJWTError:
        return None
    if payload.get("typ") != "session":
        return None
    return int(payload["sub"])


def create_oauth_state(intent: str, team_id: str | None) -> tuple[str, str]:
    """Return (state, nonce). The nonce goes into a cookie to bind the flow to this browser."""
    nonce = secrets.token_urlsafe(24)
    state = jwt.encode(
        {
            "typ": "oauth_state",
            "intent": intent,
            "team": team_id,
            "nonce": nonce,
            "exp": _now() + timedelta(minutes=10),
        },
        settings.session_secret,
        algorithm=_ALG,
    )
    return state, nonce


def read_oauth_state(state: str, nonce: str) -> dict | None:
    try:
        payload = jwt.decode(state, settings.session_secret, algorithms=[_ALG])
    except jwt.PyJWTError:
        return None
    if payload.get("typ") != "oauth_state":
        return None
    if not nonce or not secrets.compare_digest(payload.get("nonce", ""), nonce):
        return None
    return payload
