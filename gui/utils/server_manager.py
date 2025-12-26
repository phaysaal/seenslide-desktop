"""Admin server subprocess management."""

import subprocess
import sys
import time
import logging
import requests
from pathlib import Path
from typing import Optional, Dict, Any
import signal
import os

logger = logging.getLogger(__name__)


class ServerManager:
    """Manages admin server subprocess and API communication."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8081,
        startup_timeout: int = 30
    ):
        """Initialize server manager.

        Args:
            host: Server host (default: 127.0.0.1)
            port: Server port (default: 8081)
            startup_timeout: Seconds to wait for server startup (default: 30)
        """
        self.host = host
        self.port = port
        self.startup_timeout = startup_timeout
        self.base_url = f"http://{host}:{port}"

        self.process: Optional[subprocess.Popen] = None
        self.session_token: Optional[str] = None

        logger.info(f"ServerManager initialized for {self.base_url}")

    def start_server(self) -> bool:
        """Start the admin server subprocess.

        Returns:
            True if server started successfully, False otherwise
        """
        if self.is_running():
            logger.warning("Server is already running")
            return True

        try:
            # Get path to seenslide_admin.py
            project_root = Path(__file__).parent.parent.parent
            admin_script = project_root / "seenslide_admin.py"

            if not admin_script.exists():
                logger.error(f"Admin script not found: {admin_script}")
                return False

            # Start server process
            python_exec = sys.executable
            logger.info(f"Starting admin server: {python_exec} {admin_script}")

            self.process = subprocess.Popen(
                [python_exec, str(admin_script)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,  # Create new process group
                cwd=str(project_root)
            )

            # Wait for server to become ready
            logger.info(f"Waiting for server to start (timeout: {self.startup_timeout}s)...")
            start_time = time.time()

            while time.time() - start_time < self.startup_timeout:
                if self.is_server_ready():
                    logger.info("✅ Admin server started successfully")
                    return True

                # Check if process died
                if self.process.poll() is not None:
                    stderr = self.process.stderr.read().decode() if self.process.stderr else ""
                    logger.error(f"Server process died during startup: {stderr}")
                    return False

                time.sleep(0.5)

            # Timeout
            logger.error("Server startup timeout")
            self.stop_server()
            return False

        except Exception as e:
            logger.error(f"Failed to start server: {e}")
            return False

    def stop_server(self) -> bool:
        """Stop the admin server subprocess.

        Returns:
            True if stopped successfully, False otherwise
        """
        if not self.process:
            logger.warning("No server process to stop")
            return True

        try:
            logger.info("Stopping admin server...")

            # Try graceful shutdown first
            self.process.terminate()

            # Wait up to 5 seconds for graceful shutdown
            try:
                self.process.wait(timeout=5)
                logger.info("Server stopped gracefully")
            except subprocess.TimeoutExpired:
                # Force kill if graceful shutdown fails
                logger.warning("Graceful shutdown timeout, forcing kill")
                self.process.kill()
                self.process.wait()
                logger.info("Server force killed")

            self.process = None
            self.session_token = None
            return True

        except Exception as e:
            logger.error(f"Error stopping server: {e}")
            return False

    def is_running(self) -> bool:
        """Check if server process is running.

        Returns:
            True if running, False otherwise
        """
        if not self.process:
            return False

        # Check if process is still alive
        return self.process.poll() is None

    def is_server_ready(self) -> bool:
        """Check if server is ready to accept requests.

        Returns:
            True if server is responding, False otherwise
        """
        try:
            response = requests.get(
                f"{self.base_url}/api/auth/me",
                timeout=2
            )
            # Server is ready if we get any response (even 401 unauthorized)
            return True
        except:
            return False

    def login(self, username: str, password: str) -> bool:
        """Login to admin server.

        Args:
            username: Admin username
            password: Admin password

        Returns:
            True if login successful, False otherwise
        """
        try:
            response = requests.post(
                f"{self.base_url}/api/auth/login",
                json={"username": username, "password": password},
                timeout=5
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    # Extract session token from cookies
                    self.session_token = response.cookies.get("session_token")
                    logger.info("✅ Login successful")
                    return True
                else:
                    # Login failed, log the message
                    message = data.get("message", "Unknown error")
                    logger.error(f"Login failed: {message}")
                    return False

            logger.error(f"Login failed with status {response.status_code}: {response.text}")
            return False

        except Exception as e:
            logger.error(f"Login error: {e}")
            return False

    def set_crop_region(self, region: Optional[Dict[str, int]]) -> bool:
        """Set crop region via API.

        Args:
            region: Region dictionary or None to disable

        Returns:
            True if set successfully, False otherwise
        """
        if not self.session_token:
            logger.error("Not logged in")
            return False

        try:
            cookies = {"session_token": self.session_token}
            response = requests.post(
                f"{self.base_url}/api/crop-region",
                json={"crop_region": region},
                cookies=cookies,
                timeout=5
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    logger.info(f"✅ Crop region set: {region}")
                    return True

            logger.error(f"Failed to set crop region: {response.text}")
            return False

        except Exception as e:
            logger.error(f"Error setting crop region: {e}")
            return False

    def start_talk(
        self,
        name: str,
        presenter_name: str = "",
        description: str = "",
        monitor_id: int = 1,
        dedup_tolerance: float = 0.50
    ) -> Optional[str]:
        """Start a talk via API.

        Args:
            name: Talk name
            presenter_name: Presenter name
            description: Talk description
            monitor_id: Monitor to capture
            dedup_tolerance: Deduplication tolerance (0.0-1.0)

        Returns:
            Session ID if successful, None otherwise
        """
        if not self.session_token:
            logger.error("Not logged in")
            return None

        try:
            cookies = {"session_token": self.session_token}
            response = requests.post(
                f"{self.base_url}/api/sessions/start",
                json={
                    "name": name,
                    "presenter_name": presenter_name,
                    "description": description,
                    "monitor_id": monitor_id,
                    "dedup_tolerance": dedup_tolerance
                },
                cookies=cookies,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    session_id = data.get("session_id")
                    logger.info(f"✅ Talk started: {name} (session: {session_id})")
                    return session_id

            logger.error(f"Failed to start talk: {response.text}")
            return None

        except Exception as e:
            logger.error(f"Error starting talk: {e}")
            return None

    def stop_talk(self) -> bool:
        """Stop current talk via API.

        Returns:
            True if stopped successfully, False otherwise
        """
        if not self.session_token:
            logger.error("Not logged in")
            return False

        try:
            cookies = {"session_token": self.session_token}
            response = requests.post(
                f"{self.base_url}/api/sessions/stop",
                cookies=cookies,
                timeout=5
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    logger.info("✅ Talk stopped")
                    return True

            logger.error(f"Failed to stop talk: {response.text}")
            return False

        except Exception as e:
            logger.error(f"Error stopping talk: {e}")
            return False

    def get_status(self) -> Optional[Dict[str, Any]]:
        """Get server status via API.

        Returns:
            Status dictionary if successful, None otherwise
        """
        if not self.session_token:
            logger.error("Not logged in")
            return None

        try:
            cookies = {"session_token": self.session_token}
            response = requests.get(
                f"{self.base_url}/api/sessions/status",
                cookies=cookies,
                timeout=5
            )

            if response.status_code == 200:
                return response.json()

            logger.error(f"Failed to get status: {response.text}")
            return None

        except Exception as e:
            logger.error(f"Error getting status: {e}")
            return None

    def cleanup(self):
        """Cleanup resources."""
        if self.is_running():
            self.stop_server()
