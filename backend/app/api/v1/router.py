from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.teams import router as teams_router
from app.api.v1.webhook import router as webhook_router

router = APIRouter(prefix="/api/v1")
router.include_router(auth_router)
router.include_router(teams_router)
router.include_router(webhook_router)
