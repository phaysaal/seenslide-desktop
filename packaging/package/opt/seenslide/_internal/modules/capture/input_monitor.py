"""Input event monitor for event-driven screen capture.

Monitors keyboard and mouse events to detect slide changes in presentations.
Uses Linux evdev to read from /dev/input devices. When a relevant input event
is detected (e.g., arrow key, page down, mouse click), signals the capture
daemon to capture a screenshot.
"""

import logging
import select
import threading
import time
from typing import Callable, List, Optional, Set

logger = logging.getLogger(__name__)

# Keys that typically indicate a slide change in presentation software
SLIDE_CHANGE_KEYCODES = None  # Populated on import if evdev is available


def _init_keycodes():
    """Initialize keycode constants from evdev."""
    global SLIDE_CHANGE_KEYCODES, ONCE_KEYCODES
    try:
        from evdev import ecodes
        # Keys that always trigger capture (slide navigation)
        SLIDE_CHANGE_KEYCODES = {
            ecodes.KEY_SPACE,
            ecodes.KEY_RIGHT,
            ecodes.KEY_LEFT,
            ecodes.KEY_UP,
            ecodes.KEY_DOWN,
            ecodes.KEY_PAGEDOWN,
            ecodes.KEY_PAGEUP,
            # Mouse buttons
            ecodes.BTN_LEFT,
            ecodes.BTN_RIGHT,
            # Vim-style navigation (H/J/K/L)
            ecodes.KEY_H,
            ecodes.KEY_J,
            ecodes.KEY_K,
            ecodes.KEY_L,
        }
        # Keys that only trigger capture once (first press per session)
        ONCE_KEYCODES = {
            ecodes.KEY_F5,     # Start slideshow (title slide)
            ecodes.KEY_TAB,    # Alt+Tab (handled with modifier check)
        }
    except ImportError:
        SLIDE_CHANGE_KEYCODES = set()
        ONCE_KEYCODES = set()


ONCE_KEYCODES = set()
_init_keycodes()


