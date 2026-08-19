"""FastAPI app factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from sarai import db
from sarai.api.routes import events, health, meetings, summary, transcript
from sarai.config import get_settings

log = logging.getLogger("sarai.api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    settings.ensure_dirs()
    applied = db.init_db()
    if applied:
        log.info("applied migrations: %s", ", ".join(applied))
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Sarai AI", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Never swallow: log with the path, return something the UI can display.
        log.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": f"Internal error: {exc}"})

    app.include_router(health.router, prefix="/api")
    app.include_router(meetings.router, prefix="/api")
    app.include_router(transcript.router, prefix="/api")
    app.include_router(summary.router, prefix="/api")
    app.include_router(events.router, prefix="/api")
    return app


app = create_app()
