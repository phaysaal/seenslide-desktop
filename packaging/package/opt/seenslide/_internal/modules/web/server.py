"""Web server runner for SeenSlide."""

import logging
import uvicorn
from pathlib import Path

from modules.web.app import create_app
from modules.web.state import AppState
from core.config.config_loader import ConfigLoader

logger = logging.getLogger(__name__)


def run_server(
    host: str = "0.0.0.0",
    port: int = 8000,
    config_path: str = None,
    reload: bool = False
):
    """Run the SeenSlide web server.

    Args:
        host: Host to bind to
        port: Port to bind to
        config_path: Path to configuration file
        reload: Enable auto-reload for development
    """
    # Load configuration
    config_loader = ConfigLoader()
    if config_path:
        config = config_loader.load_from_file(config_path)
    else:
        config = config_loader.load_defaults()

    # Create application state
    storage_config = config.get("storage", {})
    app_state = AppState(config=storage_config)

    # Create FastAPI app
    app = create_app(app_state)

    # Run server
    logger.info(f"Starting SeenSlide web server on {host}:{port}")
    uvicorn.run(
        app,
        host=host,
        port=port,
        reload=reload,
        log_level="info"
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="SeenSlide Web Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    parser.add_argument("--config", help="Path to configuration file")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")

    args = parser.parse_args()

    run_server(
        host=args.host,
        port=args.port,
        config_path=args.config,
        reload=args.reload
    )
