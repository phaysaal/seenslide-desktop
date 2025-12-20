"""FastAPI application for SeenSlide web server."""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

from modules.web.api import sessions, slides, system, websocket
from modules.web.state import AppState

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for application startup and shutdown."""
    # Startup
    logger.info("Starting SeenSlide web server")
    yield
    # Shutdown
    logger.info("Shutting down SeenSlide web server")


def create_app(state: AppState = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        state: Application state (optional, for dependency injection)

    Returns:
        Configured FastAPI application
    """
    app = FastAPI(
        title="SeenSlide API",
        description="Real-time slide navigation system API",
        version="1.0.0",
        lifespan=lifespan
    )

    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Store application state
    if state:
        app.state.app_state = state

    # Include API routers
    app.include_router(sessions.router, prefix="/api/sessions", tags=["sessions"])
    app.include_router(slides.router, prefix="/api/slides", tags=["slides"])
    app.include_router(system.router, prefix="/api/system", tags=["system"])
    app.include_router(websocket.router, prefix="/ws", tags=["websocket"])

    # Serve static files (web client)
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    logger.info("FastAPI application created")
    return app
