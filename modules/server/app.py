"""FastAPI web server for SeenSlide slide viewing.

Provides:
- REST API for accessing slides
- WebSocket for real-time slide updates
- Static file serving for web UI
"""

import logging
from typing import List, Optional, Dict
from pathlib import Path
import asyncio
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from core.bus.event_bus import EventBus
from core.interfaces.events import EventType
from modules.storage.providers.sqlite_provider import SQLiteStorageProvider
from modules.storage.providers.filesystem_provider import FilesystemStorageProvider

logger = logging.getLogger(__name__)


class SlideServer:
    """Web server for serving captured slides."""

    def __init__(self, storage_path: str = "/tmp/seenslide", host: str = "0.0.0.0", port: int = 8080):
        """Initialize the slide server.

        Args:
            storage_path: Path to storage directory
            host: Host to bind to (0.0.0.0 for all interfaces)
            port: Port to listen on
        """
        self.storage_path = Path(storage_path)
        self.host = host
        self.port = port

        # Initialize FastAPI app
        self.app = FastAPI(
            title="SeenSlide Viewer",
            description="Real-time slide viewing for presentations",
            version="1.0.0"
        )

        # Add CORS middleware
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Initialize storage providers
        self.db_provider = SQLiteStorageProvider()
        self.db_provider.initialize({
            "base_path": str(self.storage_path),
            "database_subdir": "db",
            "database_filename": "seenslide.db"
        })

        self.fs_provider = FilesystemStorageProvider()
        self.fs_provider.initialize({
            "base_path": str(self.storage_path)
        })

        # WebSocket connection manager
        self.active_connections: Dict[str, List[WebSocket]] = {}

        # Event bus for real-time updates
        self.event_bus = EventBus()

        # Setup routes
        self._setup_routes()

        logger.info(f"Slide server initialized at {host}:{port}")

    def _setup_routes(self):
        """Setup FastAPI routes."""

        # API Routes
        @self.app.get("/api/sessions")
        async def list_sessions():
            """List all capture sessions."""
            try:
                sessions = self.db_provider.get_all_sessions()
                return [
                    {
                        "session_id": s.session_id,
                        "name": s.name,
                        "description": s.description,
                        "presenter_name": s.presenter_name,
                        "start_time": s.start_time.isoformat() if s.start_time else None,
                        "end_time": s.end_time.isoformat() if s.end_time else None,
                        "slide_count": self.db_provider.get_slide_count(s.session_id),
                    }
                    for s in sessions
                ]
            except Exception as e:
                logger.error(f"Error listing sessions: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/sessions/{session_id}")
        async def get_session(session_id: str):
            """Get session details."""
            try:
                session = self.db_provider.get_session(session_id)
                if not session:
                    raise HTTPException(status_code=404, detail="Session not found")

                return {
                    "session_id": session.session_id,
                    "name": session.name,
                    "description": session.description,
                    "presenter_name": session.presenter_name,
                    "start_time": session.start_time.isoformat() if session.start_time else None,
                    "end_time": session.end_time.isoformat() if session.end_time else None,
                    "capture_interval_seconds": session.capture_interval_seconds,
                    "dedup_strategy": session.dedup_strategy,
                    "slide_count": self.db_provider.get_slide_count(session_id),
                }
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error getting session: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/sessions/{session_id}/slides")
        async def list_slides(session_id: str, limit: int = 100, offset: int = 0):
            """List slides for a session."""
            try:
                slides = self.db_provider.get_session_slides(
                    session_id,
                    limit=limit,
                    offset=offset
                )

                return [
                    {
                        "slide_id": s.slide_id,
                        "sequence_number": s.sequence_number,
                        "timestamp": s.timestamp,
                        "width": s.width,
                        "height": s.height,
                        "image_path": s.image_path,
                        "thumbnail_path": s.thumbnail_path,
                        "image_hash": s.image_hash,
                    }
                    for s in slides
                ]
            except Exception as e:
                logger.error(f"Error listing slides: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/sessions/{session_id}/slides/{slide_number}")
        async def get_slide_by_number(session_id: str, slide_number: int):
            """Get a specific slide by sequence number."""
            try:
                slides = self.db_provider.get_session_slides(
                    session_id,
                    limit=1,
                    offset=slide_number - 1
                )

                if not slides:
                    raise HTTPException(status_code=404, detail="Slide not found")

                slide = slides[0]
                return {
                    "slide_id": slide.slide_id,
                    "sequence_number": slide.sequence_number,
                    "timestamp": slide.timestamp,
                    "width": slide.width,
                    "height": slide.height,
                    "image_path": slide.image_path,
                    "thumbnail_path": slide.thumbnail_path,
                    "image_hash": slide.image_hash,
                }
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error getting slide: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/sessions/{session_id}/current")
        async def get_current_slide(session_id: str):
            """Get the most recent slide."""
            try:
                slides = self.db_provider.get_session_slides(
                    session_id,
                    limit=1,
                    offset=0
                )

                if not slides:
                    raise HTTPException(status_code=404, detail="No slides found")

                # Get the last slide (most recent)
                total_count = self.db_provider.get_slide_count(session_id)
                slides = self.db_provider.get_session_slides(
                    session_id,
                    limit=1,
                    offset=total_count - 1
                )

                if not slides:
                    raise HTTPException(status_code=404, detail="No slides found")

                slide = slides[0]
                return {
                    "slide_id": slide.slide_id,
                    "sequence_number": slide.sequence_number,
                    "timestamp": slide.timestamp,
                    "width": slide.width,
                    "height": slide.height,
                    "image_path": slide.image_path,
                    "thumbnail_path": slide.thumbnail_path,
                    "total_slides": total_count,
                }
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error getting current slide: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/images/{session_id}/{filename}")
        async def get_image(session_id: str, filename: str):
            """Serve slide image file."""
            try:
                # Construct image path
                image_path = self.storage_path / "images" / session_id / filename

                if not image_path.exists():
                    # Try thumbnail path
                    image_path = self.storage_path / "thumbnails" / session_id / filename

                if not image_path.exists():
                    raise HTTPException(status_code=404, detail="Image not found")

                # Security: Ensure path is within storage directory
                if not str(image_path.resolve()).startswith(str(self.storage_path.resolve())):
                    raise HTTPException(status_code=403, detail="Access denied")

                return FileResponse(image_path)

            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error serving image: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.websocket("/ws/session/{session_id}")
        async def websocket_endpoint(websocket: WebSocket, session_id: str):
            """WebSocket endpoint for real-time slide updates."""
            await websocket.accept()

            # Add to active connections
            if session_id not in self.active_connections:
                self.active_connections[session_id] = []
            self.active_connections[session_id].append(websocket)

            logger.info(f"WebSocket connected for session: {session_id}")

            try:
                # Send current state
                total_slides = self.db_provider.get_slide_count(session_id)
                await websocket.send_json({
                    "type": "connected",
                    "session_id": session_id,
                    "total_slides": total_slides,
                })

                # Keep connection alive and handle incoming messages
                while True:
                    data = await websocket.receive_text()
                    # Echo back (can add commands here later)
                    await websocket.send_json({
                        "type": "pong",
                        "message": data,
                    })

            except WebSocketDisconnect:
                logger.info(f"WebSocket disconnected for session: {session_id}")
                self.active_connections[session_id].remove(websocket)
                if not self.active_connections[session_id]:
                    del self.active_connections[session_id]

        @self.app.get("/")
        async def root():
            """Serve main viewer page."""
            static_path = Path(__file__).parent / "static" / "index.html"
            if not static_path.exists():
                return JSONResponse({
                    "message": "SeenSlide Server",
                    "version": "1.0.0",
                    "docs": "/docs",
                    "api": "/api/sessions",
                })
            return FileResponse(static_path)

        # Mount static files
        static_dir = Path(__file__).parent / "static"
        if static_dir.exists():
            self.app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    async def broadcast_new_slide(self, session_id: str, slide_data: dict):
        """Broadcast new slide to all connected WebSocket clients.

        Args:
            session_id: Session ID
            slide_data: Slide information to broadcast
        """
        if session_id in self.active_connections:
            disconnected = []
            for connection in self.active_connections[session_id]:
                try:
                    await connection.send_json({
                        "type": "new_slide",
                        "slide": slide_data,
                    })
                except Exception as e:
                    logger.error(f"Error broadcasting to websocket: {e}")
                    disconnected.append(connection)

            # Remove disconnected clients
            for conn in disconnected:
                self.active_connections[session_id].remove(conn)

    def run(self):
        """Run the server."""
        import uvicorn
        logger.info(f"Starting server on {self.host}:{self.port}")
        print(f"\n{'='*70}")
        print(f"SeenSlide Server Starting")
        print(f"{'='*70}")
        print(f"\nAccess the viewer at:")
        print(f"  http://{self.host}:{self.port}")
        print(f"  http://localhost:{self.port}")
        print(f"\nAPI Documentation:")
        print(f"  http://localhost:{self.port}/docs")
        print(f"\nPress Ctrl+C to stop\n")

        uvicorn.run(
            self.app,
            host=self.host,
            port=self.port,
            log_level="info"
        )


def main():
    """Run server standalone."""
    import argparse

    parser = argparse.ArgumentParser(description="SeenSlide Web Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on")
    parser.add_argument("--storage", default="/tmp/seenslide", help="Storage path")

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Create and run server
    server = SlideServer(
        storage_path=args.storage,
        host=args.host,
        port=args.port
    )
    server.run()


if __name__ == "__main__":
    main()
