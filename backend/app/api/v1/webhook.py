import secrets

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status

from app.config import settings
from app.services import sync

router = APIRouter(prefix="/strava/webhook", tags=["webhook"])


@router.get("")
async def verify_subscription(
    mode: str = Query(alias="hub.mode"),
    challenge: str = Query(alias="hub.challenge"),
    verify_token: str = Query(alias="hub.verify_token"),
):
    expected = settings.strava_webhook_verify_token
    if mode != "subscribe" or not expected or not secrets.compare_digest(verify_token, expected):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return {"hub.challenge": challenge}


@router.post("")
async def receive_event(event: dict, background: BackgroundTasks):
    # Strava expects a 200 within 2 seconds, so work happens after the response
    expected_sub = settings.strava_webhook_subscription_id
    if expected_sub is None or event.get("subscription_id") == expected_sub:
        background.add_task(sync.handle_event, event)
    return {"ok": True}
