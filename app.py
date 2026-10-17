"""Trusted text API boundary plus a thin incoming-call adapter."""
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from graph import ConfigurationError, handle_turn
import infrastructure as db
from knowledge import initialize, utcnow
from voice import router as voice_router
from speech import router as speech_router


@asynccontextmanager
async def lifespan(app):
    if db.enabled():
        await run_in_threadpool(db.initialize)
    await run_in_threadpool(initialize)
    yield


app = FastAPI(title="WaterLine — synthetic text demo", lifespan=lifespan)
app.include_router(voice_router)
app.include_router(speech_router)
WEB = Path(__file__).with_name("web")
app.mount("/demo-assets", StaticFiles(directory=WEB), name="demo-assets")


@app.get("/demo", include_in_schema=False)
async def browser_voice_demo():
    return FileResponse(WEB / "voice.html")


class Turn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(max_length=5000)
    user_id: str = Field(default="demo-user", min_length=1, max_length=100)
    turn_id: str = Field(default_factory=lambda: str(uuid4()), min_length=1, max_length=100)


@app.post("/interact")
async def interact(turn: Turn):
    try:
        return await handle_turn(turn.message, turn.user_id, turn.turn_id, utcnow())
    except ConfigurationError as exc:
        raise HTTPException(503, detail={"message": str(exc), "turn_id": turn.turn_id}) from exc
    except Exception:
        logging.exception("Interaction failed")
        raise HTTPException(503, detail={"message": "Service unavailable. Reports may already be saved; retry with the same turn_id.", "turn_id": turn.turn_id})
