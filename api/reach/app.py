"""FastAPI application factory. Served by uvicorn locally and wrapped by Azure Functions (ASGI)."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from reach import __version__
from reach.brain import build_understander
from reach.channels.sim import router as sim_router
from reach.channels.twilio import router as twilio_router
from reach.channels.web_api import router as web_router
from reach.core.domains import load_domains
from reach.core.service import RateLimiter, ReachService
from reach.settings import Settings, get_settings
from reach.speech.tts import build_tts
from reach.storage.db import init_db, make_engine
from reach.storage.repository import Repository

log = logging.getLogger("reach")


def create_app(settings: Settings | None = None) -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    cfg = settings or get_settings()
    engine = make_engine(cfg.database_url)
    init_db(engine)
    repo = Repository(engine)
    domains = load_domains()
    service = ReachService(
        repo,
        domains,
        build_understander(cfg),
        default_domain=cfg.default_domain,
        confirm_thresholds={"voice": cfg.confirm_threshold, "sms": cfg.sms_confirm_threshold, "web": 0.0},
    )
    if cfg.salt_is_default:
        log.warning("REPORTER_SALT is the development default; set it before any real-phone test")

    app = FastAPI(
        title="Reach API", version=__version__, docs_url="/api/docs", openapi_url="/api/openapi.json"
    )
    app.state.settings = cfg
    app.state.engine = engine
    app.state.service = service
    app.state.tts = build_tts(cfg)
    app.state.limiter = RateLimiter(cfg.rate_limit_max, cfg.rate_limit_window_s)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(twilio_router)
    app.include_router(sim_router)
    app.include_router(web_router)
    if cfg.web_dist_dir.is_dir():
        app.mount("/", StaticFiles(directory=str(cfg.web_dist_dir), html=True), name="web")
    return app
