from fastapi import APIRouter

from app.api.v1.ask import router as ask_router
from app.api.v1.auth import router as auth_router
from app.api.v1.avatars import router as avatars_router
from app.api.v1.maps import router as maps_router
from app.api.v1.teams import router as teams_router
from app.api.v1.webhook import router as webhook_router

router = APIRouter(prefix="/api/v1")
router.include_router(ask_router)
router.include_router(auth_router)
router.include_router(avatars_router)
router.include_router(maps_router)
router.include_router(teams_router)
router.include_router(webhook_router)