class InputMonitor:
    """Monitors input devices for slide-change events.

    Runs in a background thread, reading from /dev/input/event* devices
    via evdev. When a relevant key press or mouse click is detected,
    calls the provided callback to trigger a screen capture.
    """

    def __init__(
        self,
        on_trigger: Callable[[], None],
        capture_delay: float = 0.4,
        debounce_interval: float = 0.5,
        extra_keycodes: Optional[Set[int]] = None,
    ):
        """Initialize the input monitor.

        Args:
            on_trigger: Callback invoked when a capture should be triggered.
            capture_delay: Seconds to wait after input event before triggering
                          (lets slide transitions complete).
            debounce_interval: Minimum seconds between triggers to avoid
                              rapid-fire from held keys or quick clicks.
            extra_keycodes: Additional evdev keycodes to monitor beyond
                           the built-in slide-change set.
        """
        self._on_trigger = on_trigger
        self._capture_delay = capture_delay
        self._debounce_interval = debounce_interval
        self._keycodes = set(SLIDE_CHANGE_KEYCODES or set())
        if extra_keycodes:
            self._keycodes.update(extra_keycodes)

        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._paused = False
        self._stop_event = threading.Event()
        self._last_trigger_time = 0.0
        self._devices: list = []
        self._available = False  # Whether evdev monitoring is available
        self._fired_once_keys: Set[int] = set()  # Track once-only keys already fired
        self._alt_held = False  # Track Alt modifier state

    def start(self) -> bool:
        """Start monitoring input devices.

        Returns:
            True if started successfully, False if evdev is unavailable
            or no suitable input devices were found.
        """
        if self._running:
            logger.warning("Input monitor already running")
            return True

        try:
            import evdev
        except ImportError:
            logger.warning(
                "evdev not available - input monitoring disabled. "
                "Install python-evdev for event-driven capture."
            )
            return False

        # Find keyboard and mouse devices
        self._devices = self._find_input_devices()

        if not self._devices:
            logger.warning(
                "No accessible input devices found for monitoring. "
                "Ensure the user is in the 'input' group: "
                "sudo usermod -aG input $USER"
            )
            return False

        device_names = [d.name for d in self._devices]
        logger.info(
            f"Input monitor starting with {len(self._devices)} devices: "
            f"{device_names}"
        )

        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._monitor_loop,
            name="InputMonitor",
            daemon=True,
        )
        self._thread.start()
        self._available = True

        logger.info("Input monitor started")
        return True

    def stop(self) -> None:
        """Stop monitoring input devices."""
        if not self._running:
            return

        logger.info("Stopping input monitor...")
        self._running = False
        self._stop_event.set()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
            if self._thread.is_alive():
                logger.warning("Input monitor thread did not stop gracefully")

        # Close devices
        for device in self._devices:
            try:
                device.close()
            except Exception:
                pass
        self._devices = []

        logger.info("Input monitor stopped")

    def pause(self) -> None:
        """Pause monitoring (events are read but not acted on)."""
        self._paused = True
        logger.debug("Input monitor paused")

    def resume(self) -> None:
        """Resume monitoring after pause. Resets once-key tracking."""
        self._paused = False
        self._fired_once_keys.clear()
        logger.debug("Input monitor resumed (once-keys reset)")

    @property
    def is_available(self) -> bool:
        """Whether input monitoring is available and running."""
        return self._available and self._running

    def _find_input_devices(self) -> list:
        """Find keyboard and mouse input devices.

        Returns:
            List of evdev InputDevice objects that have relevant keys.
        """
        try:
            import evdev
        except ImportError:
            return []

        devices = []
        try:
            all_devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
        except Exception as e:
            logger.warning(f"Failed to list input devices: {e}")
            return []

        for device in all_devices:
            try:
                capabilities = device.capabilities(verbose=False)

                # Check if device has EV_KEY (key/button events)
                ev_key = evdev.ecodes.EV_KEY
                if ev_key not in capabilities:
                    device.close()
                    continue

                device_keys = set(capabilities[ev_key])

                # Check if this device has any of our target keys
                if device_keys & self._keycodes:
                    devices.append(device)
                    logger.debug(
                        f"Monitoring device: {device.name} ({device.path})"
                    )
                else:
                    device.close()

            except Exception as e:
                logger.debug(f"Skipping device {device.path}: {e}")
                try:
                    device.close()
                except Exception:
                    pass

        return devices

    def _monitor_loop(self) -> None:
        """Main monitoring loop. Reads events from all input devices."""
        try:
            import evdev
        except ImportError:
            return

        logger.debug("Input monitor loop started")

        # Build a fd -> device mapping for select
        fd_to_device = {dev.fd: dev for dev in self._devices}

        while self._running:
            try:
                # Use select with timeout so we can check _running periodically
                if not fd_to_device:
                    break

                readable, _, _ = select.select(
                    fd_to_device.keys(), [], [], 0.5
                )

                for fd in readable:
                    if not self._running:
                        break

                    device = fd_to_device.get(fd)
                    if not device:
                        continue

                    try:
                        for event in device.read():
                            if not self._running:
                                break
                            self._process_event(event, device)
                    except OSError as e:
                        # Device disconnected
                        logger.warning(
                            f"Device disconnected: {device.name} - {e}"
                        )
                        try:
                            device.close()
                        except Exception:
                            pass
                        del fd_to_device[fd]

            except Exception as e:
                if self._running:
                    logger.error(f"Error in input monitor loop: {e}")
                    time.sleep(0.5)

        logger.debug("Input monitor loop ended")

    def _process_event(self, event, device) -> None:
        """Process a single input event.

        Only acts on key-down events (value=1) for monitored keycodes.
        Key repeats (value=2) and key-up (value=0) are ignored.
        """
        try:
            import evdev
        except ImportError:
            return

        # Only handle key/button events
        if event.type != evdev.ecodes.EV_KEY:
            return

        # Track Alt modifier state (needed for Alt+Tab detection)
        if event.code in (evdev.ecodes.KEY_LEFTALT, evdev.ecodes.KEY_RIGHTALT):
            self._alt_held = event.value != 0  # held on down/repeat, released on up
            return

        # Only on key down (value=1), ignore repeats (value=2) and release (value=0)
        if event.value != 1:
            return

        # Skip if paused
        if self._paused:
            return

        # Check if it's a once-only key (F5, Alt+Tab)
        is_once_key = False
        if event.code in ONCE_KEYCODES:
            # Tab only counts with Alt held (Alt+Tab)
            if event.code == evdev.ecodes.KEY_TAB and not self._alt_held:
                return
            if event.code in self._fired_once_keys:
                logger.debug(f"Once-key already fired: {event.code}, ignoring")
                return
            is_once_key = True
        elif event.code not in self._keycodes:
            # Not a monitored key
            return

        # Debounce
        now = time.time()
        if now - self._last_trigger_time < self._debounce_interval:
            logger.debug(
                f"Debounced input event: {event.code} from {device.name}"
            )
            return

        self._last_trigger_time = now

        if is_once_key:
            self._fired_once_keys.add(event.code)
            logger.info(f"Once-key triggered: {event.code} from {device.name}")
        else:
            logger.debug(
                f"Slide-change input detected: keycode={event.code} "
                f"from {device.name}"
            )

        # Schedule capture after delay (in a separate thread to not block
        # the event reading loop)
        threading.Thread(
            target=self._delayed_trigger,
            daemon=True,
            name="InputTrigger",
        ).start()

    def _delayed_trigger(self) -> None:
        """Wait for capture_delay then call the trigger callback."""
        if self._capture_delay > 0:
            # Wait for slide transition to complete, but abort if stopped
            if self._stop_event.wait(timeout=self._capture_delay):
                return

        if self._running and not self._paused:
            try:
                self._on_trigger()
            except Exception as e:
                logger.error(f"Error in capture trigger callback: {e}")
