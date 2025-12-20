"""Admin web server for SeenSlide management.

Provides:
- User authentication
- Capture session management (start/stop/pause)
- Session deletion
- QR code generation for viewer access
- Admin dashboard UI
"""

import logging
import io
from typing import Optional, Dict
from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, HTTPException, Depends, Cookie, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from core.models.user import User
from core.auth.auth_utils import AuthUtils, SessionManager
from modules.storage.user_storage import UserStorage
from modules.storage.providers.sqlite_provider import SQLiteStorageProvider
from seenslide.orchestrator import SeenSlideOrchestrator

logger = logging.getLogger(__name__)


# Request/Response models
class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    success: bool
    message: str
    user: Optional[Dict] = None


class SessionStartRequest(BaseModel):
    name: str
    description: str = ""
    presenter_name: str = ""
    monitor_id: int = 1
    dedup_tolerance: float = 0.50  # Default 50% tolerance


class SessionControlResponse(BaseModel):
    success: bool
    message: str
    session_id: Optional[str] = None


class AdminServer:
    """Admin web server for management."""

    def __init__(
        self,
        storage_path: str = "/tmp/seenslide",
        host: str = "0.0.0.0",
        port: int = 8081,
        viewer_port: int = 8080
    ):
        """Initialize admin server.

        Args:
            storage_path: Path to storage directory
            host: Host to bind to
            port: Port for admin server
            viewer_port: Port where viewer server is running
        """
        self.storage_path = Path(storage_path)
        self.host = host
        self.port = port
        self.viewer_port = viewer_port

        # Initialize FastAPI app
        self.app = FastAPI(
            title="SeenSlide Admin",
            description="Admin interface for SeenSlide",
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

        # Initialize storage
        self.user_storage = UserStorage(
            db_path=str(self.storage_path / "db" / "seenslide.db")
        )
        self.db_provider = SQLiteStorageProvider()
        self.db_provider.initialize({
            "base_path": str(self.storage_path),
            "database_subdir": "db",
            "database_filename": "seenslide.db"
        })

        # Session manager
        self.session_manager = SessionManager()

        # Active capture orchestrator (if any)
        self.active_orchestrator: Optional[SeenSlideOrchestrator] = None
        self.active_session_id: Optional[str] = None

        # Viewer server process
        self.viewer_process = None
        self.viewer_running = False

        # Setup routes
        self._setup_routes()

        logger.info(f"Admin server initialized at {host}:{port}")

    def _get_current_user(self, session_token: Optional[str] = Cookie(None)) -> User:
        """Get current authenticated user.

        Args:
            session_token: Session token from cookie

        Returns:
            User object

        Raises:
            HTTPException: If not authenticated
        """
        if not session_token:
            raise HTTPException(status_code=401, detail="Not authenticated")

        user_id = self.session_manager.validate_session(session_token)
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid or expired session")

        user = self.user_storage.get_user_by_id(user_id)
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="User not found or inactive")

        return user

    def _setup_routes(self):
        """Setup FastAPI routes."""

        @self.app.post("/api/auth/login")
        async def login(request: LoginRequest, response: Response):
            """Authenticate user and create session."""
            try:
                # Get user from database
                user = self.user_storage.get_user_by_username(request.username)

                if not user:
                    return LoginResponse(success=False, message="Invalid username or password")

                if not user.is_active:
                    return LoginResponse(success=False, message="Account is inactive")

                # Verify password
                if not AuthUtils.verify_password(request.password, user.password_hash):
                    return LoginResponse(success=False, message="Invalid username or password")

                # Create session
                token = self.session_manager.create_session(user.user_id)

                # Update last login
                self.user_storage.update_last_login(user.user_id)

                # Set cookie
                response.set_cookie(
                    key="session_token",
                    value=token,
                    httponly=True,
                    max_age=86400,  # 24 hours
                    samesite="lax"
                )

                return LoginResponse(
                    success=True,
                    message="Login successful",
                    user=user.to_dict()
                )

            except Exception as e:
                logger.error(f"Login error: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/api/auth/logout")
        async def logout(
            response: Response,
            session_token: Optional[str] = Cookie(None)
        ):
            """Logout user and invalidate session."""
            if session_token:
                self.session_manager.invalidate_session(session_token)

            response.delete_cookie(key="session_token")
            return {"success": True, "message": "Logged out successfully"}

        @self.app.get("/api/auth/me")
        async def get_current_user_info(
            current_user: User = Depends(self._get_current_user)
        ):
            """Get current user information."""
            return current_user.to_dict()

        @self.app.get("/api/sessions")
        async def list_sessions(
            current_user: User = Depends(self._get_current_user)
        ):
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
                        "status": s.status,
                        "slide_count": self.db_provider.get_slide_count(s.session_id),
                        "is_active": s.session_id == self.active_session_id
                    }
                    for s in sessions
                ]
            except Exception as e:
                logger.error(f"Error listing sessions: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/api/sessions/start")
        async def start_session(
            request: SessionStartRequest,
            current_user: User = Depends(self._get_current_user)
        ):
            """Start a new capture session and viewer server."""
            try:
                if self.active_orchestrator:
                    return SessionControlResponse(
                        success=False,
                        message="A capture session is already running"
                    )

                # Start viewer server if not running
                if not self.viewer_running:
                    import subprocess
                    import sys

                    python_exec = sys.executable
                    script_path = Path(__file__).parent.parent.parent / "seenslide.py"

                    self.viewer_process = subprocess.Popen(
                        [python_exec, str(script_path), "server",
                         "--host", self.host,
                         "--port", str(self.viewer_port)],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        start_new_session=True
                    )

                    self.viewer_running = True
                    logger.info(f"Auto-started viewer server on port {self.viewer_port}")

                # Create orchestrator with config
                config_path = Path(__file__).parent.parent.parent / "dev" / "config_wayland.yaml"
                if not config_path.exists():
                    config_path = None  # Use defaults

                self.active_orchestrator = SeenSlideOrchestrator(
                    config_path=str(config_path) if config_path else None
                )

                # Update deduplication tolerance in config
                if 'deduplication' not in self.active_orchestrator.config:
                    self.active_orchestrator.config['deduplication'] = {}
                self.active_orchestrator.config['deduplication']['perceptual_threshold'] = request.dedup_tolerance

                logger.info(f"Using deduplication perceptual threshold: {request.dedup_tolerance} "
                           f"(tolerance level: {int((1.0 - request.dedup_tolerance) * 100)}%)")

                # Start session
                success = self.active_orchestrator.start_session(
                    session_name=request.name,
                    description=request.description,
                    presenter_name=request.presenter_name,
                    monitor_id=request.monitor_id
                )

                if not success:
                    self.active_orchestrator = None
                    return SessionControlResponse(
                        success=False,
                        message="Failed to start capture session"
                    )

                # Get session ID
                stats = self.active_orchestrator.get_statistics()
                session_id = stats.get("session", {}).get("session_id")
                self.active_session_id = session_id

                logger.info(f"Started capture session: {session_id}")

                return SessionControlResponse(
                    success=True,
                    message="Capture session and viewer server started successfully",
                    session_id=session_id
                )

            except Exception as e:
                logger.error(f"Error starting session: {e}")
                self.active_orchestrator = None
                self.active_session_id = None
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/api/sessions/stop")
        async def stop_session(
            current_user: User = Depends(self._get_current_user)
        ):
            """Stop the active capture session."""
            try:
                if not self.active_orchestrator:
                    return SessionControlResponse(
                        success=False,
                        message="No active capture session"
                    )

                session_id = self.active_session_id

                # Stop session
                self.active_orchestrator.stop_session()
                self.active_orchestrator = None
                self.active_session_id = None

                logger.info(f"Stopped capture session: {session_id}")

                return SessionControlResponse(
                    success=True,
                    message="Capture session stopped successfully",
                    session_id=session_id
                )

            except Exception as e:
                logger.error(f"Error stopping session: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/sessions/status")
        async def get_session_status(
            current_user: User = Depends(self._get_current_user)
        ):
            """Get status of active capture session."""
            if not self.active_orchestrator:
                return {
                    "active": False,
                    "session_id": None
                }

            stats = self.active_orchestrator.get_statistics()
            return {
                "active": True,
                "session_id": self.active_session_id,
                "stats": stats
            }

        @self.app.delete("/api/sessions/{session_id}")
        async def delete_session(
            session_id: str,
            current_user: User = Depends(self._get_current_user)
        ):
            """Delete a capture session and its slides."""
            try:
                # Don't allow deleting active session
                if session_id == self.active_session_id:
                    return {"success": False, "message": "Cannot delete active session"}

                # Get session
                session = self.db_provider.get_session(session_id)
                if not session:
                    raise HTTPException(status_code=404, detail="Session not found")

                # Delete slide files
                images_dir = self.storage_path / "images" / session_id
                thumbnails_dir = self.storage_path / "thumbnails" / session_id

                if images_dir.exists():
                    import shutil
                    shutil.rmtree(images_dir)

                if thumbnails_dir.exists():
                    import shutil
                    shutil.rmtree(thumbnails_dir)

                # Delete from database (slides will be deleted by foreign key cascade)
                cursor = self.db_provider._conn.cursor()
                cursor.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
                cursor.execute("DELETE FROM slides WHERE session_id = ?", (session_id,))
                self.db_provider._conn.commit()

                logger.info(f"Deleted session: {session_id}")

                return {"success": True, "message": "Session deleted successfully"}

            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error deleting session: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.delete("/api/sessions/{session_id}/slides/{slide_id}")
        async def delete_slide(
            session_id: str,
            slide_id: str,
            current_user: User = Depends(self._get_current_user)
        ):
            """Delete an individual slide."""
            try:
                # Get slide from database
                slide = self.db_provider.get_slide(slide_id)
                if not slide or slide.session_id != session_id:
                    raise HTTPException(status_code=404, detail="Slide not found")

                # Delete image files
                image_path = Path(slide.image_path)
                thumbnail_path = Path(slide.thumbnail_path)

                if image_path.exists():
                    image_path.unlink()

                if thumbnail_path.exists():
                    thumbnail_path.unlink()

                # Delete from database
                cursor = self.db_provider._conn.cursor()
                cursor.execute("DELETE FROM slides WHERE slide_id = ?", (slide_id,))
                self.db_provider._conn.commit()

                # Update session slide count
                session = self.db_provider.get_session(session_id)
                if session:
                    session.total_slides = self.db_provider.get_slide_count(session_id)
                    self.db_provider.update_session(session)

                logger.info(f"Deleted slide: {slide_id}")

                return {"success": True, "message": "Slide deleted successfully"}

            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error deleting slide: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/api/viewer/start")
        async def start_viewer(
            current_user: User = Depends(self._get_current_user)
        ):
            """Start the viewer server."""
            try:
                if self.viewer_running:
                    return {"success": False, "message": "Viewer server is already running"}

                import subprocess
                import sys

                # Start viewer server in background
                python_exec = sys.executable
                script_path = Path(__file__).parent.parent.parent / "seenslide.py"

                self.viewer_process = subprocess.Popen(
                    [python_exec, str(script_path), "server",
                     "--host", self.host,
                     "--port", str(self.viewer_port)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    start_new_session=True
                )

                self.viewer_running = True
                logger.info(f"Started viewer server on port {self.viewer_port}")

                return {
                    "success": True,
                    "message": "Viewer server started successfully",
                    "port": self.viewer_port
                }

            except Exception as e:
                logger.error(f"Error starting viewer server: {e}")
                self.viewer_running = False
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/api/viewer/stop")
        async def stop_viewer(
            current_user: User = Depends(self._get_current_user)
        ):
            """Stop the viewer server."""
            try:
                if not self.viewer_running:
                    return {"success": False, "message": "Viewer server is not running"}

                if self.viewer_process:
                    self.viewer_process.terminate()
                    self.viewer_process.wait(timeout=5)
                    self.viewer_process = None

                self.viewer_running = False
                logger.info("Stopped viewer server")

                return {"success": True, "message": "Viewer server stopped successfully"}

            except Exception as e:
                logger.error(f"Error stopping viewer server: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/viewer/status")
        async def get_viewer_status(
            current_user: User = Depends(self._get_current_user)
        ):
            """Get viewer server status."""
            return {
                "running": self.viewer_running,
                "port": self.viewer_port if self.viewer_running else None
            }

        @self.app.get("/api/qr")
        async def get_qr_code(
            current_user: User = Depends(self._get_current_user)
        ):
            """Generate QR code for viewer URL."""
            try:
                import qrcode

                # Get actual LAN IP address
                import socket
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                try:
                    # Connect to an external address (doesn't actually send data)
                    s.connect(('8.8.8.8', 80))
                    ip_address = s.getsockname()[0]
                except Exception:
                    # Fallback to hostname method
                    ip_address = socket.gethostbyname(socket.gethostname())
                finally:
                    s.close()

                # Generate viewer URL
                viewer_url = f"http://{ip_address}:{self.viewer_port}"

                # Generate QR code
                qr = qrcode.QRCode(
                    version=1,
                    error_correction=qrcode.constants.ERROR_CORRECT_L,
                    box_size=10,
                    border=4,
                )
                qr.add_data(viewer_url)
                qr.make(fit=True)

                # Create image
                img = qr.make_image(fill_color="black", back_color="white")

                # Convert to bytes
                img_io = io.BytesIO()
                img.save(img_io, 'PNG')
                img_io.seek(0)

                return StreamingResponse(img_io, media_type="image/png")

            except ImportError:
                raise HTTPException(
                    status_code=500,
                    detail="QR code library not installed. Run: pip install qrcode[pil]"
                )
            except Exception as e:
                logger.error(f"Error generating QR code: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/viewer-url")
        async def get_viewer_url(
            current_user: User = Depends(self._get_current_user)
        ):
            """Get viewer URL."""
            import socket
            # Get actual LAN IP address
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.connect(('8.8.8.8', 80))
                ip_address = s.getsockname()[0]
            except Exception:
                ip_address = socket.gethostbyname(socket.gethostname())
            finally:
                s.close()

            return {
                "url": f"http://{ip_address}:{self.viewer_port}",
                "port": self.viewer_port,
                "ip": ip_address
            }

        @self.app.get("/")
        async def root():
            """Serve admin dashboard."""
            static_path = Path(__file__).parent / "static" / "index.html"
            if not static_path.exists():
                return JSONResponse({
                    "message": "SeenSlide Admin Server",
                    "version": "1.0.0",
                    "docs": "/docs",
                })
            return FileResponse(static_path)

        # Mount static files
        static_dir = Path(__file__).parent / "static"
        if static_dir.exists():
            self.app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    def run(self):
        """Run the admin server."""
        import uvicorn
        logger.info(f"Starting admin server on {self.host}:{self.port}")
        print(f"\n{'='*70}")
        print(f"SeenSlide Admin Server Starting")
        print(f"{'='*70}")
        print(f"\nAccess the admin panel at:")
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
    """Run admin server standalone."""
    import argparse

    parser = argparse.ArgumentParser(description="SeenSlide Admin Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8081, help="Port to listen on")
    parser.add_argument("--viewer-port", type=int, default=8080, help="Viewer server port")
    parser.add_argument("--storage", default="/tmp/seenslide", help="Storage path")

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Create and run server
    server = AdminServer(
        storage_path=args.storage,
        host=args.host,
        port=args.port,
        viewer_port=args.viewer_port
    )
    server.run()


if __name__ == "__main__":
    main()
