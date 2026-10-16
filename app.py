"""Trusted text API boundary plus a thin incoming-call adapter."""
import logging
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from graph import ConfigurationError, handle_turn
from knowledge import initialize, utcnow
from voice import router as voice_router


@asynccontextmanager
async def lifespan(app):
    await run_in_threadpool(initialize)
    yield


app = FastAPI(title="WaterLine — synthetic text demo", lifespan=lifespan)
app.include_router(voice_router)


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
