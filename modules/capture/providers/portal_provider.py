"""XDG Desktop Portal screen capture provider for Wayland.

This provider uses the XDG Desktop Portal ScreenCast API to capture screens
on Wayland compositors. It provides silent, continuous capture via PipeWire.

Key features:
- Silent operation (after initial one-time permission)
- Continuous capture via PipeWire stream
- GPU-accelerated (minimal CPU usage)
- No interruption to other applications
- Works across all Wayland compositors

Requirements:
- python3-dbus (system package)
- python3-gi (system package)
- GStreamer with pipewiresrc plugin
"""

import logging
import time
import threading
import uuid
from typing import Optional, List, Dict, Callable, Tuple
from pathlib import Path
from PIL import Image
import io

# D-Bus and GObject imports
try:
    import dbus
    from dbus.mainloop.glib import DBusGMainLoop
    import gi
    gi.require_version('Gst', '1.0')
    gi.require_version('GLib', '2.0')
    from gi.repository import Gst, GLib
    PORTAL_AVAILABLE = True
except ImportError as e:
    PORTAL_AVAILABLE = False
    IMPORT_ERROR = str(e)

from core.interfaces.capture import ICaptureProvider, CaptureError
from core.models.slide import RawCapture

logger = logging.getLogger(__name__)


class PortalCaptureProvider(ICaptureProvider):
    """Screen capture provider using XDG Desktop Portal.

    This provider captures screens on Wayland using the standardized
    XDG Desktop Portal ScreenCast API with PipeWire backend.
    """

    def __init__(self):
        """Initialize the portal capture provider."""
        if not PORTAL_AVAILABLE:
            raise ImportError(
                f"Portal provider requires system packages: {IMPORT_ERROR}\n"
                "Install: sudo apt install python3-dbus python3-gi gstreamer1.0-pipewire"
            )

        self._config = {}
        self._initialized = False

        # D-Bus objects
        self._bus = None
        self._portal = None
        self._screencast_iface = None

        # Session management
        self._session_handle = None
        self._restore_token = None

        # PipeWire stream
        self._pipewire_node_id = None
        self._stream_active = False

        # GStreamer pipeline
        self._pipeline = None
        self._loop = None
        self._loop_thread = None

        # Frame capture
        self._latest_frame = None
        self._frame_lock = threading.Lock()
        self._frame_callback = None

        # Async response handling
        self._response_received = threading.Event()
        self._response_data = None
        self._response_code = None

        # Initialize GStreamer
        Gst.init(None)

        # Initialize D-Bus main loop
        DBusGMainLoop(set_as_default=True)

    def _get_sender_token(self) -> str:
        """Generate valid sender token for portal requests.

        Returns:
            Token string in format required by portal
        """
        # Get our unique bus name (e.g., ":1.234")
        sender = self._bus.get_unique_name()
        # Portal expects tokens with sender prefix
        # Replace : and . with _ to make valid token
        sender_clean = sender.replace(':', '').replace('.', '_')
        token = f"{sender_clean}_{uuid.uuid4().hex[:8]}"
        return token

    def initialize(self, config: dict) -> bool:
        """Initialize the portal capture provider.

        Args:
            config: Dictionary containing provider configuration:
                - restore_token: str, token to restore previous permission
                - framerate: int, target framerate (default: 10)
                - cursor_mode: str, 'hidden', 'embedded', or 'metadata'

        Returns:
            True if initialization successful, False otherwise
        """
        try:
            self._config = config
            self._restore_token = config.get('restore_token')

            # Connect to session bus
            self._bus = dbus.SessionBus()

            # Get portal interface
            self._portal = self._bus.get_object(
                'org.freedesktop.portal.Desktop',
                '/org/freedesktop/portal/desktop'
            )

            self._screencast_iface = dbus.Interface(
                self._portal,
                'org.freedesktop.portal.ScreenCast'
            )

            self._initialized = True
            logger.info("Portal capture provider initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize portal provider: {e}")
            return False

    def _handle_response(self, response_code, results):
        """Handle async response from portal request.

        This is called by the D-Bus signal handler.

        Args:
            response_code: 0 = success, 1 = cancelled, 2 = other error
            results: Dictionary of response data
        """
        logger.debug(f"Response received: code={response_code}, results={results}")
        self._response_code = response_code
        self._response_data = results
        self._response_received.set()

    def _wait_for_response(self, timeout=30.0) -> Tuple[int, Dict]:
        """Wait for async response from portal.

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            Tuple of (response_code, response_data)

        Raises:
            TimeoutError: If response not received within timeout
        """
        if not self._response_received.wait(timeout):
            raise TimeoutError(f"Portal response not received within {timeout}s")

        code = self._response_code
        data = self._response_data

        # Reset for next request
        self._response_received.clear()
        self._response_code = None
        self._response_data = None

        return code, data

    def start_screencast(self, on_frame: Optional[Callable] = None) -> bool:
        """Start the screencast session.

        This must be called before capture() can work. It will show a
        permission dialog on first use.

        Args:
            on_frame: Optional callback for continuous frame delivery

        Returns:
            True if screencast started, False otherwise
        """
        if not self._initialized:
            logger.error("Provider not initialized")
            return False

        if self._stream_active:
            logger.warning("Screencast already active")
            return True

        try:
            self._frame_callback = on_frame

            # Start GLib main loop in background (needed for signals)
            if not self._loop:
                self._loop = GLib.MainLoop()
                self._loop_thread = threading.Thread(
                    target=self._loop.run,
                    daemon=True,
                    name="PortalGLibLoop"
                )
                self._loop_thread.start()
                time.sleep(0.1)  # Give loop time to start

            # Create session
            logger.info("Creating portal session...")
            if not self._create_session():
                return False

            # Select sources (screens to capture)
            logger.info("Selecting sources (permission dialog may appear)...")
            if not self._select_sources():
                return False

            # Start the stream
            logger.info("Starting stream...")
            if not self._start_stream():
                return False

            logger.info("Screencast started successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to start screencast: {e}", exc_info=True)
            return False

    def _create_session(self) -> bool:
        """Create a screencast session."""
        try:
            # Generate valid sender token
            session_token = self._get_sender_token()

            options = {
                'session_handle_token': session_token,
            }

            # Call CreateSession
            logger.debug(f"Calling CreateSession with token: {session_token}")
            request_path = self._screencast_iface.CreateSession(options)

            logger.debug(f"CreateSession request path: {request_path}")

            # Set up signal handler for this request
            request_obj = self._bus.get_object(
                'org.freedesktop.portal.Desktop',
                request_path
            )
            request_iface = dbus.Interface(
                request_obj,
                'org.freedesktop.portal.Request'
            )

            # Connect to Response signal
            request_iface.connect_to_signal('Response', self._handle_response)

            # Wait for response
            logger.debug("Waiting for CreateSession response...")
            code, results = self._wait_for_response(timeout=10.0)

            if code != 0:
                logger.error(f"CreateSession failed with code: {code}")
                return False

            # Extract session handle
            self._session_handle = results.get('session_handle')
            if not self._session_handle:
                logger.error("No session handle in response")
                return False

            logger.debug(f"Session created: {self._session_handle}")
            return True

        except TimeoutError:
            logger.error("CreateSession timed out")
            return False
        except Exception as e:
            logger.error(f"Failed to create session: {e}", exc_info=True)
            return False

    def _select_sources(self) -> bool:
        """Select sources (screens) to capture."""
        try:
            # Generate valid sender token
            request_token = self._get_sender_token()

            options = {
                'handle_token': request_token,
                'types': dbus.UInt32(1),  # 1 = monitor, 2 = window
                'multiple': dbus.Boolean(False),  # Single monitor
                'cursor_mode': dbus.UInt32(self._get_cursor_mode()),
                'persist_mode': dbus.UInt32(2),  # 2 = persist until explicitly revoked
            }

            # Add restore token if available (skip permission dialog)
            if self._restore_token:
                options['restore_token'] = self._restore_token
                logger.debug(f"Using restore token: {self._restore_token}")

            # Call SelectSources
            logger.debug(f"Calling SelectSources with token: {request_token}")
            request_path = self._screencast_iface.SelectSources(
                dbus.ObjectPath(self._session_handle),
                options
            )

            logger.debug(f"SelectSources request path: {request_path}")

            # Set up signal handler for this request
            request_obj = self._bus.get_object(
                'org.freedesktop.portal.Desktop',
                request_path
            )
            request_iface = dbus.Interface(
                request_obj,
                'org.freedesktop.portal.Request'
            )

            # Connect to Response signal
            request_iface.connect_to_signal('Response', self._handle_response)

            # Wait for response (this may take a while if user interaction needed)
            logger.debug("Waiting for SelectSources response (user may need to select screen)...")
            code, results = self._wait_for_response(timeout=120.0)  # 2 min for user interaction

            if code == 1:
                logger.error("User cancelled source selection")
                return False
            elif code != 0:
                logger.error(f"SelectSources failed with code: {code}")
                return False

            logger.debug("Sources selected successfully")
            return True

        except TimeoutError:
            logger.error("SelectSources timed out (user may not have responded)")
            return False
        except Exception as e:
            logger.error(f"Failed to select sources: {e}", exc_info=True)
            return False

    def _get_cursor_mode(self) -> int:
        """Get cursor mode from config."""
        mode = self._config.get('cursor_mode', 'hidden')
        modes = {
            'hidden': 1,
            'embedded': 2,
            'metadata': 4,
        }
        return modes.get(mode, 1)

    def _start_stream(self) -> bool:
        """Start the PipeWire stream."""
        try:
            # Generate valid sender token
            request_token = self._get_sender_token()

            options = {
                'handle_token': request_token,
            }

            # Call Start
            logger.debug(f"Calling Start with token: {request_token}")
            request_path = self._screencast_iface.Start(
                dbus.ObjectPath(self._session_handle),
                '',  # parent_window (empty for non-window apps)
                options
            )

            logger.debug(f"Start request path: {request_path}")

            # Set up signal handler for this request
            request_obj = self._bus.get_object(
                'org.freedesktop.portal.Desktop',
                request_path
            )
            request_iface = dbus.Interface(
                request_obj,
                'org.freedesktop.portal.Request'
            )

            # Connect to Response signal
            request_iface.connect_to_signal('Response', self._handle_response)

            # Wait for response
            logger.debug("Waiting for Start response...")
            code, results = self._wait_for_response(timeout=10.0)

            if code != 0:
                logger.error(f"Start failed with code: {code}")
                return False

            # Get streams info
            streams = results.get('streams', [])
            if not streams:
                logger.error("No streams available in response")
                return False

            # Get node ID from first stream
            # Stream format: (node_id, properties_dict)
            self._pipewire_node_id = streams[0][0]

            # Get restore token for future use
            restore_token = results.get('restore_token')
            if restore_token:
                self._restore_token = restore_token
                logger.info(f"Got restore token for future sessions: {restore_token}")
                logger.info("Save this to config for silent operation next time!")

            logger.info(f"PipeWire node ID: {self._pipewire_node_id}")

            # Start GStreamer pipeline
            return self._start_gstreamer_pipeline()

        except TimeoutError:
            logger.error("Start timed out")
            return False
        except Exception as e:
            logger.error(f"Failed to start stream: {e}", exc_info=True)
            return False

    def _start_gstreamer_pipeline(self) -> bool:
        """Start GStreamer pipeline to consume PipeWire stream."""
        try:
            # Build pipeline
            # pipewiresrc captures from PipeWire node
            # videoconvert ensures proper format
            # appsink allows us to grab frames
            pipeline_str = (
                f"pipewiresrc path={self._pipewire_node_id} do-timestamp=true ! "
                "queue ! "
                "videoconvert ! "
                "video/x-raw,format=RGB ! "
                "appsink name=sink emit-signals=true max-buffers=1 drop=true"
            )

            logger.debug(f"Creating GStreamer pipeline: {pipeline_str}")
            self._pipeline = Gst.parse_launch(pipeline_str)

            # Get appsink and connect to new-sample signal
            appsink = self._pipeline.get_by_name('sink')
            appsink.connect('new-sample', self._on_new_sample)

            # Start pipeline
            ret = self._pipeline.set_state(Gst.State.PLAYING)
            if ret == Gst.StateChangeReturn.FAILURE:
                logger.error("Failed to start GStreamer pipeline")
                return False

            self._stream_active = True
            logger.info("GStreamer pipeline started successfully")

            # Wait a bit for first frame
            time.sleep(0.5)

            return True

        except Exception as e:
            logger.error(f"Failed to start GStreamer pipeline: {e}", exc_info=True)
            return False

    def _on_new_sample(self, appsink):
        """Callback when new frame is available from GStreamer."""
        try:
            # Pull sample from appsink
            sample = appsink.emit('pull-sample')
            if not sample:
                return Gst.FlowReturn.OK

            # Get buffer
            buffer = sample.get_buffer()
            caps = sample.get_caps()

            # Get frame dimensions
            structure = caps.get_structure(0)
            width = structure.get_value('width')
            height = structure.get_value('height')

            # Map buffer to read data
            success, map_info = buffer.map(Gst.MapFlags.READ)
            if not success:
                return Gst.FlowReturn.ERROR

            try:
                # Convert to PIL Image
                image_data = map_info.data
                image = Image.frombytes('RGB', (width, height), image_data)

                # Store latest frame
                with self._frame_lock:
                    self._latest_frame = image

                # Call frame callback if provided
                if self._frame_callback:
                    try:
                        self._frame_callback(image)
                    except Exception as e:
                        logger.error(f"Error in frame callback: {e}")

            finally:
                buffer.unmap(map_info)

            return Gst.FlowReturn.OK

        except Exception as e:
            logger.error(f"Error processing frame: {e}")
            return Gst.FlowReturn.ERROR

    def capture(self, monitor_id: Optional[int] = None) -> RawCapture:
        """Capture a screenshot from the active screencast.

        Args:
            monitor_id: Ignored (portal captures selected sources)

        Returns:
            RawCapture object containing the captured image

        Raises:
            CaptureError: If capture fails
        """
        if not self._stream_active:
            raise CaptureError(
                "Screencast not active. Call start_screencast() first."
            )

        # Get latest frame
        with self._frame_lock:
            if self._latest_frame is None:
                raise CaptureError("No frames available yet (stream starting up)")

            image = self._latest_frame.copy()

        # Create RawCapture object
        timestamp = time.time()
        capture = RawCapture(
            image=image,
            timestamp=timestamp,
            monitor_id=monitor_id or 0,
            width=image.width,
            height=image.height,
            metadata={
                "provider": self.name,
                "pipewire_node": self._pipewire_node_id,
                "session": self._session_handle,
            }
        )

        logger.debug(
            f"Captured frame: {capture.width}x{capture.height}"
        )
        return capture

    def stop_screencast(self) -> bool:
        """Stop the screencast session."""
        if not self._stream_active:
            logger.debug("Screencast not active, nothing to stop")
            return True

        try:
            # Stop GStreamer pipeline
            if self._pipeline:
                self._pipeline.set_state(Gst.State.NULL)
                self._pipeline = None

            self._stream_active = False
            self._pipewire_node_id = None

            with self._frame_lock:
                self._latest_frame = None

            logger.info("Screencast stopped")
            return True

        except Exception as e:
            logger.error(f"Error stopping screencast: {e}")
            return False

    def list_monitors(self) -> List[Dict]:
        """List available monitors.

        Note: Portal API doesn't provide monitor enumeration before
        starting a session. This returns a placeholder.

        Returns:
            List with single entry representing portal capture
        """
        return [{
            "id": 0,
            "name": "Portal ScreenCast",
            "x": 0,
            "y": 0,
            "width": 0,  # Unknown until stream starts
            "height": 0,
        }]

    def cleanup(self) -> None:
        """Clean up resources used by the capture provider."""
        try:
            self.stop_screencast()

            # Stop GLib main loop
            if self._loop:
                self._loop.quit()
                if self._loop_thread and self._loop_thread.is_alive():
                    self._loop_thread.join(timeout=2.0)
                self._loop = None
                self._loop_thread = None

            self._initialized = False
            logger.debug("Portal capture provider cleaned up")
        except Exception as e:
            logger.warning(f"Error during cleanup: {e}")

    @property
    def name(self) -> str:
        """Provider name."""
        return "portal"

    @property
    def supported_platforms(self) -> List[str]:
        """List of supported platforms."""
        return ["linux"]  # Wayland compositors

    @property
    def restore_token(self) -> Optional[str]:
        """Get the restore token to save for future use."""
        return self._restore_token

    @property
    def is_active(self) -> bool:
        """Check if screencast is active."""
        return self._stream_active

    def __del__(self):
        """Destructor to ensure cleanup."""
        self.cleanup()
