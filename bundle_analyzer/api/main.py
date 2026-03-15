"""FastAPI application factory for the Bundle Analyzer backend.

Creates the app with CORS middleware, all API routers, an optional
static file mount for the production frontend build, and a lifespan
context manager for startup/shutdown cleanup.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

# Load .env before any other imports that might read env vars
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
load_dotenv()  # also try cwd

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from bundle_analyzer.api.routes import (
    analysis,
    bundles,
    diff,
    export,
    findings,
    interview,
    ws,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: startup and shutdown hooks.

    On startup, logs the server configuration.
    On shutdown, cleans up any temporary files from active sessions.

    Args:
        app: The FastAPI application instance.
    """
    logger.info("Bundle Analyzer API starting up")

    # Initialize PostgreSQL connection
    import os as _os
    if _os.environ.get("DATABASE_URL") or _os.environ.get("POSTGRES_URL"):
        try:
            from bundle_analyzer.db.database import init_db
            await init_db()
            logger.info("PostgreSQL database connected")
        except Exception as exc:
            logger.warning("Database init failed (running without persistence): {}", exc)
    else:
        logger.info("No DATABASE_URL set — running without database persistence")

    yield
    # Cleanup: remove temp files for all sessions
    # Close database connection
    try:
        from bundle_analyzer.db.database import close_db
        await close_db()
    except Exception:
        pass

    logger.info("Bundle Analyzer API shutting down -- cleaning up sessions")
    from bundle_analyzer.api.deps import get_store

    store = get_store()
    for session in store.list_all():
        if session.extracted_root and session.extracted_root.exists():
            import shutil

            try:
                shutil.rmtree(session.extracted_root, ignore_errors=True)
            except OSError as exc:
                logger.warning("Cleanup failed for {}: {}", session.id, exc)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Fully configured FastAPI app with all routes and middleware.
    """
    app = FastAPI(
        title="Bundle Analyzer API",
        description="AI-powered Kubernetes support bundle forensics",
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS middleware -- allows Next.js dev server + production frontend
    allowed_origins = os.environ.get(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    allowed_origins = [o.strip() for o in allowed_origins if o.strip()]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Global exception handler to ensure CORS headers on 500s
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Catch unhandled exceptions so CORS headers are still present."""
        logger.error("Unhandled error on {}: {}", request.url.path, exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error. Please try again."},
        )

    # Include all routers under /api/v1
    api_prefix = "/api/v1"
    app.include_router(bundles.router, prefix=api_prefix)
    app.include_router(analysis.router, prefix=api_prefix)
    app.include_router(findings.router, prefix=api_prefix)
    app.include_router(interview.router, prefix=api_prefix)
    app.include_router(diff.router, prefix=api_prefix)
    app.include_router(export.router, prefix=api_prefix)
    app.include_router(ws.router, prefix=api_prefix)

    # Health check
    @app.get("/api/v1/health", tags=["health"])
    async def health_check() -> dict[str, str]:
        """Return API health status.

        Returns:
            Dict with status field.
        """
        return {"status": "ok"}

    # Static files mount for production frontend (Next.js export)
    frontend_dir = Path(__file__).parent.parent.parent / "frontend" / "out"
    if frontend_dir.is_dir():
        app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
        logger.info("Serving frontend static files from {}", frontend_dir)
    else:
        logger.debug("No frontend build found at {}", frontend_dir)

    return app


# Module-level app instance for `uvicorn bundle_analyzer.api.main:app`
app = create_app()
