import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from app.api.v1.router import router as v1_router
from app.database import engine
from app.models import Base
from app.services import coach, enrich


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    worker = asyncio.create_task(enrich.run_forever())
    coach_worker = asyncio.create_task(coach.run_forever())
    yield
    worker.cancel()
    coach_worker.cancel()
    with suppress(asyncio.CancelledError):
        await worker
    with suppress(asyncio.CancelledError):
        await coach_worker


app = FastAPI(title="RaceDay API", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


app.include_router(v1_router)
