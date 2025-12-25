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
import yaml
from typing import Optional, Dict
from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, HTTPException, Depends, Cookie, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from core.models.user import User
from core.models.capture_mode import CaptureMode
from core.auth.auth_utils import AuthUtils, SessionManager
from core.session.persistent_session_manager import PersistentSessionManager
from modules.storage.user_storage import UserStorage
from modules.storage.providers.sqlite_provider import SQLiteStorageProvider
from modules.storage.providers.cloud_provider import CloudStorageProvider
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

        # Load configuration file
        self.config = self._load_config()

        # Initialize FastAPI app
        self.app = FastAPI(
            title="SeenSlide Admin",
            description="Admin interface for SeenSlide",
            version="1.0.0"
        )

        # Add CORS middleware - restrict to localhost and local network
        # Note: Same-origin requests (from served frontend) don't need CORS
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=[
                "http://localhost:8081",
                "http://127.0.0.1:8081",
                f"http://localhost:{port}",
                f"http://127.0.0.1:{port}",
            ],
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Content-Type", "Authorization", "Cookie"],
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

        # Persistent session manager
        self.persistent_session_manager = PersistentSessionManager()
        self.persistent_session = self.persistent_session_manager.load_or_create_session(
            default_name="SeenSlide Session"
        )
        logger.info(f"Persistent session loaded: {self.persistent_session['session_id']}")

        # Cloud storage provider (for persistent session)
        self.cloud_provider = CloudStorageProvider()
        if self.config.get('cloud'):
            self.cloud_provider.initialize(self.config['cloud'])
            # Create cloud session immediately
            self._create_persistent_cloud_session()

        # Current local session (auto-created on startup)
        self.current_session_id: Optional[str] = None
        self._create_fresh_local_session()

        # Persistent idle capture orchestrator
        self.idle_orchestrator: Optional[SeenSlideOrchestrator] = None

        # Active talk session info
        self.active_session_id: Optional[str] = None
        self.active_talk_name: Optional[str] = None

        # Viewer server process
        self.viewer_process = None
        self.viewer_running = False

        # Setup routes
        self._setup_routes()

        # Start idle capture to trigger screen permission dialog once on startup
        self._start_idle_capture()

        logger.info(f"Admin server initialized at {host}:{port}")

    def _load_config(self) -> Dict:
        """Load configuration from file.

        Returns:
            Configuration dictionary
        """
        # Try user config first, then dev config, then defaults
        config_path = Path.home() / ".config" / "seenslide" / "config.yaml"
        if not config_path.exists():
            config_path = Path(__file__).parent.parent.parent / "dev" / "config_wayland.yaml"
            if not config_path.exists():
                config_path = None

        if config_path and config_path.exists():
            try:
                with open(config_path, 'r') as f:
                    config = yaml.safe_load(f)
                    logger.info(f"Loaded config from: {config_path}")
                    return config
            except Exception as e:
                logger.error(f"Failed to load config: {e}")

        # Return defaults
        return {}

    def _generate_session_name(self) -> str:
        """Generate a recognizable session name like 'AUY-2481'."""
        import random
        import string

        # 3 letters + 4 digits, e.g., 'AUY-2481'
        letters = ''.join(random.choices(string.ascii_uppercase, k=3))
        numbers = ''.join(random.choices(string.digits, k=4))
        return f"{letters}-{numbers}"

    def _create_fresh_local_session(self) -> None:
        """Create a fresh local session on startup."""
        try:
            from core.models.session import Session

            # Generate recognizable session name
            session_name = self._generate_session_name()

            # Create new session
            new_session = Session(
                name=session_name,
                description="Created on startup",
                presenter_name="Admin",
                status="created"
            )

            session_id = self.db_provider.create_session(new_session)
            self.current_session_id = session_id

            logger.info(f"✅ Created fresh local session on startup: {session_id} ({session_name})")
        except Exception as e:
            logger.error(f"Error creating fresh local session: {e}", exc_info=True)

    def _create_persistent_cloud_session(self) -> None:
        """Create cloud session for persistent session on startup."""
        if not self.cloud_provider.enabled:
            logger.info("Cloud sync disabled, skipping cloud session creation")
            return

        # Check if cloud session already exists
        if self.persistent_session.get('cloud_session_id'):
            logger.info(f"Cloud session already exists: {self.persistent_session['cloud_session_id']}")
            # Verify it's still valid or create new one
            # For now, we'll keep the existing one
            self.cloud_provider.cloud_session_id = self.persistent_session['cloud_session_id']
            return

        # Create new cloud session
        try:
            session_name = self.persistent_session.get('session_name', 'SeenSlide Session')
            cloud_session_id = self.cloud_provider.start_session(
                session_id=self.persistent_session['session_id'],
                session_name=session_name,
                description="Persistent session for multiple talks",
                presenter_name="Admin"
            )

            if cloud_session_id:
                # Update persistent session with cloud ID
                self.persistent_session_manager.update_cloud_session_id(cloud_session_id)
                self.persistent_session['cloud_session_id'] = cloud_session_id
                logger.info(f"✅ Cloud session created on startup: {cloud_session_id}")
                logger.info(f"📺 Viewer URL: {self.cloud_provider.api_url}/{cloud_session_id}")
            else:
                logger.warning("Failed to create cloud session on startup")
        except Exception as e:
            logger.error(f"Error creating cloud session on startup: {e}", exc_info=True)

    def _start_idle_capture(self) -> None:
        """Start idle mode capture to keep portal session alive."""
        try:
            logger.info("Starting idle mode capture...")

            # Create orchestrator in IDLE mode
            config_path = Path.home() / ".config" / "seenslide" / "config.yaml"
            if not config_path.exists():
                config_path = Path(__file__).parent.parent.parent / "dev" / "config_wayland.yaml"
                if not config_path.exists():
                    config_path = None

            self.idle_orchestrator = SeenSlideOrchestrator(
                config_path=str(config_path) if config_path else None
            )

            # Inject FULL cloud config with persistent session ID
            if self.cloud_provider.enabled and self.cloud_provider.cloud_session_id:
                # Copy entire cloud config from self.config, then add existing_session_id
                if 'cloud' not in self.idle_orchestrator.config:
                    self.idle_orchestrator.config['cloud'] = {}

                # Copy cloud settings from loaded config
                cloud_config = self.config.get('cloud', {})
                self.idle_orchestrator.config['cloud'].update(cloud_config)

                # Inject persistent cloud session ID
                self.idle_orchestrator.config['cloud']['existing_session_id'] = self.cloud_provider.cloud_session_id

                logger.info(f"Injected full cloud config with session ID: {self.cloud_provider.cloud_session_id}")

            # Start in IDLE mode
            success = self.idle_orchestrator.start_session(
                session_name="Idle Capture",
                description="Keeping portal session alive",
                presenter_name="System",
                monitor_id=1,
                mode=CaptureMode.IDLE
            )

            if success:
                logger.info("✅ Idle mode capture started - portal permission will be requested once")
            else:
                logger.warning("Failed to start idle capture - permission dialogs may appear for each talk")
                self.idle_orchestrator = None

        except Exception as e:
            logger.error(f"Error starting idle capture: {e}", exc_info=True)
            self.idle_orchestrator = None

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

        # Persistent Session Endpoints
        @self.app.get("/api/persistent-session")
        async def get_persistent_session(
            current_user: User = Depends(self._get_current_user)
        ):
            """Get persistent session information."""
            cloud_url = None
            if self.cloud_provider.cloud_session_id:
                cloud_url = f"{self.cloud_provider.api_url}/{self.cloud_provider.cloud_session_id}"

            return {
                "session_id": self.persistent_session['session_id'],
                "session_name": self.persistent_session['session_name'],
                "created_at": self.persistent_session['created_at'],
                "last_reset": self.persistent_session.get('last_reset'),
                "cloud_session_id": self.cloud_provider.cloud_session_id,
                "cloud_api_url": self.cloud_provider.api_url,
                "cloud_viewer_url": cloud_url,
                "cloud_enabled": self.cloud_provider.enabled
            }

        @self.app.post("/api/persistent-session/reset")
        async def reset_persistent_session(
            current_user: User = Depends(self._get_current_user)
        ):
            """Reset persistent session with new ID."""
            try:
                # Store old session ID for cleanup
                old_session_id = self.persistent_session.get('session_id')

                # Reset persistent session
                self.persistent_session = self.persistent_session_manager.reset_session()
                logger.info(f"Persistent session reset to: {self.persistent_session['session_id']}")

                # Auto-delete old session if it has no talks/slides
                if old_session_id:
                    try:
                        slide_count = self.db_provider.get_slide_count(old_session_id)
                        if slide_count == 0:
                            self.db_provider.delete_session(old_session_id)
                            logger.info(f"✅ Auto-deleted empty previous session: {old_session_id}")
                    except Exception as e:
                        logger.warning(f"Failed to auto-delete previous session {old_session_id}: {e}")

                # Create new cloud session if enabled
                if self.cloud_provider.enabled:
                    session_name = self.persistent_session.get('session_name', 'SeenSlide Session')
                    cloud_session_id = self.cloud_provider.start_session(
                        session_id=self.persistent_session['session_id'],
                        session_name=session_name,
                        description="Persistent session for multiple talks",
                        presenter_name="Admin"
                    )

                    if cloud_session_id:
                        self.persistent_session_manager.update_cloud_session_id(cloud_session_id)
                        self.persistent_session['cloud_session_id'] = cloud_session_id
                        logger.info(f"✅ New cloud session created: {cloud_session_id}")

                return {
                    "success": True,
                    "message": "Persistent session reset successfully",
                    "session_id": self.persistent_session['session_id'],
                    "cloud_session_id": self.cloud_provider.cloud_session_id
                }
            except Exception as e:
                logger.error(f"Failed to reset persistent session: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/sessions")
        async def list_sessions(
            current_user: User = Depends(self._get_current_user)
        ):
            """List all capture sessions (excluding idle capture sessions)."""
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
                    if s.name != "Idle Capture"  # Filter out temporary idle capture sessions
                ]
            except Exception as e:
                logger.error(f"Error listing sessions: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/api/sessions/start")
        async def start_session(
            request: SessionStartRequest,
            current_user: User = Depends(self._get_current_user)
        ):
            """Start a talk (switch from IDLE to ACTIVE mode)."""
            try:
                # Check if already in active talk
                if self.active_session_id:
                    return SessionControlResponse(
                        success=False,
                        message="A talk is already in progress. Please stop the current talk first."
                    )

                # Check if idle orchestrator exists
                if not self.idle_orchestrator or not self.idle_orchestrator.is_running():
                    return SessionControlResponse(
                        success=False,
                        message="Idle capture not running. Please restart admin server."
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

                # Create a new session for this talk
                from core.models.session import Session
                new_session = Session(
                    name=request.name,
                    description=request.description or "",
                    presenter_name=request.presenter_name or "Unknown",
                    capture_interval_seconds=self.idle_orchestrator.config.get("capture", {}).get("interval_seconds", 2.0),
                    dedup_strategy=self.idle_orchestrator.config.get("deduplication", {}).get("strategy", "hash")
                )

                logger.info(f"Created new session for talk: {request.name} ({new_session.session_id})")

                # Store the new session in the database
                self.db_provider.create_session(new_session)
                logger.info(f"Stored new session in database: {new_session.session_id}")

                # Create filesystem directories for the new session
                if self.idle_orchestrator.storage_manager:
                    if self.idle_orchestrator.storage_manager._filesystem:
                        self.idle_orchestrator.storage_manager._filesystem.create_session(new_session)
                        logger.info(f"Created filesystem directories for session: {new_session.session_id}")

                # Update the orchestrator to use this new session
                success = self.idle_orchestrator.update_session(new_session)
                if not success:
                    return SessionControlResponse(
                        success=False,
                        message="Failed to update session in orchestrator"
                    )

                # Update deduplication tolerance in config
                if 'deduplication' not in self.idle_orchestrator.config:
                    self.idle_orchestrator.config['deduplication'] = {}
                self.idle_orchestrator.config['deduplication']['perceptual_threshold'] = request.dedup_tolerance

                logger.info(f"Using deduplication perceptual threshold: {request.dedup_tolerance} "
                           f"(tolerance level: {int((1.0 - request.dedup_tolerance) * 100)}%)")

                # Switch to ACTIVE mode
                success = self.idle_orchestrator.set_capture_mode(CaptureMode.ACTIVE)
                if not success:
                    return SessionControlResponse(
                        success=False,
                        message="Failed to switch to active mode"
                    )

                # Store active talk info
                self.active_session_id = new_session.session_id
                self.active_talk_name = request.name

                logger.info(f"✅ Started talk '{request.name}' (switched to ACTIVE mode)")

                # Get cloud viewer URL
                viewer_url = None
                if self.cloud_provider.cloud_session_id:
                    viewer_url = f"{self.cloud_provider.api_url}/{self.cloud_provider.cloud_session_id}"
                    logger.info(f"📺 Cloud Viewer URL: {viewer_url}")

                message = f"Talk '{request.name}' started successfully"
                if viewer_url:
                    message += f"\n📺 Cloud Viewer: {viewer_url}"

                return SessionControlResponse(
                    success=True,
                    message=message,
                    session_id=self.active_session_id
                )

            except Exception as e:
                logger.error(f"Error starting talk: {e}", exc_info=True)
                # Try to switch back to idle on error
                if self.idle_orchestrator:
                    try:
                        self.idle_orchestrator.set_capture_mode(CaptureMode.IDLE)
                    except:
                        pass
                self.active_session_id = None
                self.active_talk_name = None
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/api/sessions/stop")
        async def stop_session(
            current_user: User = Depends(self._get_current_user)
        ):
            """Stop current talk (switch from ACTIVE to IDLE mode)."""
            try:
                if not self.active_session_id:
                    return SessionControlResponse(
                        success=False,
                        message="No active talk to stop"
                    )

                talk_name = self.active_talk_name
                session_id = self.active_session_id

                # Switch back to IDLE mode
                if self.idle_orchestrator and self.idle_orchestrator.is_running():
                    success = self.idle_orchestrator.set_capture_mode(CaptureMode.IDLE)
                    if success:
                        logger.info(f"✅ Stopped talk '{talk_name}' (switched back to IDLE mode)")
                    else:
                        logger.warning("Failed to switch to idle mode")
                else:
                    logger.warning("Idle orchestrator not running")

                # Clear active talk info
                self.active_session_id = None
                self.active_talk_name = None

                # Auto-delete session if it has no talks/slides
                slide_count = self.db_provider.get_slide_count(session_id)
                if slide_count == 0:
                    try:
                        self.db_provider.delete_session(session_id)
                        logger.info(f"✅ Auto-deleted empty session: {session_id}")
                    except Exception as e:
                        logger.warning(f"Failed to auto-delete empty session {session_id}: {e}")

                return SessionControlResponse(
                    success=True,
                    message=f"Talk '{talk_name}' stopped successfully",
                    session_id=session_id
                )

            except Exception as e:
                logger.error(f"Error stopping talk: {e}", exc_info=True)
                # Still clear the active session info
                self.active_session_id = None
                self.active_talk_name = None
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/sessions/status")
        async def get_session_status(
            current_user: User = Depends(self._get_current_user)
        ):
            """Get status of current talk."""
            # Get cloud session info (always available with persistent session)
            cloud_session_id = self.cloud_provider.cloud_session_id
            cloud_viewer_url = None
            if cloud_session_id:
                cloud_viewer_url = f"{self.cloud_provider.api_url}/{cloud_session_id}"

            # Check if idle orchestrator is running
            if not self.idle_orchestrator or not self.idle_orchestrator.is_running():
                return {
                    "active": False,
                    "session_id": None,
                    "idle_running": False,
                    "cloud_session_id": cloud_session_id,
                    "cloud_viewer_url": cloud_viewer_url
                }

            # Check if in active talk mode
            mode = self.idle_orchestrator.get_capture_mode()
            is_active = (mode == CaptureMode.ACTIVE and self.active_session_id is not None)

            if is_active:
                # Get statistics from idle orchestrator
                stats = self.idle_orchestrator.get_statistics()
                return {
                    "active": True,
                    "session_id": self.active_session_id,
                    "talk_name": self.active_talk_name,
                    "stats": stats,
                    "cloud_session_id": cloud_session_id,
                    "cloud_viewer_url": cloud_viewer_url
                }
            else:
                # In idle mode
                return {
                    "active": False,
                    "session_id": None,
                    "idle_running": True,
                    "cloud_session_id": cloud_session_id,
                    "cloud_viewer_url": cloud_viewer_url
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

        # ==================== Talks Management ====================

        @self.app.get("/api/sessions/{session_id}/talks")
        async def get_talks(
            session_id: str,
            current_user: User = Depends(self._get_current_user)
        ):
            """Get all talks for a session."""
            try:
                talks = self.db_provider.get_talks(session_id)
                return {"talks": talks, "total": len(talks)}
            except Exception as e:
                logger.error(f"Error getting talks: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/api/sessions/{session_id}/talks")
        async def create_talk(
            session_id: str,
            title: str,
            presenter_name: str = None,
            description: str = None,
            current_user: User = Depends(self._get_current_user)
        ):
            """Create a new talk in a session."""
            try:
                # Verify session exists
                session = self.db_provider.get_session(session_id)
                if not session:
                    raise HTTPException(status_code=404, detail="Session not found")

                talk_id = self.db_provider.create_talk(
                    session_id=session_id,
                    title=title,
                    presenter_name=presenter_name,
                    description=description
                )

                return {
                    "success": True,
                    "talk_id": talk_id,
                    "message": f"Talk '{title}' created successfully"
                }
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error creating talk: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.delete("/api/sessions/{session_id}/talks/{talk_id}")
        async def delete_talk(
            session_id: str,
            talk_id: str,
            current_user: User = Depends(self._get_current_user)
        ):
            """Delete a talk from a session."""
            try:
                success = self.db_provider.delete_talk(talk_id)
                if not success:
                    raise HTTPException(status_code=404, detail="Talk not found")

                logger.info(f"Deleted talk {talk_id} from session {session_id}")

                # Auto-delete session if it has no talks/slides left
                try:
                    slide_count = self.db_provider.get_slide_count(session_id)
                    if slide_count == 0:
                        self.db_provider.delete_session(session_id)
                        logger.info(f"✅ Auto-deleted empty session after deleting last talk: {session_id}")
                except Exception as e:
                    logger.warning(f"Failed to auto-delete empty session {session_id}: {e}")

                return {"success": True, "message": "Talk deleted successfully"}

            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error deleting talk: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        # ==================== Session Management ====================

        @self.app.patch("/api/sessions/{session_id}")
        async def update_session(
            session_id: str,
            name: Optional[str] = None,
            description: Optional[str] = None,
            presenter_name: Optional[str] = None,
            current_user: User = Depends(self._get_current_user)
        ):
            """Update session properties (name, description, presenter_name)."""
            try:
                session = self.db_provider.get_session(session_id)
                if not session:
                    raise HTTPException(status_code=404, detail="Session not found")

                # Update fields if provided
                if name is not None:
                    session.name = name
                if description is not None:
                    session.description = description
                if presenter_name is not None:
                    session.presenter_name = presenter_name

                # Save updated session
                success = self.db_provider.update_session(session)
                if not success:
                    raise HTTPException(status_code=500, detail="Failed to update session")

                logger.info(f"Updated session {session_id}: name={session.name}")
                return {
                    "success": True,
                    "message": "Session updated successfully",
                    "session": {
                        "session_id": session.session_id,
                        "name": session.name,
                        "description": session.description,
                        "presenter_name": session.presenter_name
                    }
                }

            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error updating session: {e}")
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
            """Generate QR code for viewer URL (persistent cloud session if available, otherwise local)."""
            try:
                import qrcode

                # Try to get persistent cloud URL first
                viewer_url = None
                if self.cloud_provider.cloud_session_id:
                    viewer_url = f"{self.cloud_provider.api_url}/{self.cloud_provider.cloud_session_id}"
                    logger.info(f"QR code for persistent cloud URL: {viewer_url}")

                # Fallback to local LAN URL if no cloud URL
                if not viewer_url:
                    import socket
                    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    try:
                        s.connect(('8.8.8.8', 80))
                        ip_address = s.getsockname()[0]
                    except Exception:
                        ip_address = socket.gethostbyname(socket.gethostname())
                    finally:
                        s.close()
                    viewer_url = f"http://{ip_address}:{self.viewer_port}"
                    logger.info(f"QR code for local URL: {viewer_url}")

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
            """Get viewer URL (persistent cloud session if available, otherwise local LAN)."""
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

            local_url = f"http://{ip_address}:{self.viewer_port}"

            # Get persistent cloud viewer URL if available
            cloud_url = None
            cloud_session_id = self.cloud_provider.cloud_session_id
            if cloud_session_id:
                cloud_url = f"{self.cloud_provider.api_url}/{cloud_session_id}"

            return {
                "url": cloud_url if cloud_url else local_url,  # Prefer cloud URL
                "local_url": local_url,
                "cloud_url": cloud_url,
                "port": self.viewer_port,
                "ip": ip_address,
                "cloud_session_id": cloud_session_id
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
