"""SeenSlide Pro Dashboard — Home, Setup, and Live Cockpit views.

Redesigned with:
- Personalized home screen with recent sessions
- Clean setup form with tips sidebar
- Information-dense live cockpit with stats, preview, and recent slides
"""

import time
import logging
import os
import datetime
import requests
from pathlib import Path
from typing import Optional, List

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QStackedWidget, QSizePolicy, QSpacerItem,
    QLineEdit, QTextEdit, QSlider, QGraphicsDropShadowEffect,
    QScrollArea, QFileDialog, QApplication, QMessageBox,
    QGridLayout, QDialog, QProgressBar, QComboBox
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread, QRectF
from PyQt5.QtGui import (
    QFont, QPixmap, QColor, QPainter, QPainterPath, QPen
)

from gui.utils import styles
from gui.widgets.countdown_widget import CountdownWidget
from gui.widgets.new_session_dialog import NewSessionDialog
from gui.widgets.sign_in_dialog import SignInDialog
from gui.widgets.edit_account_dialog import EditAccountDialog
from gui.widgets.nudge_dialog import NudgeDialog
from gui.widgets.region_selector import RegionSelector
from gui.utils.screenshot_util import (
    get_monitor_count, get_primary_screen_size, get_screen_info,
    capture_screenshot,
)
from gui.utils.region_utils import calculate_default_region, validate_region

import core.app_settings as app_settings

from seenslide.orchestrator import SeenSlideOrchestrator, CaptureMode
from core.session.collection_registry import CollectionRegistry, Collection
from core.session.credential_manager import CredentialManager
from core.cloud_sessions import CloudSessionsClient
from core.identity import identity
from core.nudge import NudgeState, NudgeTier
from core.interfaces.events import Event, EventType

logger = logging.getLogger(__name__)

# ── Design Tokens ──────────────────────────────────────────────────

SIDEBAR_BG = "#1a1f2e"
SIDEBAR_BG_BOTTOM = "#151927"
SIDEBAR_ACTIVE_BG = "rgba(59, 130, 246, 0.15)"
SIDEBAR_ACTIVE_BORDER = "#3b82f6"

BG_MAIN = "#f8fafc"
BG_WHITE = "#ffffff"
BG_INPUT = "#f8fafc"

BLUE = "#3b82f6"
BLUE_DARK = "#2563eb"
BLUE_LIGHT = "#eff6ff"
BLUE_PALE = "#93c5fd"
GREEN = "#10b981"
GREEN_DARK = "#059669"
GREEN_LIGHT = "#ecfdf5"
RED = "#ef4444"
RED_DARK = "#dc2626"
RED_LIGHT = "#fef2f2"

TEXT_DARK = "#1e293b"
TEXT_BODY = "#475569"
TEXT_MUTED = "#94a3b8"
TEXT_FAINT = "#64748b"
BORDER = "#e2e8f0"
CARD_BORDER = "#ecf0f1"


# ── Reusable Widgets ───────────────────────────────────────────────

class ShadowCard(QFrame):
    """White card with subtle drop shadow and optional top accent."""
    def __init__(self, parent=None, accent_color=None, radius=12):
        super().__init__(parent)
        self._radius = radius
        self.setObjectName("shadowCard")
        border_css = f"border-top: 3px solid {accent_color};" if accent_color else ""
        self.setStyleSheet(f"""
            QFrame#shadowCard {{
                background: {BG_WHITE};
                border: 1px solid {BORDER};
                border-radius: {radius}px;
                {border_css}
            }}
        """)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(16)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 20))
        self.setGraphicsEffect(shadow)


class SidebarButton(QPushButton):
    """Nav button with left accent bar when active."""
    def __init__(self, text, icon_char="", parent=None):
        super().__init__(text, parent)
        self.icon_char = icon_char
        self._active = False
        self.setCheckable(True)
        self.setFixedHeight(44)
        self.setCursor(Qt.PointingHandCursor)
        self.apply_style()

    @property
    def active(self):
        return self._active

    @active.setter
    def active(self, val):
        self._active = val
        self.apply_style()

    def apply_style(self):
        if self._active:
            self.setStyleSheet(f"""
                QPushButton {{
                    background: {SIDEBAR_ACTIVE_BG};
                    color: #e2e8f0;
                    border: none;
                    border-left: 3px solid {SIDEBAR_ACTIVE_BORDER};
                    border-radius: 8px;
                    padding-left: 16px;
                    text-align: left;
                    font-size: 13px;
                                   }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {TEXT_FAINT};
                    border: none;
                    padding-left: 20px;
                    text-align: left;
                    font-size: 13px;
                                       border-radius: 8px;
                }}
                QPushButton:hover {{
                    background: rgba(255,255,255,0.05);
                    color: #e2e8f0;
                }}
            """)


class StatCard(ShadowCard):
    """Stat card showing label + large value."""
    def __init__(self, label, value="0", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)

        self.lbl = QLabel(label)
        self.lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px; letter-spacing: 0.5px; background: transparent;")

        self.val = QLabel(value)
        self.val.setStyleSheet(f"color: {TEXT_DARK}; font-size: 22px; background: transparent;")

        layout.addWidget(self.lbl)
        layout.addWidget(self.val)


class RecentSessionRow(QFrame):
    """A row in the recent sessions list."""
    clicked = pyqtSignal(str)

    def __init__(self, title, subtitle, badge_color=BLUE, action_text="Resume", parent=None):
        super().__init__(parent)
        self.setFixedHeight(52)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(f"""
            QFrame {{
                background: {BG_WHITE};
                border: 1px solid {BORDER};
                border-radius: 8px;
            }}
            QFrame:hover {{
                border-color: {BLUE};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 16, 0)
        layout.setSpacing(12)

        # Badge circle
        badge = QLabel(title[0].upper() if title else "S")
        badge_bg = BLUE_LIGHT if badge_color == BLUE else GREEN_LIGHT
        badge_fg = BLUE if badge_color == BLUE else GREEN
        badge.setFixedSize(28, 28)
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet(f"""
            background: {badge_bg};
            color: {badge_fg};
            border-radius: 14px;
            font-size: 11px;
                   """)
        layout.addWidget(badge)

        # Text
        text_layout = QVBoxLayout()
        text_layout.setSpacing(1)
        t = QLabel(title)
        t.setStyleSheet(f"color: {TEXT_DARK}; font-size: 13px; background: transparent;")
        s = QLabel(subtitle)
        s.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; background: transparent;")
        text_layout.addWidget(t)
        text_layout.addWidget(s)
        layout.addLayout(text_layout, 1)

        # Action
        action = QLabel(action_text)
        action.setStyleSheet(f"color: {BLUE}; font-size: 11px; background: transparent;")
        layout.addWidget(action)


class SlideThumbnail(QFrame):
    """Small slide thumbnail for the recent slides panel."""
    def __init__(self, slide_num, is_current=False, parent=None):
        super().__init__(parent)
        self.setFixedSize(96, 68)
        border = f"2px solid {BLUE}" if is_current else f"1px solid {BORDER}"
        self.setStyleSheet(f"""
            QFrame {{
                background: {BG_WHITE};
                border: {border};
                border-radius: 6px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 2)
        layout.setSpacing(0)

        self.img_label = QLabel()
        self.img_label.setStyleSheet("background: #f1f5f9; border-radius: 3px;")
        self.img_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.img_label, 1)

        num = QLabel(str(slide_num))
        num_color = BLUE if is_current else TEXT_MUTED
        num.setStyleSheet(f"color: {num_color}; font-size: 9px; background: transparent;")
        num.setAlignment(Qt.AlignRight)
        layout.addWidget(num)


# ── Orchestrator Worker ────────────────────────────────────────────

class OrchestratorStartWorker(QThread):
    """Initialize orchestrator in a worker thread.

    The orchestrator is stored on the worker instance and retrieved
    from the main thread after `finished` signal fires, avoiding
    cross-thread QObject::setParent warnings.
    """
    ready = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, monitor_id, crop_region, collection=None):
        super().__init__()
        self.monitor_id = monitor_id
        self.crop_region = crop_region
        self.collection = collection
        self.orchestrator = None
        self.cloud_id = ""
        self.cloud_url = ""

    def run(self):
        try:
            import yaml

            # Find and load config file (same logic as direct_talk_window)
            config_paths = [
                Path.home() / ".config" / "seenslide" / "config.yaml",
                Path(__file__).parent.parent.parent / "config" / "config.yaml",
            ]
            config_path = None
            loaded_config = {}
            for path in config_paths:
                if path.exists():
                    config_path = path
                    with open(path, 'r') as f:
                        loaded_config = yaml.safe_load(f) or {}
                    break

            orch = SeenSlideOrchestrator(config_path=str(config_path) if config_path else None)

            # Inject the chosen monitor_id into the capture provider's config.
            # The orchestrator's start_session(monitor_id=...) parameter is a
            # dead pass-through — the mss provider reads its monitor from
            # capture.config.monitor_id at initialize() time. (Portal provider
            # ignores monitor_id and uses the user's portal-dialog selection.)
            if 'capture' not in orch.config:
                orch.config['capture'] = {}
            if 'config' not in orch.config['capture']:
                orch.config['capture']['config'] = {}
            orch.config['capture']['config']['monitor_id'] = self.monitor_id

            # Inject cloud settings from config file
            if 'cloud' not in orch.config:
                orch.config['cloud'] = {}
            cloud_config = loaded_config.get('cloud', {})
            orch.config['cloud'].update(cloud_config)

            # If collection exists, reuse its cloud ID
            if self.collection:
                orch.config['cloud']['existing_session_id'] = self.collection.cloud_collection_id
                logger.info(f"Reusing existing collection: {self.collection.cloud_collection_id}")

            session_name = self.collection.name if self.collection else "My Presentation"
            success = orch.start_session(
                session_name=f"{session_name} - Idle",
                monitor_id=self.monitor_id,
                mode=CaptureMode.IDLE,
                crop_region=self.crop_region
            )

            if not success:
                self.error.emit("Failed to start capture engine")
                return

            self.orchestrator = orch
            if orch.storage_manager._cloud.enabled:
                self.cloud_id = orch.storage_manager._cloud.cloud_session_id or ""
                self.cloud_url = f"{orch.storage_manager._cloud.api_url}/{self.cloud_id}"

            self.ready.emit()
        except Exception as e:
            logger.error(f"OrchestratorStartWorker failed: {e}", exc_info=True)
            self.error.emit(str(e))


class IdentityBootstrapWorker(QThread):
    """Background worker for the first-launch device-bootstrap call."""

    finished_ok = pyqtSignal()
    failed = pyqtSignal(str)

    def run(self):
        try:
            ok = identity().ensure_bootstrap()
            if ok:
                self.finished_ok.emit()
            else:
                self.failed.emit("Could not reach the cloud to register this device.")
        except Exception as e:
            logger.error(f"IdentityBootstrapWorker failed: {e}", exc_info=True)
            self.failed.emit(str(e))


class IdentityRefreshWorker(QThread):
    """Background worker for /api/auth/me/identity GET.

    Pulls the latest identity record (email/phone/full_name/is_anonymous)
    from the cloud so changes made on another device propagate. Runs off
    the main thread because the HTTP call has a 10s timeout — blocking the
    GUI for that long on a flaky network is unacceptable.
    """

    finished_ok = pyqtSignal()
    failed = pyqtSignal(str)

    def run(self):
        try:
            ok = identity().refresh_me()
            if ok:
                self.finished_ok.emit()
            else:
                self.failed.emit("Could not refresh identity from the cloud.")
        except Exception as e:
            logger.error(f"IdentityRefreshWorker failed: {e}", exc_info=True)
            self.failed.emit(str(e))


class CloudSessionsWorker(QThread):
    """Background worker for cloud session API calls."""

    finished_list = pyqtSignal(list)
    finished_create = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, client: CloudSessionsClient, op: str, **kwargs):
        super().__init__()
        self.client = client
        self.op = op
        self.kwargs = kwargs

    def run(self):
        try:
            if self.op == "list":
                self.finished_list.emit(self.client.list_sessions())
            elif self.op == "create":
                result = self.client.create_session(**self.kwargs)
                if result is None:
                    self.failed.emit("Failed to create session — check your network and token.")
                else:
                    self.finished_create.emit(result)
        except Exception as e:
            logger.error(f"CloudSessionsWorker {self.op} failed: {e}", exc_info=True)
            self.failed.emit(str(e))


# ── Main Dashboard ─────────────────────────────────────────────────

class MainDashboard(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SeenSlide Pro")
        self.resize(1100, 720)
        self.setStyleSheet(f"background-color: {BG_MAIN};")

        self.logo_path = str(Path(__file__).parent.parent / "resources" / "icons" / "logo.png")

        self.orchestrator: Optional[SeenSlideOrchestrator] = None
        self.collection_registry = CollectionRegistry()
        self.cloud_sessions_client = CloudSessionsClient()
        # List and create run as independent CloudSessionsWorkers. Sharing
        # one slot meant a slow list refresh blocked the "+ New" button —
        # the two operations don't actually conflict, so keep them on
        # separate refs and let each de-dupe only against its own kind.
        self._sessions_list_worker: Optional[CloudSessionsWorker] = None
        self._sessions_create_worker: Optional[CloudSessionsWorker] = None
        self._cloud_sessions_cache: list = []
        self.nudge_state = NudgeState.load()
        self._nudge_dialog_open = False
        self.start_time = 0
        self.is_active = False
        self.slide_count = 0

        self._build_ui()
        self._show_last_collection()
        # Identity bootstrap runs first; cloud sync waits for it to finish so
        # the bearer token is present before the first authenticated request.
        QTimer.singleShot(50, self._start_identity_bootstrap)
        QTimer.singleShot(100, self._init_orchestrator)

    # ── Identity bootstrap ─────────────────────────────────────────

    def _start_identity_bootstrap(self):
        """Bootstrap a device-anonymous account if no token cached, then
        kick off the cloud sessions sync once auth is valid."""
        ident = identity()
        if ident.is_authenticated:
            # Already have a cached token — refresh the user record in
            # the background and proceed straight to sessions sync.
            self._on_identity_ready()
            return

        self._identity_worker = IdentityBootstrapWorker()
        self._identity_worker.finished_ok.connect(self._on_identity_ready)
        self._identity_worker.failed.connect(self._on_identity_failed)
        self._identity_worker.start()

    def _on_identity_ready(self):
        """Auth is good — start the cloud session refresh."""
        ident = identity()
        if ident.is_anonymous:
            logger.info(
                f"Running as anonymous user {ident.record.user_id} "
                f"(device {ident.device_id[:8]}…)"
            )
        else:
            logger.info(f"Running as {ident.record.email or ident.record.phone_number}")
        # Refresh /me/identity in the background so changes from another
        # device propagate (e.g. user signed in on phone, secret rotated).
        # Off the main thread — the HTTP call's 10s timeout would otherwise
        # freeze the dashboard on a slow network.
        self._start_identity_refresh()
        # Now we can safely call /api/cloud/sessions
        QTimer.singleShot(200, self._refresh_sessions_list)
        # Check if a tier-B reminder is due (2+ days since last shown).
        QTimer.singleShot(800, self._evaluate_nudge)

    def _on_identity_failed(self, reason: str):
        logger.warning(f"Identity bootstrap failed: {reason}")
        # Try cloud sync anyway — it will fall through to local cache silently.
        QTimer.singleShot(200, self._refresh_sessions_list)

    def _start_identity_refresh(self):
        """Run identity().refresh_me() in a worker thread, then refresh the
        Account view from the main thread when it finishes. Safe to call
        from user-initiated paths (after sign-in, after edit-identifiers)
        and from background reconciliation."""
        if getattr(self, "_identity_refresh_worker", None) and self._identity_refresh_worker.isRunning():
            return  # one in-flight is enough; results are idempotent
        self._identity_refresh_worker = IdentityRefreshWorker()
        self._identity_refresh_worker.finished_ok.connect(self._refresh_account_view)
        self._identity_refresh_worker.failed.connect(
            lambda reason: logger.debug(f"identity refresh failed: {reason}")
        )
        self._identity_refresh_worker.start()

    # ── UI Construction ────────────────────────────────────────────

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_sidebar())

        # Content area
        content = QVBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)

        # Stacked views: Home -> Setup -> Live
        self.view_stack = QStackedWidget()
        self.view_stack.addWidget(self._build_home_view())      # 0
        self.view_stack.addWidget(self._build_setup_view())     # 1
        self.view_stack.addWidget(self._build_live_view())      # 2
        self.view_stack.addWidget(self._build_conference_view())  # 3
        self.view_stack.addWidget(self._build_sessions_view())    # 4
        self.view_stack.addWidget(self._build_account_view())     # 5

        content.addWidget(self.view_stack)
        root.addLayout(content)

    def _build_sidebar(self):
        sidebar = QFrame()
        sidebar.setFixedWidth(200)
        sidebar.setStyleSheet(f"background-color: {SIDEBAR_BG};")

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Logo
        logo_area = QHBoxLayout()
        logo_area.setContentsMargins(20, 24, 20, 28)
        logo_area.setSpacing(8)

        logo_lbl = QLabel()
        if os.path.exists(self.logo_path):
            logo_lbl.setPixmap(QPixmap(self.logo_path).scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            logo_lbl.setFixedSize(24, 24)
            logo_lbl.setStyleSheet(f"background: {BLUE}; border-radius: 12px;")

        brand = QLabel("SeenSlide")
        brand.setStyleSheet("color: #60a5fa; font-size: 18px; background: transparent;")
        logo_area.addWidget(logo_lbl)
        logo_area.addWidget(brand)
        logo_area.addStretch()
        layout.addLayout(logo_area)

        # Nav buttons
        nav_container = QVBoxLayout()
        nav_container.setContentsMargins(8, 0, 8, 0)
        nav_container.setSpacing(4)

        self.btn_home = SidebarButton("Home")
        self.btn_home.active = True
        self.btn_sessions = SidebarButton("Conference")
        self.btn_library = SidebarButton("Sessions")
        self.btn_account = SidebarButton("Account")

        self.nav_buttons = [self.btn_home, self.btn_sessions, self.btn_library, self.btn_account]
        nav_indices = [0, 3, 4, 5]  # Map to view_stack indices

        for btn, idx in zip(self.nav_buttons, nav_indices):
            btn.clicked.connect(lambda checked, i=idx: self._switch_view(i))
            nav_container.addWidget(btn)

        layout.addLayout(nav_container)
        layout.addStretch()

        # Live session indicator (hidden until active)
        self.sidebar_live_box = QFrame()
        self.sidebar_live_box.setFixedHeight(80)
        self.sidebar_live_box.setStyleSheet("background: rgba(255,255,255,0.04); border-radius: 8px; margin: 8px;")
        live_layout = QVBoxLayout(self.sidebar_live_box)
        live_layout.setContentsMargins(12, 8, 12, 8)
        live_layout.setSpacing(2)

        self.sidebar_session_label = QLabel("SESSION CODE")
        self.sidebar_session_label.setStyleSheet(f"color: {TEXT_FAINT}; font-size: 9px; letter-spacing: 0.5px; background: transparent;")
        self.sidebar_session_code = QLabel("")
        self.sidebar_session_code.setStyleSheet("color: #e2e8f0; font-size: 15px; letter-spacing: 2px; background: transparent;")
        self.sidebar_copy_link = QPushButton("Copy link")
        self.sidebar_copy_link.setCursor(Qt.PointingHandCursor)
        self.sidebar_copy_link.setStyleSheet(f"color: {BLUE}; font-size: 11px; border: none; text-align: left; background: transparent; text-decoration: underline;")

        live_layout.addWidget(self.sidebar_session_label)
        live_layout.addWidget(self.sidebar_session_code)
        live_layout.addWidget(self.sidebar_copy_link)
        self.sidebar_live_box.setVisible(False)
        layout.addWidget(self.sidebar_live_box)

        # Connection status
        status_frame = QFrame()
        status_frame.setFixedHeight(40)
        status_frame.setStyleSheet("background: rgba(16,185,129,0.1); border-radius: 6px; margin: 8px 12px 12px 12px;")
        status_layout = QHBoxLayout(status_frame)
        status_layout.setContentsMargins(10, 0, 10, 0)
        status_layout.setSpacing(6)

        self.status_dot = QLabel()
        self.status_dot.setFixedSize(8, 8)
        self.status_dot.setStyleSheet(f"background: {GREEN}; border-radius: 4px;")
        status_layout.addWidget(self.status_dot)

        self.status_text = QLabel("Server Connected")
        self.status_text.setStyleSheet(f"color: {GREEN}; font-size: 13px; background: transparent;")
        status_layout.addWidget(self.status_text)
        status_layout.addStretch()

        layout.addWidget(status_frame)

        return sidebar

    # ── Home View ──────────────────────────────────────────────────

    def _build_home_view(self):
        view = QWidget()
        view.setStyleSheet(f"background: {BG_MAIN};")

        layout = QVBoxLayout(view)
        layout.setContentsMargins(40, 32, 40, 32)
        layout.setSpacing(20)

        # Greeting
        greeting = self._get_greeting()
        title = QLabel(greeting)
        title.setStyleSheet(f"color: {TEXT_DARK}; font-size: 22px; background: transparent;")
        subtitle = QLabel("What would you like to do?")
        subtitle.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 13px; background: transparent;")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        # Active session banner (shown when orchestrator has a session)
        self.active_session_card = ShadowCard(accent_color=BLUE)
        self.active_session_card.setFixedHeight(64)
        as_layout = QHBoxLayout(self.active_session_card)
        as_layout.setContentsMargins(20, 0, 20, 0)
        as_layout.setSpacing(12)

        # Live dot
        as_dot = QLabel()
        as_dot.setFixedSize(10, 10)
        as_dot.setStyleSheet(f"background: {GREEN}; border-radius: 5px;")
        as_layout.addWidget(as_dot)

        # Session info
        as_info = QVBoxLayout()
        as_info.setSpacing(1)
        self.as_name = QLabel("—")
        self.as_name.setStyleSheet(f"color: {TEXT_DARK}; font-size: 13px; background: transparent;")
        self.as_id = QLabel("")
        self.as_id.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; background: transparent;")
        as_info.addWidget(self.as_name)
        as_info.addWidget(self.as_id)
        as_layout.addLayout(as_info, 1)

        # Label badge
        self.as_badge = QLabel("Current Session")
        self.as_badge.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; background: transparent;")
        as_layout.addWidget(self.as_badge)

        self.active_session_card.setVisible(False)
        layout.addWidget(self.active_session_card)

        # Two cards side by side
        cards_row = QHBoxLayout()
        cards_row.setSpacing(20)

        # Single Talk card
        single_card = self._build_mode_card(
            title="Single Talk",
            subtitle="One presenter, one session",
            desc="Perfect for lectures, demos, and standalone presentations.",
            accent=BLUE,
            btn_text="Start Presenting",
            btn_color=BLUE,
            on_click=lambda: self._show_setup()
        )
        cards_row.addWidget(single_card)

        # Conference card
        conf_card = self._build_mode_card(
            title="Conference Mode",
            subtitle="Multiple talks, one event",
            desc="Manage sequential speakers and talks in a single collection.",
            accent=GREEN,
            btn_text="Set Up Conference",
            btn_color=GREEN,
            on_click=lambda: self._switch_view(3)
        )
        cards_row.addWidget(conf_card)
        layout.addLayout(cards_row)

        # Upload bar
        upload_card = ShadowCard()
        upload_layout = QHBoxLayout(upload_card)
        upload_layout.setContentsMargins(20, 14, 20, 14)
        upload_layout.setSpacing(12)

        upload_text = QLabel("Drop a PDF or PowerPoint here, or")
        upload_text.setStyleSheet(f"color: {TEXT_FAINT}; font-size: 13px; background: transparent;")
        upload_link = QPushButton("browse files")
        upload_link.setCursor(Qt.PointingHandCursor)
        upload_link.setStyleSheet(f"color: {BLUE}; font-size: 13px; border: none; background: transparent;")
        upload_link.clicked.connect(self._on_upload_clicked)

        upload_layout.addStretch()
        upload_layout.addWidget(upload_text)
        upload_layout.addWidget(upload_link)
        upload_layout.addStretch()
        layout.addWidget(upload_card)

        # Recent Sessions
        recent_label = QLabel("Recent Sessions")
        recent_label.setStyleSheet(f"color: {TEXT_DARK}; font-size: 14px; background: transparent;")
        layout.addWidget(recent_label)

        # Placeholder recent sessions
        self.recent_sessions_layout = QVBoxLayout()
        self.recent_sessions_layout.setSpacing(8)

        empty = QLabel("No recent sessions yet. Start presenting to see them here.")
        empty.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px; background: transparent; padding: 16px;")
        empty.setAlignment(Qt.AlignCenter)
        self.recent_sessions_layout.addWidget(empty)

        layout.addLayout(self.recent_sessions_layout)
        layout.addStretch()

        return view

    def _build_mode_card(self, title, subtitle, desc, accent, btn_text, btn_color, on_click):
        card = ShadowCard(accent_color=accent)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(8)

        t = QLabel(title)
        t.setStyleSheet(f"color: {TEXT_DARK}; font-size: 16px; background: transparent;")
        s = QLabel(subtitle)
        s.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px; background: transparent;")
        d = QLabel(desc)
        d.setWordWrap(True)
        d.setStyleSheet(f"color: {TEXT_FAINT}; font-size: 12px; background: transparent; margin-top: 8px;")

        btn = QPushButton(btn_text)
        btn.setFixedHeight(36)
        btn.setFixedWidth(160)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {btn_color};
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 13px;
                           }}
            QPushButton:hover {{
                background: {accent};
                opacity: 0.9;
            }}
        """)
        btn.clicked.connect(on_click)

        layout.addWidget(t)
        layout.addWidget(s)
        layout.addWidget(d)
        layout.addSpacing(8)
        layout.addWidget(btn)
        layout.addStretch()

        return card

    # ── Setup View ─────────────────────────────────────────────────

    def _build_setup_view(self):
        view = QWidget()
        view.setStyleSheet(f"background: {BG_MAIN};")

        outer = QVBoxLayout(view)
        outer.setContentsMargins(40, 24, 40, 32)
        outer.setSpacing(16)

        # Breadcrumb
        breadcrumb = QHBoxLayout()
        bc_home = QPushButton("Home")
        bc_home.setCursor(Qt.PointingHandCursor)
        bc_home.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px; border: none; background: transparent;")
        bc_home.clicked.connect(lambda: self._switch_view(0))
        bc_sep = QLabel("/")
        bc_sep.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px; background: transparent;")
        bc_current = QLabel("New Talk")
        bc_current.setStyleSheet(f"color: {TEXT_DARK}; font-size: 12px; background: transparent;")
        breadcrumb.addWidget(bc_home)
        breadcrumb.addWidget(bc_sep)
        breadcrumb.addWidget(bc_current)
        breadcrumb.addStretch()
        outer.addLayout(breadcrumb)

        # Title
        page_title = QLabel("Set Up Your Talk")
        page_title.setStyleSheet(f"color: {TEXT_DARK}; font-size: 20px; background: transparent;")
        page_sub = QLabel("Fill in the details below. You can change these later.")
        page_sub.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 13px; background: transparent;")
        outer.addWidget(page_title)
        outer.addWidget(page_sub)

        # Form + Tips side by side
        content_row = QHBoxLayout()
        content_row.setSpacing(20)

        # Form card
        form_card = ShadowCard()
        form_layout = QVBoxLayout(form_card)
        form_layout.setContentsMargins(28, 24, 28, 28)
        form_layout.setSpacing(16)

        # Talk Title
        form_layout.addWidget(self._field_label("TALK TITLE"))
        self.in_title = QLineEdit()
        self.in_title.setPlaceholderText("e.g. Introduction to Machine Learning")
        self.in_title.setStyleSheet(self._input_style())
        self.in_title.setFixedHeight(40)
        form_layout.addWidget(self.in_title)

        # Presenter
        form_layout.addWidget(self._field_label("PRESENTER"))
        self.in_presenter = QLineEdit()
        self.in_presenter.setPlaceholderText("Your name")
        self.in_presenter.setStyleSheet(self._input_style())
        self.in_presenter.setFixedHeight(40)
        form_layout.addWidget(self.in_presenter)

        # Capture source (monitor). Only useful with the mss provider on X11;
        # the Wayland portal provider lets the user pick at portal-dialog time
        # and ignores this value, so we hide the picker entirely if there's
        # only one monitor or the picker can't enumerate.
        self._build_monitor_picker(form_layout)

        # Dedup-comparison area (which screen region the dedup engine
        # compares to decide "same slide vs new slide"). Default is the
        # middle 50% of the chosen monitor; user can override via the
        # RegionSelector overlay.
        self._build_dedup_area_picker(form_layout)

        # Sensitivity + Voice toggle row
        row = QHBoxLayout()
        row.setSpacing(24)

        sens_col = QVBoxLayout()
        sens_col.addWidget(self._field_label("SLIDE CHANGE SENSITIVITY"))
        self.slider_sens = QSlider(Qt.Horizontal)
        self.slider_sens.setRange(0, 100)
        self.slider_sens.setValue(int(app_settings.get("dedup_sensitivity", 60)))
        self.slider_sens.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                height: 6px;
                background: {BORDER};
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: {BLUE};
                border: 2px solid white;
                width: 16px;
                height: 16px;
                margin: -6px 0;
                border-radius: 9px;
            }}
            QSlider::sub-page:horizontal {{
                background: {BLUE};
                border-radius: 3px;
            }}
        """)
        self.sens_hint = QLabel("")
        self.sens_hint.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; background: transparent;")
        self.slider_sens.valueChanged.connect(self._on_sensitivity_changed)
        sens_col.addWidget(self.slider_sens)
        sens_col.addWidget(self.sens_hint)
        # Render the hint for the initial value
        self._on_sensitivity_changed(self.slider_sens.value())
        row.addLayout(sens_col, 2)

        voice_col = QVBoxLayout()
        voice_col.addWidget(self._field_label("VOICE RECORDING"))
        self.voice_toggle = QPushButton("Enabled")
        self.voice_toggle.setCheckable(True)
        self.voice_toggle.setChecked(True)
        self.voice_toggle.setCursor(Qt.PointingHandCursor)
        self.voice_toggle.setFixedHeight(28)
        self.voice_toggle.setFixedWidth(100)
        self.voice_toggle.setStyleSheet(f"""
            QPushButton {{
                background: {BLUE};
                color: white;
                border: none;
                border-radius: 14px;
                font-size: 12px;
                           }}
            QPushButton:checked {{
                background: {BLUE};
            }}
            QPushButton:!checked {{
                background: {BORDER};
                color: {TEXT_FAINT};
            }}
        """)
        self.voice_toggle.clicked.connect(self._on_voice_toggle)
        voice_col.addWidget(self.voice_toggle)
        voice_col.addStretch()
        row.addLayout(voice_col, 1)

        form_layout.addLayout(row)

        # Description
        form_layout.addWidget(self._field_label("DESCRIPTION (OPTIONAL)"))
        self.in_desc = QTextEdit()
        self.in_desc.setPlaceholderText("Brief description of your talk...")
        self.in_desc.setFixedHeight(72)
        self.in_desc.setStyleSheet(self._input_style())
        form_layout.addWidget(self.in_desc)

        # Start button
        self.btn_start = QPushButton("Start Presenting")
        self.btn_start.setFixedHeight(44)
        self.btn_start.setCursor(Qt.PointingHandCursor)
        self.btn_start.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {BLUE},stop:1 {BLUE_DARK});
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                           }}
            QPushButton:hover {{
                background: {BLUE_DARK};
            }}
        """)
        self.btn_start.clicked.connect(self._on_start_clicked)
        form_layout.addWidget(self.btn_start)

        content_row.addWidget(form_card, 3)

        # Tips card
        tips_card = ShadowCard()
        tips_card.setFixedWidth(200)
        tips_layout = QVBoxLayout(tips_card)
        tips_layout.setContentsMargins(20, 18, 20, 18)
        tips_layout.setSpacing(16)

        tips_title = QLabel("Quick Tips")
        tips_title.setStyleSheet(f"color: {TEXT_DARK}; font-size: 13px; background: transparent;")
        tips_layout.addWidget(tips_title)

        tips = [
            ("1", "Open your slides in any app (PPT, PDF)"),
            ("2", "Start presenting — slides auto-capture"),
            ("3", "Share session code with your audience"),
            ("4", "Viewers can ask AI, chat, take notes"),
        ]
        for num, text in tips:
            tip_row = QHBoxLayout()
            tip_row.setSpacing(8)
            tip_row.setAlignment(Qt.AlignTop)

            circle = QLabel(num)
            circle.setFixedSize(20, 20)
            circle.setAlignment(Qt.AlignCenter)
            circle.setStyleSheet(f"background: {BLUE_LIGHT}; color: {BLUE}; border-radius: 10px; font-size: 10px;")
            tip_row.addWidget(circle)

            tip_text = QLabel(text)
            tip_text.setWordWrap(True)
            tip_text.setStyleSheet(f"color: {TEXT_FAINT}; font-size: 11px; background: transparent;")
            tip_row.addWidget(tip_text, 1)

            tips_layout.addLayout(tip_row)

        tips_layout.addStretch()
        content_row.addWidget(tips_card, 1)

        outer.addLayout(content_row, 1)

        return view

    # ── Live Cockpit View ──────────────────────────────────────────

    def _build_live_view(self):
        view = QWidget()
        view.setStyleSheet(f"background: {BG_MAIN};")

        outer = QVBoxLayout(view)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Top bar with title + LIVE badge
        top_bar = QFrame()
        top_bar.setFixedHeight(56)
        top_bar.setStyleSheet(f"background: {BG_WHITE}; border-bottom: 1px solid {BORDER};")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(24, 0, 24, 0)

        self.live_title = QLabel("Presentation")
        self.live_title.setStyleSheet(f"color: {TEXT_DARK}; font-size: 17px; background: transparent;")
        top_layout.addWidget(self.live_title)
        top_layout.addStretch()

        # LIVE badge
        live_badge = QFrame()
        live_badge.setFixedSize(64, 26)
        live_badge.setStyleSheet(f"background: {RED_LIGHT}; border-radius: 13px;")
        badge_layout = QHBoxLayout(live_badge)
        badge_layout.setContentsMargins(8, 0, 10, 0)
        badge_layout.setSpacing(4)
        dot = QLabel()
        dot.setFixedSize(8, 8)
        dot.setStyleSheet(f"background: {RED}; border-radius: 4px;")
        badge_text = QLabel("LIVE")
        badge_text.setStyleSheet(f"color: {RED}; font-size: 11px; background: transparent;")
        badge_layout.addWidget(dot)
        badge_layout.addWidget(badge_text)
        top_layout.addWidget(live_badge)

        outer.addWidget(top_bar)

        # Body
        body = QVBoxLayout()
        body.setContentsMargins(24, 16, 24, 20)
        body.setSpacing(16)

        # Stats row
        stats_row = QHBoxLayout()
        stats_row.setSpacing(12)
        self.stat_elapsed = StatCard("ELAPSED", "00:00")
        self.stat_slides = StatCard("SLIDES", "0")
        self.stat_viewers = StatCard("VIEWERS", "0")
        self.stat_queries = StatCard("AI QUERIES", "0")
        stats_row.addWidget(self.stat_elapsed)
        stats_row.addWidget(self.stat_slides)
        stats_row.addWidget(self.stat_viewers)
        stats_row.addWidget(self.stat_queries)
        body.addLayout(stats_row)

        # Preview + Recent slides row
        preview_row = QHBoxLayout()
        preview_row.setSpacing(16)

        # Live preview (large)
        preview_card = ShadowCard()
        preview_card.setStyleSheet(f"""
            QFrame#shadowCard {{
                background: {TEXT_DARK};
                border: none;
                border-radius: 10px;
            }}
        """)
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setContentsMargins(12, 10, 12, 12)
        preview_layout.setSpacing(6)

        preview_label = QLabel("LIVE PREVIEW")
        preview_label.setStyleSheet(f"color: {TEXT_FAINT}; font-size: 10px; letter-spacing: 0.5px; background: transparent;")
        preview_layout.addWidget(preview_label)

        self.slide_preview = QLabel()
        self.slide_preview.setMinimumHeight(200)
        self.slide_preview.setStyleSheet("background: white; border-radius: 6px;")
        self.slide_preview.setAlignment(Qt.AlignCenter)
        no_slide = QLabel("Waiting for first slide...", self.slide_preview)
        no_slide.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 13px; background: transparent;")
        no_slide.setAlignment(Qt.AlignCenter)
        preview_layout.addWidget(self.slide_preview, 1)

        preview_row.addWidget(preview_card, 3)

        # Right panel: Recent slides + Share
        right_panel = QVBoxLayout()
        right_panel.setSpacing(12)

        recent_label = QLabel("RECENT SLIDES")
        recent_label.setStyleSheet(f"color: {TEXT_FAINT}; font-size: 10px; letter-spacing: 0.5px; background: transparent;")
        right_panel.addWidget(recent_label)

        # Thumbnails in a scroll area
        self.thumb_scroll = QScrollArea()
        self.thumb_scroll.setWidgetResizable(True)
        self.thumb_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.thumb_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.thumb_container = QWidget()
        self.thumb_container.setStyleSheet("background: transparent;")
        self.thumb_layout = QVBoxLayout(self.thumb_container)
        self.thumb_layout.setContentsMargins(0, 0, 0, 0)
        self.thumb_layout.setSpacing(8)
        self.thumb_layout.addStretch()
        self.thumb_scroll.setWidget(self.thumb_container)
        self.thumb_scroll.setFixedWidth(210)
        right_panel.addWidget(self.thumb_scroll, 1)

        # Share card
        share_card = ShadowCard()
        share_card.setFixedWidth(210)
        share_layout = QVBoxLayout(share_card)
        share_layout.setContentsMargins(16, 12, 16, 14)
        share_layout.setSpacing(6)

        share_title = QLabel("SHARE WITH AUDIENCE")
        share_title.setStyleSheet(f"color: {TEXT_FAINT}; font-size: 9px; letter-spacing: 0.5px; background: transparent;")
        share_layout.addWidget(share_title)

        self.share_code = QLabel("")
        self.share_code.setAlignment(Qt.AlignCenter)
        self.share_code.setFixedHeight(32)
        self.share_code.setStyleSheet(f"""
            background: {BG_INPUT};
            border: 1px solid {BORDER};
            border-radius: 6px;
            color: {TEXT_DARK};
            font-size: 14px;
                       letter-spacing: 1px;
        """)
        share_layout.addWidget(self.share_code)

        copy_btn = QPushButton("Copy Viewer Link")
        copy_btn.setFixedHeight(28)
        copy_btn.setCursor(Qt.PointingHandCursor)
        copy_btn.setStyleSheet(f"""
            QPushButton {{
                background: {BLUE_LIGHT};
                color: {BLUE};
                border: none;
                border-radius: 6px;
                font-size: 11px;
                           }}
            QPushButton:hover {{
                background: {BLUE_PALE};
            }}
        """)
        share_layout.addWidget(copy_btn)
        right_panel.addWidget(share_card)

        preview_row.addLayout(right_panel)
        body.addLayout(preview_row, 1)

        # Voice recording indicator
        self.voice_bar = ShadowCard()
        self.voice_bar.setFixedHeight(48)
        voice_layout = QHBoxLayout(self.voice_bar)
        voice_layout.setContentsMargins(16, 0, 16, 0)
        voice_layout.setSpacing(10)

        mic_dot = QLabel()
        mic_dot.setFixedSize(24, 24)
        mic_dot.setStyleSheet(f"background: {RED_LIGHT}; border-radius: 12px;")
        mic_dot.setAlignment(Qt.AlignCenter)
        voice_layout.addWidget(mic_dot)

        voice_text = QLabel("Voice Recording")
        voice_text.setStyleSheet(f"color: {TEXT_DARK}; font-size: 12px; background: transparent;")
        voice_layout.addWidget(voice_text)

        self.voice_elapsed = QLabel("00:00")
        self.voice_elapsed.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; background: transparent;")
        voice_layout.addWidget(self.voice_elapsed)

        voice_layout.addStretch()
        body.addWidget(self.voice_bar)

        # End button
        self.btn_stop = QPushButton("End Presentation")
        self.btn_stop.setFixedHeight(48)
        self.btn_stop.setCursor(Qt.PointingHandCursor)
        self.btn_stop.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {RED},stop:1 {RED_DARK});
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 15px;
                           }}
            QPushButton:hover {{
                background: {RED_DARK};
            }}
        """)
        self.btn_stop.clicked.connect(self._stop_recording)
        body.addWidget(self.btn_stop)

        outer.addLayout(body, 1)
        return view

    # ── Conference View ──────────────────────────────────────────

    def _build_conference_view(self):
        view = QWidget()
        view.setStyleSheet(f"background: {BG_MAIN};")

        outer = QVBoxLayout(view)
        outer.setContentsMargins(40, 24, 40, 32)
        outer.setSpacing(16)

        # Breadcrumb
        breadcrumb = QHBoxLayout()
        bc_home = QPushButton("Home")
        bc_home.setCursor(Qt.PointingHandCursor)
        bc_home.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px; border: none; background: transparent;")
        bc_home.clicked.connect(lambda: self._switch_view(0))
        bc_sep = QLabel("/")
        bc_sep.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px; background: transparent;")
        bc_current = QLabel("Conference Setup")
        bc_current.setStyleSheet(f"color: {TEXT_DARK}; font-size: 12px; background: transparent;")
        breadcrumb.addWidget(bc_home)
        breadcrumb.addWidget(bc_sep)
        breadcrumb.addWidget(bc_current)
        breadcrumb.addStretch()
        outer.addLayout(breadcrumb)

        # Title
        page_title = QLabel("Set Up Conference")
        page_title.setStyleSheet(f"color: {TEXT_DARK}; font-size: 20px; background: transparent;")
        page_sub = QLabel("Create a collection with multiple sequential talks.")
        page_sub.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 13px; background: transparent;")
        outer.addWidget(page_title)
        outer.addWidget(page_sub)

        # Two-column layout: form + talk list
        content_row = QHBoxLayout()
        content_row.setSpacing(20)

        # Left: Conference details form
        form_card = ShadowCard()
        form_layout = QVBoxLayout(form_card)
        form_layout.setContentsMargins(28, 24, 28, 28)
        form_layout.setSpacing(14)

        form_layout.addWidget(self._field_label("CONFERENCE NAME"))
        self.conf_name = QLineEdit()
        self.conf_name.setPlaceholderText("e.g. NUS Research Seminar 2026")
        self.conf_name.setStyleSheet(self._input_style())
        self.conf_name.setFixedHeight(40)
        form_layout.addWidget(self.conf_name)

        form_layout.addWidget(self._field_label("ORGANIZER"))
        self.conf_organizer = QLineEdit()
        self.conf_organizer.setPlaceholderText("Your name or organization")
        self.conf_organizer.setStyleSheet(self._input_style())
        self.conf_organizer.setFixedHeight(40)
        form_layout.addWidget(self.conf_organizer)

        form_layout.addWidget(self._field_label("DESCRIPTION (OPTIONAL)"))
        self.conf_desc = QTextEdit()
        self.conf_desc.setPlaceholderText("Brief description of the event...")
        self.conf_desc.setFixedHeight(64)
        self.conf_desc.setStyleSheet(self._input_style())
        form_layout.addWidget(self.conf_desc)

        # Sensitivity
        form_layout.addWidget(self._field_label("CAPTURE SENSITIVITY"))
        self.conf_slider = QSlider(Qt.Horizontal)
        self.conf_slider.setRange(0, 100)
        self.conf_slider.setValue(60)
        self.conf_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                height: 6px; background: {BORDER}; border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: {GREEN}; border: 2px solid white;
                width: 16px; height: 16px; margin: -6px 0; border-radius: 9px;
            }}
            QSlider::sub-page:horizontal {{
                background: {GREEN}; border-radius: 3px;
            }}
        """)
        form_layout.addWidget(self.conf_slider)

        form_layout.addStretch()

        # Launch button
        self.btn_launch_conf = QPushButton("Launch Conference")
        self.btn_launch_conf.setFixedHeight(44)
        self.btn_launch_conf.setCursor(Qt.PointingHandCursor)
        self.btn_launch_conf.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {GREEN},stop:1 {GREEN_DARK});
                color: white; border: none; border-radius: 8px;
                font-size: 14px;            }}
            QPushButton:hover {{ background: {GREEN_DARK}; }}
        """)
        self.btn_launch_conf.clicked.connect(self._on_launch_conference)
        form_layout.addWidget(self.btn_launch_conf)

        content_row.addWidget(form_card, 2)

        # Right: Talk schedule
        talks_card = ShadowCard()
        talks_layout = QVBoxLayout(talks_card)
        talks_layout.setContentsMargins(20, 18, 20, 18)
        talks_layout.setSpacing(10)

        talks_header = QHBoxLayout()
        talks_title = QLabel("Talk Schedule")
        talks_title.setStyleSheet(f"color: {TEXT_DARK}; font-size: 14px; background: transparent;")
        talks_header.addWidget(talks_title)
        talks_header.addStretch()

        self.btn_add_talk = QPushButton("+ Add Talk")
        self.btn_add_talk.setCursor(Qt.PointingHandCursor)
        self.btn_add_talk.setStyleSheet(f"""
            QPushButton {{
                background: {GREEN_LIGHT}; color: {GREEN};
                border: none; border-radius: 6px;
                padding: 6px 12px; font-size: 11px;            }}
            QPushButton:hover {{ background: rgba(16,185,129,0.2); }}
        """)
        self.btn_add_talk.clicked.connect(self._add_conference_talk)
        talks_header.addWidget(self.btn_add_talk)
        talks_layout.addLayout(talks_header)

        # Talk list scroll area
        self.conf_talk_scroll = QScrollArea()
        self.conf_talk_scroll.setWidgetResizable(True)
        self.conf_talk_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.conf_talk_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.conf_talk_container = QWidget()
        self.conf_talk_container.setStyleSheet("background: transparent;")
        self.conf_talk_list = QVBoxLayout(self.conf_talk_container)
        self.conf_talk_list.setContentsMargins(0, 0, 0, 0)
        self.conf_talk_list.setSpacing(8)

        # Placeholder
        self.conf_empty_label = QLabel("No talks added yet.\nClick '+ Add Talk' to schedule speakers.")
        self.conf_empty_label.setAlignment(Qt.AlignCenter)
        self.conf_empty_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px; background: transparent; padding: 32px;")
        self.conf_talk_list.addWidget(self.conf_empty_label)

        self.conf_talk_list.addStretch()
        self.conf_talk_scroll.setWidget(self.conf_talk_container)
        talks_layout.addWidget(self.conf_talk_scroll, 1)

        # Talk count footer
        self.conf_talk_count = QLabel("0 talks scheduled")
        self.conf_talk_count.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; background: transparent;")
        talks_layout.addWidget(self.conf_talk_count)

        content_row.addWidget(talks_card, 3)

        outer.addLayout(content_row, 1)
        return view

    def _add_conference_talk(self):
        """Add a new talk entry to the conference schedule."""
        # Hide empty label
        self.conf_empty_label.setVisible(False)

        talk_num = self.conf_talk_list.count()  # includes stretch + empty label

        row = QFrame()
        row.setFixedHeight(64)
        row.setStyleSheet(f"""
            QFrame {{
                background: {BG_MAIN};
                border: 1px solid {BORDER};
                border-radius: 8px;
            }}
        """)

        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(12, 8, 12, 8)
        row_layout.setSpacing(10)

        # Number badge
        num_label = QLabel(str(talk_num))
        num_label.setFixedSize(24, 24)
        num_label.setAlignment(Qt.AlignCenter)
        num_label.setStyleSheet(f"background: {GREEN_LIGHT}; color: {GREEN}; border-radius: 12px; font-size: 11px;")
        row_layout.addWidget(num_label)

        # Fields
        fields = QVBoxLayout()
        fields.setSpacing(4)

        title_input = QLineEdit()
        title_input.setPlaceholderText(f"Talk {talk_num} title")
        title_input.setStyleSheet(f"""
            QLineEdit {{
                background: white; border: 1px solid {BORDER}; border-radius: 4px;
                padding: 4px 8px; font-size: 12px; color: {TEXT_DARK};
            }}
            QLineEdit:focus {{ border-color: {GREEN}; }}
        """)
        fields.addWidget(title_input)

        speaker_input = QLineEdit()
        speaker_input.setPlaceholderText("Speaker name")
        speaker_input.setStyleSheet(f"""
            QLineEdit {{
                background: white; border: 1px solid {BORDER}; border-radius: 4px;
                padding: 4px 8px; font-size: 11px; color: {TEXT_FAINT};
            }}
            QLineEdit:focus {{ border-color: {GREEN}; }}
        """)
        fields.addWidget(speaker_input)
        row_layout.addLayout(fields, 1)

        # Remove button
        remove_btn = QPushButton("x")
        remove_btn.setFixedSize(24, 24)
        remove_btn.setCursor(Qt.PointingHandCursor)
        remove_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {TEXT_MUTED};
                border: none; border-radius: 12px; font-size: 14px;
            }}
            QPushButton:hover {{ background: {RED_LIGHT}; color: {RED}; }}
        """)
        remove_btn.clicked.connect(lambda: self._remove_conference_talk(row))
        row_layout.addWidget(remove_btn)

        # Insert before stretch
        self.conf_talk_list.insertWidget(self.conf_talk_list.count() - 1, row)
        self._update_conf_talk_count()

    def _remove_conference_talk(self, row):
        """Remove a talk row from the schedule."""
        row.setParent(None)
        row.deleteLater()
        self._update_conf_talk_count()

        # Show empty label if no talks
        has_talks = False
        for i in range(self.conf_talk_list.count()):
            item = self.conf_talk_list.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), QFrame) and item.widget() != self.conf_empty_label:
                has_talks = True
                break
        self.conf_empty_label.setVisible(not has_talks)

    def _update_conf_talk_count(self):
        """Update the talk count label."""
        count = 0
        for i in range(self.conf_talk_list.count()):
            item = self.conf_talk_list.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), QFrame) and item.widget() != self.conf_empty_label:
                count += 1
        self.conf_talk_count.setText(f"{count} talk{'s' if count != 1 else ''} scheduled")

    def _on_launch_conference(self):
        """Launch the conference mode."""
        name = self.conf_name.text().strip()
        if not name:
            self.conf_name.setFocus()
            self.conf_name.setStyleSheet(self._input_style().replace(BORDER, RED))
            QTimer.singleShot(2000, lambda: self.conf_name.setStyleSheet(self._input_style()))
            return

        logger.info(f"Launching conference: {name}")
        # TODO: Connect to ConferenceLauncher / admin server startup

    # ── Sessions View ─────────────────────────────────────────────

    def _build_sessions_view(self):
        view = QWidget()
        view.setStyleSheet(f"background: {BG_MAIN};")

        main_layout = QHBoxLayout(view)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Left panel: session list ──
        left_panel = QFrame()
        left_panel.setFixedWidth(280)
        left_panel.setStyleSheet(f"background: {BG_WHITE}; border-right: 1px solid {BORDER};")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        # Header
        header = QFrame()
        header.setFixedHeight(56)
        header.setStyleSheet(f"background: {BG_WHITE}; border-bottom: 1px solid {BORDER};")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 0, 16, 0)
        header_title = QLabel("Sessions")
        header_title.setStyleSheet(f"color: {TEXT_DARK}; font-size: 16px; background: transparent;")
        header_layout.addWidget(header_title)
        header_layout.addStretch()

        new_btn = QPushButton("+ New")
        new_btn.setCursor(Qt.PointingHandCursor)
        new_btn.setFixedHeight(30)
        new_btn.setStyleSheet(f"""
            QPushButton {{
                background: {BLUE}; color: white; border: none;
                border-radius: 6px; padding: 0 14px; font-size: 12px;
            }}
            QPushButton:hover {{ background: {BLUE_DARK}; }}
        """)
        new_btn.clicked.connect(self._show_new_session_dialog)
        header_layout.addWidget(new_btn)

        # Refresh status label (shown briefly during sync)
        self.session_status_label = QLabel("")
        self.session_status_label.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px; padding: 4px 16px; background: transparent;"
        )
        self.session_status_label.setVisible(False)
        left_layout.addWidget(header)
        left_layout.addWidget(self.session_status_label)

        # Session list (scrollable)
        self.session_scroll = QScrollArea()
        self.session_scroll.setWidgetResizable(True)
        self.session_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.session_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.session_list_widget = QWidget()
        self.session_list_widget.setStyleSheet("background: transparent;")
        self.session_list_layout = QVBoxLayout(self.session_list_widget)
        self.session_list_layout.setContentsMargins(0, 0, 0, 0)
        self.session_list_layout.setSpacing(0)
        self.session_list_layout.addStretch()
        self.session_scroll.setWidget(self.session_list_widget)
        left_layout.addWidget(self.session_scroll)

        main_layout.addWidget(left_panel)

        # ── Right panel: detail area ──
        self.sessions_detail_stack = QStackedWidget()

        # Index 0: empty state
        empty_detail = QWidget()
        empty_detail.setStyleSheet(f"background: {BG_MAIN};")
        empty_layout = QVBoxLayout(empty_detail)
        empty_layout.setAlignment(Qt.AlignCenter)
        empty_icon = QLabel("Select a session to view details")
        empty_icon.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 14px; background: transparent;")
        empty_icon.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(empty_icon)
        self.sessions_detail_stack.addWidget(empty_detail)  # index 0

        # Index 1: session detail (talks + slides)
        self.session_detail_widget = QWidget()
        self.session_detail_widget.setStyleSheet(f"background: {BG_MAIN};")
        detail_layout = QVBoxLayout(self.session_detail_widget)
        detail_layout.setContentsMargins(32, 24, 32, 24)
        detail_layout.setSpacing(16)

        # Session header with delete button
        sd_header = QHBoxLayout()
        sd_header_info = QVBoxLayout()
        sd_header_info.setSpacing(4)
        self.sd_title = QLabel("")
        self.sd_title.setStyleSheet(f"color: {TEXT_DARK}; font-size: 20px; background: transparent;")
        self.sd_subtitle = QLabel("")
        self.sd_subtitle.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px; background: transparent;")
        sd_header_info.addWidget(self.sd_title)
        sd_header_info.addWidget(self.sd_subtitle)
        sd_header.addLayout(sd_header_info, 1)

        self.sd_delete_btn = QPushButton("Delete Session")
        self.sd_delete_btn.setCursor(Qt.PointingHandCursor)
        self.sd_delete_btn.setFixedHeight(32)
        self.sd_delete_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {RED};
                border: 1px solid {RED}; border-radius: 6px;
                padding: 0 16px; font-size: 12px;
            }}
            QPushButton:hover {{
                background: {RED}; color: white;
            }}
        """)
        self.sd_delete_btn.clicked.connect(self._delete_selected_session)
        sd_header.addWidget(self.sd_delete_btn)

        detail_layout.addLayout(sd_header)

        # Talks list
        self.sd_talks_label = QLabel("Talks")
        self.sd_talks_label.setStyleSheet(f"color: {TEXT_DARK}; font-size: 14px; background: transparent;")
        detail_layout.addWidget(self.sd_talks_label)

        self.sd_talks_layout = QVBoxLayout()
        self.sd_talks_layout.setSpacing(6)
        detail_layout.addLayout(self.sd_talks_layout)

        # Slides section
        slides_header = QHBoxLayout()
        self.sd_slides_label = QLabel("Slides")
        self.sd_slides_label.setStyleSheet(f"color: {TEXT_DARK}; font-size: 14px; background: transparent;")
        slides_header.addWidget(self.sd_slides_label)
        slides_header.addStretch()
        detail_layout.addLayout(slides_header)

        # Slide grid in scroll area
        self.sd_slides_scroll = QScrollArea()
        self.sd_slides_scroll.setWidgetResizable(True)
        self.sd_slides_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.sd_slides_grid_widget = QWidget()
        self.sd_slides_grid_widget.setStyleSheet("background: transparent;")
        self.sd_slides_grid = QGridLayout(self.sd_slides_grid_widget)
        self.sd_slides_grid.setSpacing(12)
        self.sd_slides_scroll.setWidget(self.sd_slides_grid_widget)
        detail_layout.addWidget(self.sd_slides_scroll, 1)

        self.sessions_detail_stack.addWidget(self.session_detail_widget)  # index 1

        main_layout.addWidget(self.sessions_detail_stack, 1)

        # State
        self._selected_session = None
        self._selected_talk_id = None

        return view

    def _clear_sessions_worker_ref(self, worker: "CloudSessionsWorker", kind: str) -> None:
        """Drop our reference to a finished CloudSessionsWorker.

        Connected to QThread.finished. Only clears the slot if it still
        points at THIS worker — protects against a race where a second
        worker of the same kind was started before this one's finished
        signal landed.
        """
        attr = f"_sessions_{kind}_worker"
        if getattr(self, attr, None) is worker:
            setattr(self, attr, None)
        worker.deleteLater()

    def _refresh_sessions_list(self):
        """Render cached sessions immediately, then refresh from cloud in the background."""
        self._render_sessions_list(self._collect_known_sessions())

        # Auto-select the current collection so the right-side detail
        # panel shows its talks/slides immediately on first navigation
        # to the Sessions tab. Without this the panel stays on the empty
        # "Select a session to view details" state until the user clicks
        # a row — even though there's clearly a current session marked
        # with a ✓ in the list.
        if self._selected_session is None:
            cur = self.collection_registry.get_current_collection()
            if cur is not None:
                self._on_session_selected(cur)

        # Kick off a cloud refresh if configured. is_configured() now means
        # the bearer token from core.identity is present and the api_url is
        # set — there is no more user-editable cloud.session_token in YAML.
        if not self.cloud_sessions_client.is_configured():
            if not self.cloud_sessions_client.api_url:
                self.session_status_label.setText("Cloud sync is not configured.")
            else:
                self.session_status_label.setText(
                    "Sessions sync unavailable — check your connection or sign in."
                )
            self.session_status_label.setVisible(True)
            return

        if self._sessions_list_worker and self._sessions_list_worker.isRunning():
            return  # one in-flight list refresh is enough; result is idempotent

        self.session_status_label.setText("Refreshing from cloud…")
        self.session_status_label.setVisible(True)

        worker = CloudSessionsWorker(self.cloud_sessions_client, op="list")
        worker.finished_list.connect(self._on_cloud_sessions_loaded)
        worker.failed.connect(self._on_cloud_sessions_failed)
        # Clear the ref + recycle the QThread once it finishes, so the next
        # navigation to the Sessions tab gets a fresh worker.
        worker.finished.connect(lambda w=worker: self._clear_sessions_worker_ref(w, "list"))
        self._sessions_list_worker = worker
        worker.start()

    def _collect_known_sessions(self):
        """Build the merged session list from local cache (registry + DB).

        Returns a list of dicts with the shape expected by _render_sessions_list:
            { name, cloud_id, total_slides, talk_count, last_accessed, status,
              data (Collection or Session), is_current (bool) }

        Order of preference for what to surface:
        1. Collections in the registry (the normal path).
        2. SQLite sessions whose cloud_session_id isn't covered by any
           registry entry (orphan recovery — e.g. collections.yaml lost,
           or a session was recorded before the registry got an entry).
        This means a user who deletes their collections file by accident
        can still see their data and rebuild from the Sessions tab,
        rather than facing a blank list.
        """
        items = []
        seen_cloud_ids = set()
        current_cloud_id = None
        cur = self.collection_registry.get_current_collection()
        if cur:
            current_cloud_id = cur.cloud_collection_id

        cloud_session_ids = {s.get("session_id") for s in self._cloud_sessions_cache}

        # Precompute talk/slide counts per local cloud_session_id by walking
        # the SQLite sessions once. The Sessions tab list used to show
        # everything as "No talks yet" because these were hardcoded to 0;
        # now the meta line shows real counts even before the user clicks
        # into a session. Best-effort — skips silently if storage manager
        # isn't ready, and falls back to 0 for any cloud_id we can't map.
        counts_by_cloud_id: dict = {}
        if self.orchestrator and hasattr(self.orchestrator, "storage_manager"):
            try:
                db = self.orchestrator.storage_manager._database
                for s in db.get_all_sessions():
                    cid = s.cloud_session_id or ""
                    if not cid:
                        continue
                    talks = db.get_talks(s.session_id)
                    counts_by_cloud_id[cid] = {
                        "talk_count": len(talks),
                        "total_slides": db.get_slide_count(s.session_id),
                        "local_session_id": s.session_id,
                    }
            except Exception as e:
                logger.debug(f"could not aggregate talk/slide counts: {e}")

        # Collections from registry
        for col in self.collection_registry.list_collections():
            counts = counts_by_cloud_id.get(col.cloud_collection_id, {})
            items.append({
                "name": col.name or "Unnamed",
                "cloud_id": col.cloud_collection_id,
                "total_slides": counts.get("total_slides", 0),
                "talk_count": counts.get("talk_count", 0),
                "last_accessed": col.last_accessed,
                "status": "synced" if col.cloud_collection_id in cloud_session_ids else "local",
                "data": col,
                "is_current": col.cloud_collection_id == current_cloud_id,
            })
            seen_cloud_ids.add(col.cloud_collection_id)

        # Orphan recovery: SQLite sessions not represented by a registry
        # entry. Best-effort — silently skips if orchestrator isn't ready
        # yet (the user will see them after _on_orch_ready re-renders).
        if self.orchestrator and hasattr(self.orchestrator, "storage_manager"):
            try:
                db = self.orchestrator.storage_manager._database
                for s in db.get_all_sessions():
                    cloud_id = s.cloud_session_id or ""
                    if cloud_id and cloud_id in seen_cloud_ids:
                        continue
                    # Sessions without a cloud_session_id are purely local;
                    # surface them too with status "local only".
                    items.append({
                        "name": s.name or "Unnamed Session",
                        "cloud_id": cloud_id,
                        "total_slides": db.get_slide_count(s.session_id),
                        "talk_count": len(db.get_talks(s.session_id)),
                        "last_accessed": s.start_time,
                        "status": "orphan" if cloud_id else "local only",
                        "data": s,
                        "is_current": False,
                    })
                    if cloud_id:
                        seen_cloud_ids.add(cloud_id)
            except Exception as e:
                logger.debug(f"could not scan SQLite for orphan sessions: {e}")

        # Sort: current first, then by last_accessed desc
        items.sort(
            key=lambda x: (not x["is_current"], -(self._iso_to_ts(x["last_accessed"]) or 0))
        )
        return items

    @staticmethod
    def _iso_to_ts(value):
        if not value:
            return 0
        try:
            if isinstance(value, str):
                return datetime.datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()
            return float(value)
        except Exception:
            return 0

    def _render_sessions_list(self, items):
        """Clear and re-populate the session list panel."""
        while self.session_list_layout.count() > 1:
            child = self.session_list_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        if not items:
            empty = QLabel("No sessions yet.\nClick + New to create one.")
            empty.setAlignment(Qt.AlignCenter)
            empty.setWordWrap(True)
            empty.setStyleSheet(
                f"color: {TEXT_MUTED}; font-size: 12px; padding: 32px 16px; background: transparent;"
            )
            self.session_list_layout.insertWidget(0, empty)
            return

        for item in items:
            row = self._make_session_list_item(
                name=item["name"],
                session_id=item["cloud_id"],
                total_slides=item["total_slides"],
                talk_count=item["talk_count"],
                start_time=item["last_accessed"],
                status=item["status"],
                data=item["data"],
                is_current=item["is_current"],
            )
            self.session_list_layout.insertWidget(
                self.session_list_layout.count() - 1, row
            )

    def _on_cloud_sessions_loaded(self, sessions: list):
        """Cloud list arrived — merge into the registry and re-render."""
        had_current_before = self.collection_registry.get_current_collection() is not None
        self._cloud_sessions_cache = sessions
        self._merge_cloud_into_registry(sessions)
        self.session_status_label.setText(
            f"Synced {len(sessions)} session{'s' if len(sessions) != 1 else ''} from cloud."
        )
        QTimer.singleShot(2500, lambda: self.session_status_label.setVisible(False))
        self._render_sessions_list(self._collect_known_sessions())

        # On first sync of a fresh machine, pick the most recent session as current
        # so the home banner and orchestrator have something to point at.
        if not had_current_before and sessions:
            most_recent = max(sessions, key=lambda s: s.get("created_at", 0))
            cloud_id = most_recent.get("session_id")
            col = self.collection_registry.get_collection_by_cloud_id(cloud_id) if cloud_id else None
            if col:
                self.collection_registry.set_current_collection(col.collection_id)
                self._apply_current_session_to_orchestrator(col.cloud_collection_id)
                self._update_session_banner(col.name, col.cloud_collection_id)
                self._render_sessions_list(self._collect_known_sessions())

    def _on_cloud_sessions_failed(self, reason: str):
        self.session_status_label.setText(f"Cloud sync failed: {reason}")
        QTimer.singleShot(4000, lambda: self.session_status_label.setVisible(False))

    @staticmethod
    def _is_phantom_unknown_session(cs: dict) -> bool:
        """Identify phantom cloud sessions accidentally spawned by older
        builds at orchestrator boot.

        Earlier versions auto-created a cloud session on every launch
        (now fixed in storage_manager.start). cloud_provider's default
        for an empty presenter_name was the literal string "Unknown",
        which then echoed back from /api/cloud/sessions and polluted
        the registry. The signature: presenter_name=="Unknown", no
        slides ever recorded, no active talk. Anything matching all
        three is one of those phantoms — we ignore it on merge and
        evict it on detection.

        A real user-created session named "Unknown" wouldn't match
        because it would either have slides or be the active talk; if
        it has neither AND is named "Unknown", losing the registry
        row is recoverable (the cloud session still exists, and our
        orphan-recovery pass in _collect_known_sessions would surface
        any locally-recorded data).
        """
        if cs.get("presenter_name") != "Unknown":
            return False
        if cs.get("total_slides", 0):
            return False
        if cs.get("active_talk_id"):
            return False
        return True

    def _merge_cloud_into_registry(self, cloud_sessions: list):
        """Ensure every cloud session has a matching Collection in the
        local registry; ignore and evict the boot-time phantom pattern.
        """
        existing_by_cloud_id = {
            c.cloud_collection_id: c for c in self.collection_registry.list_collections()
        }
        for cs in cloud_sessions:
            cloud_id = cs.get("session_id")
            if not cloud_id:
                continue

            # Filter phantoms first: don't ADD them, and evict if they
            # were added by a previous (buggy) build.
            if self._is_phantom_unknown_session(cs):
                if cloud_id in existing_by_cloud_id:
                    col = existing_by_cloud_id[cloud_id]
                    try:
                        self.collection_registry.remove_collection(col.collection_id)
                        logger.info(
                            f"Evicted phantom 'Unknown' collection "
                            f"{col.collection_id} ({cloud_id}) from registry"
                        )
                    except Exception as e:
                        logger.debug(f"could not evict phantom collection: {e}")
                continue

            display_name = cs.get("presenter_name") or "Untitled Session"
            if cloud_id in existing_by_cloud_id:
                # Refresh name if it changed
                col = existing_by_cloud_id[cloud_id]
                if col.name != display_name:
                    self.collection_registry.update_collection(
                        col.collection_id, name=display_name
                    )
            else:
                self.collection_registry.add_collection(
                    cloud_collection_id=cloud_id,
                    name=display_name,
                    owner_username="",
                    is_owner=True,
                    access_level="owner",
                )

    # ── New session ────────────────────────────────────────────────

    def _show_new_session_dialog(self):
        """Prompt the user for a session title and create it in the cloud."""
        if not self.cloud_sessions_client.is_configured():
            # The cloud bearer comes from core.identity, not YAML. If we
            # don't have it, the right next step is the sign-in dialog
            # (which also handles device-bootstrap when there's no token
            # at all). After it closes we re-check before proceeding.
            if not self.cloud_sessions_client.api_url:
                QMessageBox.warning(
                    self, "Cloud Unavailable",
                    "Cloud sync isn't configured in this build.",
                )
                return
            dlg = SignInDialog(self, mode="claim")
            if dlg.exec_() != QDialog.Accepted:
                return
            # Fire-and-forget — the token is already updated by SignInDialog's
            # claim/login response; refresh_me here is belt-and-suspenders to
            # pull any fields not in the auth response (e.g. full_name).
            self._start_identity_refresh()
            if not self.cloud_sessions_client.is_configured():
                QMessageBox.warning(
                    self, "Cloud Unavailable",
                    "Couldn't reach the cloud after signing in. "
                    "Check your connection and try again.",
                )
                return
            # Fall through — we're authenticated now and can create the session.

        title = NewSessionDialog.get_new_title(self)
        if not title:
            return

        # Only de-dupe against another in-flight CREATE; we no longer block
        # on a list refresh — list and create are independent operations.
        if self._sessions_create_worker and self._sessions_create_worker.isRunning():
            QMessageBox.information(
                self, "Please wait", "A session is already being created."
            )
            return

        self.session_status_label.setText(f"Creating “{title}”…")
        self.session_status_label.setVisible(True)

        worker = CloudSessionsWorker(
            self.cloud_sessions_client, op="create", title=title
        )
        worker.finished_create.connect(self._on_session_created)
        worker.failed.connect(self._on_cloud_sessions_failed)
        worker.finished.connect(lambda w=worker: self._clear_sessions_worker_ref(w, "create"))
        self._sessions_create_worker = worker
        worker.start()

    def _on_session_created(self, result: dict):
        cloud_id = result.get("session_id", "")
        name = result.get("presenter_name") or "Untitled Session"
        if not cloud_id:
            self._on_cloud_sessions_failed("Server did not return a session_id.")
            return

        # Reuse an existing local row if one already matches this cloud_id.
        # _merge_cloud_into_registry can race with us — if the cloud list
        # echoes the new session before our finished_create signal lands,
        # the merge will have already added it, and a second add_collection
        # would create a duplicate row pointing at the same cloud session.
        col = self.collection_registry.get_collection_by_cloud_id(cloud_id)
        if col is None:
            col = self.collection_registry.add_collection(
                cloud_collection_id=cloud_id,
                name=name,
                owner_username="",
                is_owner=True,
                access_level="owner",
            )
        if col is None:
            # Defensive: add_collection currently always returns a Collection,
            # but a future refactor could change that. Bail without crashing
            # rather than hitting AttributeError on col.collection_id below.
            logger.warning(
                f"Could not register cloud_id={cloud_id} in the local registry"
            )
            self._on_cloud_sessions_failed(
                "Could not register the new session locally."
            )
            return

        self.collection_registry.set_current_collection(col.collection_id)
        self._apply_current_session_to_orchestrator(cloud_id)
        self._update_session_banner(name, cloud_id)
        self.session_status_label.setText(f"Created “{name}”.")
        QTimer.singleShot(2500, lambda: self.session_status_label.setVisible(False))

        # Refresh the list (will also pick up the new session from /api/cloud/sessions)
        self._refresh_sessions_list()

    # ── Switching the current session ──────────────────────────────

    def _set_current_session(self, collection: Collection):
        """Make `collection` the active session for new talks."""
        if self.is_active:
            QMessageBox.warning(
                self,
                "Talk in Progress",
                "Stop the current talk before switching sessions.",
            )
            return

        self.collection_registry.set_current_collection(collection.collection_id)
        self._apply_current_session_to_orchestrator(collection.cloud_collection_id)
        self._update_session_banner(collection.name, collection.cloud_collection_id)
        self._render_sessions_list(self._collect_known_sessions())

    def _apply_current_session_to_orchestrator(self, cloud_id: str):
        """Point the running orchestrator at this cloud session.

        Updates the cloud provider's target session_id (for any preview /
        banner queries) and the orchestrator.session.cloud_session_id so a
        later update_session() doesn't overwrite the value with a stale one.

        Does NOT switch the local session_id — that happens lazily at
        Start-Presenting time via _switch_orchestrator_to_cloud, since the
        local switch needs to either look up an existing local row or create
        a fresh one.
        """
        if not self.orchestrator or not hasattr(self.orchestrator, "storage_manager"):
            return
        try:
            cloud = self.orchestrator.storage_manager._cloud
            cloud.cloud_session_id = cloud_id
            cloud.current_talk_id = None
            # Re-enable cloud sync. It may have been disabled earlier in
            # this app session by a transient failure (e.g. a creation
            # timeout on a slow Railway cold-start). The user is now
            # explicitly pointing at an existing cloud session, so the
            # provider should be willing to talk again. api_url must be
            # set (it was at initialize() time) — if not, skip the toggle.
            if cloud.api_url and not cloud.enabled:
                cloud.enabled = True
                logger.info("Re-enabled cloud sync on session switch")
            if self.orchestrator.session:
                self.orchestrator.session.cloud_session_id = cloud_id
            logger.info(f"Switched orchestrator to cloud session {cloud_id}")
        except Exception as e:
            logger.warning(f"Could not update orchestrator's cloud session: {e}")

    def _switch_orchestrator_to_cloud(self, cloud_id: str):
        """Atomically re-point the orchestrator at a different local session
        row that corresponds to this cloud session.

        If a local Session row already exists for `cloud_id`, reuse it (so
        talks/slides created on this device for that collection accumulate
        in one place). Otherwise create a fresh local row and use it. The
        in-place mutation of self.orchestrator.session is intentional — all
        modules (storage manager, capture daemon, dedup engine) hold the
        same reference, and update_session() propagates the new ids down.
        """
        if not self.orchestrator or not self.orchestrator.session:
            return
        if not hasattr(self.orchestrator, "storage_manager"):
            return
        try:
            db = self.orchestrator.storage_manager._database
            existing = db.get_sessions_by_cloud_session(cloud_id)
            if existing:
                local = existing[0]
                self.orchestrator.session.session_id = local.session_id
                self.orchestrator.session.cloud_session_id = cloud_id
                self.orchestrator.session.start_time = local.start_time
                logger.info(
                    f"Switched orchestrator to existing local session "
                    f"{local.session_id} (cloud {cloud_id})"
                )
            else:
                from core.models.session import Session as SessionModel
                new_local = SessionModel(
                    name=self.orchestrator.session.name or "Untitled",
                    presenter_name=self.orchestrator.session.presenter_name or "",
                    cloud_session_id=cloud_id,
                )
                db.create_session(new_local)
                fs = self.orchestrator.storage_manager._filesystem
                fs.create_session(new_local)
                self.orchestrator.session.session_id = new_local.session_id
                self.orchestrator.session.cloud_session_id = cloud_id
                self.orchestrator.session.start_time = new_local.start_time
                logger.info(
                    f"Created new local session {new_local.session_id} "
                    f"for cloud {cloud_id}"
                )
        except Exception as e:
            logger.warning(
                f"Could not switch orchestrator to cloud {cloud_id}: {e}",
                exc_info=True,
            )

    def _make_session_list_item(self, name, session_id, total_slides, talk_count, start_time, status, data, is_current=False):
        """Create a clickable session row for the list."""
        frame = QFrame()
        frame.setFixedHeight(72)
        frame.setCursor(Qt.PointingHandCursor)
        bg = BLUE_LIGHT if is_current else "transparent"
        border_left = f"border-left: 3px solid {BLUE};" if is_current else "border-left: 3px solid transparent;"
        frame.setStyleSheet(f"""
            QFrame {{
                background: {bg};
                border-bottom: 1px solid {BORDER};
                {border_left}
                padding: 0 16px;
            }}
            QFrame:hover {{
                background: {BLUE_LIGHT};
            }}
        """)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(2)

        name_text = f"{name}  ✓" if is_current else name
        name_label = QLabel(name_text)
        weight = "font-weight: 600;" if is_current else ""
        name_label.setStyleSheet(f"color: {TEXT_DARK}; font-size: 13px; {weight} background: transparent; border: none;")

        # Talk/slide counts line
        count_parts = []
        if talk_count:
            count_parts.append(f"{talk_count} talk{'s' if talk_count != 1 else ''}")
        if total_slides:
            count_parts.append(f"{total_slides} slide{'s' if total_slides != 1 else ''}")
        count_str = " · ".join(count_parts) if count_parts else "No talks yet"
        count_label = QLabel(count_str)
        count_label.setStyleSheet(f"color: {TEXT_FAINT}; font-size: 11px; background: transparent; border: none;")

        # Format time + session ID
        time_str = ""
        if start_time:
            try:
                if isinstance(start_time, str):
                    # ISO format from collection registry
                    dt = datetime.datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                    time_str = dt.strftime("%b %d, %Y")
                else:
                    dt = datetime.datetime.fromtimestamp(start_time)
                    time_str = dt.strftime("%b %d, %Y %H:%M")
            except Exception:
                time_str = str(start_time)[:10]

        meta_parts = [session_id]
        if time_str:
            meta_parts.append(time_str)
        if status and status not in ("collection",):
            meta_parts.append(status)

        meta_label = QLabel(" · ".join(meta_parts))
        meta_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px; background: transparent; border: none;")

        layout.addWidget(name_label)
        layout.addWidget(count_label)
        layout.addWidget(meta_label)

        # Click handler — switch active session AND show its detail
        frame.mousePressEvent = lambda e, d=data: self._on_session_row_clicked(d)

        return frame

    def _on_session_row_clicked(self, data):
        """Row click: make this session current, then show its detail panel."""
        if isinstance(data, Collection):
            self._set_current_session(data)
        self._on_session_selected(data)

    def _on_session_selected(self, session_data):
        """Handle session selection — load talks and slides."""
        self._selected_session = session_data
        self._selected_talk_id = None

        # Determine session info
        if isinstance(session_data, Collection):
            name = session_data.name or "Unnamed"
            cloud_id = session_data.cloud_collection_id
            self.sd_title.setText(name)
            self.sd_subtitle.setText(f"Session: {cloud_id}")
            # Load talks from local DB by matching cloud_session_id
            self._load_talks_for_cloud_id(cloud_id)
        else:
            # It's a Session object
            name = session_data.name or "Unnamed Session"
            sid = session_data.cloud_session_id or session_data.session_id[:8]
            self.sd_title.setText(name)
            self.sd_subtitle.setText(
                f"Session: {sid} · {session_data.total_slides} slides · {session_data.status}"
            )
            self._load_talks_for_session(session_data.session_id)

        self.sessions_detail_stack.setCurrentIndex(1)

    def _delete_selected_session(self):
        """Delete the currently selected session."""
        if not self._selected_session:
            return

        if isinstance(self._selected_session, Collection):
            name = self._selected_session.name or "Unnamed"
        else:
            name = self._selected_session.name or "Unnamed Session"

        reply = QMessageBox.question(
            self, "Delete Session",
            f"Delete \"{name}\"?\n\nThis will remove the session, all its talks, and all slides from the local database.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        deleted = False
        if isinstance(self._selected_session, Collection):
            # Delete from collection registry
            try:
                self.collection_registry.collections = [
                    c for c in self.collection_registry.collections
                    if c.collection_id != self._selected_session.collection_id
                ]
                self.collection_registry._save_registry()
                deleted = True
            except Exception as e:
                logger.error(f"Failed to delete collection: {e}")
        else:
            # Delete from SQLite DB
            if self.orchestrator and hasattr(self.orchestrator, 'storage_manager'):
                db = self.orchestrator.storage_manager._database
                deleted = db.delete_session(self._selected_session.session_id)

        if deleted:
            self._selected_session = None
            self.sessions_detail_stack.setCurrentIndex(0)
            self._refresh_sessions_list()
            # Update home page banner
            self._show_last_collection()
            logger.info(f"Deleted session: {name}")

    def _load_talks_for_cloud_id(self, cloud_id):
        """Load talks for a session identified by cloud_session_id."""
        # Clear talks
        self._clear_layout(self.sd_talks_layout)

        if not self.orchestrator or not hasattr(self.orchestrator, 'storage_manager'):
            # Orchestrator still booting — show a busy indicator instead of
            # a misleading "no talks". _on_orch_ready will re-run this load.
            self._show_talks_loading()
            self._clear_grid(self.sd_slides_grid)
            self._show_slides_loading()
            return

        db = self.orchestrator.storage_manager._database
        # Find local session matching this cloud ID
        sessions = db.get_all_sessions()
        local_session = None
        for s in sessions:
            if s.cloud_session_id == cloud_id:
                local_session = s
                break

        if not local_session:
            self._show_no_talks()
            self._load_slides_for_session_all(None)
            return

        self._load_talks_for_session(local_session.session_id)

    def _load_talks_for_session(self, session_id):
        """Load talks for a local session_id."""
        self._clear_layout(self.sd_talks_layout)

        if not self.orchestrator or not hasattr(self.orchestrator, 'storage_manager'):
            self._show_talks_loading()
            self._clear_grid(self.sd_slides_grid)
            self._show_slides_loading()
            return

        db = self.orchestrator.storage_manager._database
        talks = db.get_talks(session_id)

        if not talks:
            self._show_no_talks()
            # Show all slides for this session
            self._load_slides_for_session_all(session_id)
            return

        self.sd_talks_label.setText(f"Talks ({len(talks)})")

        # "All slides" button
        all_btn = self._make_talk_row("All Slides", "", session_id, is_all=True)
        self.sd_talks_layout.addWidget(all_btn)

        for talk in talks:
            row = self._make_talk_row(
                title=talk['title'] or "Untitled Talk",
                presenter=talk.get('presenter_name', ''),
                talk_id=talk['talk_id'],
                is_all=False
            )
            self.sd_talks_layout.addWidget(row)

        # Default: show all slides
        self._load_slides_for_session_all(session_id)

    def _make_talk_row(self, title, presenter, talk_id, is_all=False):
        """Create a clickable talk row."""
        frame = QFrame()
        frame.setFixedHeight(40)
        frame.setCursor(Qt.PointingHandCursor)
        frame.setStyleSheet(f"""
            QFrame {{
                background: {BG_WHITE};
                border: 1px solid {BORDER};
                border-radius: 6px;
            }}
            QFrame:hover {{
                background: {BLUE_LIGHT};
                border-color: {BLUE};
            }}
        """)

        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(8)

        t = QLabel(title)
        t.setStyleSheet(f"color: {TEXT_DARK}; font-size: 12px; background: transparent; border: none;")
        layout.addWidget(t)

        if presenter:
            p = QLabel(presenter)
            p.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; background: transparent; border: none;")
            layout.addWidget(p)

        layout.addStretch()

        if is_all:
            frame.mousePressEvent = lambda e, sid=talk_id: self._load_slides_for_session_all(sid)
        else:
            frame.mousePressEvent = lambda e, tid=talk_id: self._load_slides_for_talk(tid)

        return frame

    def _load_slides_for_session_all(self, session_id):
        """Load all slides for a session into the grid."""
        self._selected_talk_id = None
        self._clear_grid(self.sd_slides_grid)

        if not self.orchestrator or not hasattr(self.orchestrator, 'storage_manager'):
            self._show_slides_loading()
            return
        if not session_id:
            self.sd_slides_label.setText("Slides")
            return

        db = self.orchestrator.storage_manager._database
        slides = db.list_slides(session_id)
        self.sd_slides_label.setText(f"Slides ({len(slides)})")
        self._populate_slide_grid(slides)

    def _load_slides_for_talk(self, talk_id):
        """Load slides for a specific talk into the grid."""
        self._selected_talk_id = talk_id
        self._clear_grid(self.sd_slides_grid)

        if not self.orchestrator or not hasattr(self.orchestrator, 'storage_manager'):
            self._show_slides_loading()
            return

        db = self.orchestrator.storage_manager._database
        slides = db.list_slides_by_talk(talk_id)

        self.sd_slides_label.setText(f"Slides ({len(slides)})")
        self._populate_slide_grid(slides)

    def _populate_slide_grid(self, slides):
        """Fill the slide grid with thumbnail cards."""
        cols = 4
        for i, slide in enumerate(slides):
            card = self._make_slide_card(slide, i)
            self.sd_slides_grid.addWidget(card, i // cols, i % cols)

    def _make_slide_card(self, slide, index):
        """Create a slide thumbnail card with delete button."""
        card = QFrame()
        card.setFixedSize(160, 140)
        card.setStyleSheet(f"""
            QFrame {{
                background: {BG_WHITE};
                border: 1px solid {BORDER};
                border-radius: 8px;
            }}
        """)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Thumbnail
        thumb = QLabel()
        thumb.setFixedSize(152, 100)
        thumb.setAlignment(Qt.AlignCenter)
        thumb.setStyleSheet(f"background: #f1f5f9; border-radius: 4px; border: none;")

        # Try to load thumbnail or full image
        img_path = slide.thumbnail_path or slide.image_path
        if img_path and os.path.exists(img_path):
            pix = QPixmap(img_path).scaled(152, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            thumb.setPixmap(pix)
        else:
            thumb.setText(f"Slide {slide.sequence_number}")
            thumb.setStyleSheet(f"background: #f1f5f9; border-radius: 4px; border: none; color: {TEXT_MUTED}; font-size: 11px;")

        layout.addWidget(thumb)

        # Bottom row: number + delete
        bottom = QHBoxLayout()
        bottom.setContentsMargins(4, 0, 4, 0)
        num = QLabel(f"#{slide.sequence_number}")
        num.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px; background: transparent; border: none;")
        bottom.addWidget(num)
        bottom.addStretch()

        del_btn = QPushButton("×")
        del_btn.setFixedSize(20, 20)
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {TEXT_MUTED};
                border: none; font-size: 14px;
            }}
            QPushButton:hover {{
                color: {RED}; background: {RED_LIGHT}; border-radius: 10px;
            }}
        """)
        del_btn.clicked.connect(lambda _, s=slide, c=card: self._delete_slide(s, c))
        bottom.addWidget(del_btn)

        layout.addLayout(bottom)
        return card

    def _delete_slide(self, slide, card_widget):
        """Delete a slide from local DB and cloud."""
        reply = QMessageBox.question(
            self, "Delete Slide",
            f"Delete slide #{slide.sequence_number}?\nThis will also remove it from the cloud.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        deleted_local = False
        deleted_cloud = False

        # Delete from local DB
        if self.orchestrator and hasattr(self.orchestrator, 'storage_manager'):
            db = self.orchestrator.storage_manager._database
            try:
                cursor = db._conn.cursor()
                cursor.execute("DELETE FROM slides WHERE slide_id = ?", (slide.slide_id,))
                db._conn.commit()
                deleted_local = True
            except Exception as e:
                logger.error(f"Failed to delete slide locally: {e}")

            # Delete from cloud
            cloud = self.orchestrator.storage_manager._cloud
            if cloud.enabled:
                cloud_session_id = cloud.cloud_session_id
                if cloud_session_id:
                    deleted_cloud = cloud.delete_slide(cloud_session_id, slide.slide_id)

            # Delete local files
            for path in (slide.image_path, slide.thumbnail_path):
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                    except Exception:
                        pass

        if deleted_local:
            card_widget.deleteLater()
            # Update slide count label
            current_text = self.sd_slides_label.text()
            try:
                count = int(current_text.split("(")[1].split(")")[0]) - 1
                self.sd_slides_label.setText(f"Slides ({count})")
            except Exception:
                pass
            logger.info(f"Deleted slide {slide.slide_id} (cloud: {deleted_cloud})")

    def _show_no_talks(self):
        """Show empty state in talks section."""
        self.sd_talks_label.setText("Talks")
        lbl = QLabel("No talks found")
        lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px; background: transparent;")
        self.sd_talks_layout.addWidget(lbl)

    def _make_busy_row(self, text: str) -> QFrame:
        """Inline busy indicator (indeterminate progress bar + label)."""
        row = QFrame()
        row.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(4, 6, 4, 6)
        layout.setSpacing(10)

        bar = QProgressBar()
        bar.setRange(0, 0)  # indeterminate marquee
        bar.setTextVisible(False)
        bar.setFixedHeight(4)
        bar.setFixedWidth(96)
        bar.setStyleSheet(
            f"QProgressBar {{ background: {BG_INPUT}; border: none; border-radius: 2px; }}"
            f"QProgressBar::chunk {{ background: {BLUE}; border-radius: 2px; }}"
        )
        layout.addWidget(bar)

        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px; background: transparent;")
        layout.addWidget(lbl)
        layout.addStretch()
        return row

    def _show_talks_loading(self):
        """Show a busy indicator while waiting for talks to load."""
        self.sd_talks_label.setText("Talks")
        self.sd_talks_layout.addWidget(self._make_busy_row("Loading talks…"))

    def _show_slides_loading(self):
        """Show a busy indicator while waiting for slides to load."""
        self.sd_slides_label.setText("Slides")
        self.sd_slides_grid.addWidget(self._make_busy_row("Loading slides…"), 0, 0)

    def _clear_layout(self, layout):
        """Remove all widgets from a layout."""
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _clear_grid(self, grid):
        """Remove all widgets from a grid layout."""
        while grid.count():
            item = grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _build_placeholder(self, text):
        w = QWidget()
        w.setStyleSheet(f"background: {BG_MAIN};")
        layout = QVBoxLayout(w)
        layout.setAlignment(Qt.AlignCenter)
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {TEXT_DARK}; font-size: 20px; background: transparent;")
        lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl)
        sub = QLabel("Coming soon")
        sub.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 13px; background: transparent;")
        sub.setAlignment(Qt.AlignCenter)
        layout.addWidget(sub)
        return w

    # ── Account view ───────────────────────────────────────────────

    def _build_account_view(self):
        view = QWidget()
        view.setStyleSheet(f"background: {BG_MAIN};")

        outer = QVBoxLayout(view)
        outer.setContentsMargins(48, 36, 48, 36)
        outer.setSpacing(20)

        title = QLabel("Account")
        title.setStyleSheet(f"color: {TEXT_DARK}; font-size: 22px; background: transparent;")
        outer.addWidget(title)

        # ── Identity card ──
        id_card = ShadowCard()
        id_layout = QVBoxLayout(id_card)
        id_layout.setContentsMargins(20, 18, 20, 18)
        id_layout.setSpacing(10)

        self.acc_status_label = QLabel("")
        self.acc_status_label.setStyleSheet(f"color: {TEXT_DARK}; font-size: 16px; background: transparent;")
        id_layout.addWidget(self.acc_status_label)

        self.acc_email_row = self._account_row("Email", "—")
        self.acc_phone_row = self._account_row("Phone", "—")
        self.acc_userid_row = self._account_row("User ID", "—")
        id_layout.addLayout(self.acc_email_row["row"])
        id_layout.addLayout(self.acc_phone_row["row"])
        id_layout.addLayout(self.acc_userid_row["row"])

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.acc_primary_btn = QPushButton("Sign In or Register")
        self.acc_primary_btn.setCursor(Qt.PointingHandCursor)
        self.acc_primary_btn.setFixedHeight(34)
        self.acc_primary_btn.setStyleSheet(
            f"QPushButton {{ background: {BLUE}; color: white; border: none;"
            f" border-radius: 6px; padding: 0 16px; font-size: 12px; }}"
            f"QPushButton:hover {{ background: {BLUE_DARK}; }}"
        )
        self.acc_primary_btn.clicked.connect(self._on_account_primary_clicked)
        btn_row.addWidget(self.acc_primary_btn)

        self.acc_secondary_btn = QPushButton("Sign Out")
        self.acc_secondary_btn.setCursor(Qt.PointingHandCursor)
        self.acc_secondary_btn.setFixedHeight(34)
        self.acc_secondary_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {TEXT_BODY};"
            f" border: 1px solid {BORDER}; border-radius: 6px; padding: 0 16px; font-size: 12px; }}"
            f"QPushButton:hover {{ background: #f1f5f9; }}"
        )
        self.acc_secondary_btn.clicked.connect(self._on_account_signout_clicked)
        btn_row.addWidget(self.acc_secondary_btn)
        btn_row.addStretch()

        id_layout.addLayout(btn_row)
        outer.addWidget(id_card)

        # ── Device card ──
        dev_card = ShadowCard()
        dev_layout = QVBoxLayout(dev_card)
        dev_layout.setContentsMargins(20, 18, 20, 18)
        dev_layout.setSpacing(8)

        dev_title = QLabel("This device")
        dev_title.setStyleSheet(f"color: {TEXT_DARK}; font-size: 14px; background: transparent;")
        dev_layout.addWidget(dev_title)

        self.dev_label_row = self._account_row("Label", identity().device_label)
        self.dev_id_row = self._account_row("Device ID", identity().device_id[:16] + "…")
        dev_layout.addLayout(self.dev_label_row["row"])
        dev_layout.addLayout(self.dev_id_row["row"])

        outer.addWidget(dev_card)

        # ── Recovery hint card (only when phone-primary) ──
        self.acc_recovery_card = ShadowCard()
        rec_layout = QVBoxLayout(self.acc_recovery_card)
        rec_layout.setContentsMargins(20, 16, 20, 16)
        rec_layout.setSpacing(6)
        rec_title = QLabel("Recovery email")
        rec_title.setStyleSheet(f"color: {TEXT_DARK}; font-size: 14px; background: transparent;")
        rec_layout.addWidget(rec_title)
        rec_hint = QLabel(
            "Add an email so you can recover your account if you forget your PIN. "
            "Recovery via email is the only free option right now."
        )
        rec_hint.setWordWrap(True)
        rec_hint.setStyleSheet(f"color: {TEXT_BODY}; font-size: 12px; background: transparent;")
        rec_layout.addWidget(rec_hint)
        rec_btn = QPushButton("Add recovery email")
        rec_btn.setCursor(Qt.PointingHandCursor)
        rec_btn.setFixedHeight(30)
        rec_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {BLUE};"
            f" border: 1px solid {BLUE}; border-radius: 6px; padding: 0 14px; font-size: 12px; }}"
            f"QPushButton:hover {{ background: #eff6ff; }}"
        )
        rec_btn.clicked.connect(self._on_account_edit_clicked)
        rec_btn.setMaximumWidth(180)
        rec_layout.addWidget(rec_btn)
        outer.addWidget(self.acc_recovery_card)

        outer.addStretch()
        return view

    def _account_row(self, label_text: str, value_text: str) -> dict:
        row = QHBoxLayout()
        row.setSpacing(12)
        label = QLabel(label_text)
        label.setStyleSheet(f"color: {TEXT_FAINT}; font-size: 12px; background: transparent;")
        label.setMinimumWidth(80)
        value = QLabel(value_text)
        value.setStyleSheet(f"color: {TEXT_DARK}; font-size: 13px; background: transparent;")
        value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        row.addWidget(label)
        row.addWidget(value, 1)
        return {"row": row, "value": value}

    def _refresh_account_view(self):
        ident = identity()
        rec = ident.record

        if rec.is_anonymous or not ident.is_authenticated:
            self.acc_status_label.setText("Anonymous account")
            self.acc_email_row["value"].setText("—")
            self.acc_phone_row["value"].setText("—")
            self.acc_userid_row["value"].setText(rec.user_id or "—")
            self.acc_primary_btn.setText("Sign In or Register")
            self.acc_secondary_btn.setVisible(False)
            self.acc_recovery_card.setVisible(False)
        else:
            email = rec.email or ""
            phone = rec.phone_number or ""
            primary = email or phone or "Signed in"
            self.acc_status_label.setText(f"Signed in as {primary}")
            self.acc_email_row["value"].setText(email or "—")
            self.acc_phone_row["value"].setText(phone or "—")
            self.acc_userid_row["value"].setText(rec.user_id or "—")
            self.acc_primary_btn.setText("Edit")
            self.acc_secondary_btn.setVisible(True)
            # Recovery card visible only when phone-primary and no email on file
            self.acc_recovery_card.setVisible(bool(phone) and not email)

    # ── Account actions ────────────────────────────────────────────

    def _on_account_primary_clicked(self):
        if identity().is_anonymous or not identity().is_authenticated:
            self._open_sign_in_dialog()
        else:
            self._on_account_edit_clicked()

    def _open_sign_in_dialog(self):
        dlg = SignInDialog(self, mode="claim")
        if dlg.exec_() == QDialog.Accepted:
            action = dlg.get_action()
            if action == "merged":
                msg = "Signed in. Sessions from this device were merged with your existing account."
            elif action == "upgraded":
                msg = "Account created. Your existing data is now linked to this email/phone."
            else:
                msg = "Signed in."
            QMessageBox.information(self, "Welcome", msg)
            self.nudge_state.reset()
            self._start_identity_refresh()
            # The user_id may have changed (merged path) — reload sessions.
            # The list query authenticates by token (already updated by the
            # sign-in worker), so it can run in parallel with refresh_me.
            self._refresh_sessions_list()

    def _on_account_edit_clicked(self):
        dlg = EditAccountDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            self._start_identity_refresh()

    # ── Nudge ──────────────────────────────────────────────────────

    def _evaluate_nudge(self):
        """Decide if a register/sign-in nudge should be shown right now."""
        if self._nudge_dialog_open:
            return
        if not identity().is_authenticated:
            # Bootstrap hasn't completed yet — try again later.
            return
        tier = self.nudge_state.evaluate(is_anonymous=identity().is_anonymous)
        if tier is None:
            return
        self._show_nudge(tier)

    def _show_nudge(self, tier: NudgeTier):
        self._nudge_dialog_open = True
        try:
            while True:
                dlg = NudgeDialog(self, tier=tier)
                dlg.exec_()
                # Mark this tier as shown so we don't immediately re-fire it.
                self.nudge_state.mark_shown(tier)

                if dlg.signed_in():
                    # User clicked "Sign In or Register" — open the real flow.
                    sign_dlg = SignInDialog(self, mode="claim")
                    if sign_dlg.exec_() == QDialog.Accepted:
                        # Claim succeeded — reset nudge state and refresh UI.
                        self.nudge_state.reset()
                        self._start_identity_refresh()
                        self._refresh_sessions_list()
                        return
                    # Sign-in cancelled. For enforce tier, re-loop. For others, give up.
                    if tier != NudgeTier.ENFORCE:
                        return
                    continue

                # User dismissed without signing in.
                if tier != NudgeTier.ENFORCE:
                    return
                # Enforce tier: cannot dismiss. Loop until they sign in or close app.
        finally:
            self._nudge_dialog_open = False

    def _on_account_signout_clicked(self):
        if self.is_active:
            QMessageBox.warning(
                self, "Talk in Progress",
                "Stop the current talk before signing out.",
            )
            return
        reply = QMessageBox.question(
            self, "Sign Out",
            "Sign out and return to an anonymous account on this device?\n\n"
            "Your session list will be hidden until you sign in again. "
            "Local data is not deleted.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        identity().logout()
        # Bootstrap a fresh anonymous account so the device keeps a token.
        identity().ensure_bootstrap()
        self._refresh_account_view()
        self._refresh_sessions_list()

    # ── Helpers ────────────────────────────────────────────────────

    def _field_label(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {TEXT_BODY}; font-size: 11px; letter-spacing: 0.5px; background: transparent;")
        return lbl

    def _input_style(self):
        return f"""
            QLineEdit, QTextEdit {{
                background: {BG_INPUT};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 13px;
                color: {TEXT_DARK};
            }}
            QLineEdit:focus, QTextEdit:focus {{
                border-color: {BLUE};
            }}
        """

    # ── Monitor picker ─────────────────────────────────────────────

    def _resolve_monitor_id(self) -> int:
        """Choose the monitor index to start the orchestrator with.

        Prefers the user's saved choice (`app_settings.monitor_id`). Falls
        back to 1 (mss's primary). If the saved index is no longer valid
        (e.g. user unplugged the secondary monitor between launches), the
        mss provider will raise CaptureError; we don't pre-validate here
        because get_monitor_count() opens an mss context that's wasted on
        the happy path.
        """
        try:
            saved = int(app_settings.get("monitor_id", 1))
            return saved if saved >= 1 else 1
        except Exception:
            return 1

    def _build_monitor_picker(self, form_layout: QVBoxLayout) -> None:
        """Insert the monitor-source picker into the Setup form.

        Hidden when only one monitor is available. The picker's choice is
        persisted to app_settings and takes effect on the NEXT app launch —
        the orchestrator's capture daemon is already bound to a monitor by
        the time the user reaches the Setup view.
        """
        try:
            screens = get_screen_info()
        except Exception as e:
            logger.debug(f"could not enumerate monitors: {e}")
            screens = []

        if len(screens) < 2:
            # Single monitor (or enumeration failed): nothing to pick.
            return

        form_layout.addWidget(self._field_label("CAPTURE SOURCE"))
        self.monitor_picker = QComboBox()
        self.monitor_picker.setFixedHeight(38)
        self.monitor_picker.setStyleSheet(self._input_style())
        for s in screens:
            label = f"Monitor {s['id']} — {s['width']}×{s['height']}"
            self.monitor_picker.addItem(label, userData=s["id"])

        saved_id = self._resolve_monitor_id()
        for i in range(self.monitor_picker.count()):
            if self.monitor_picker.itemData(i) == saved_id:
                self.monitor_picker.setCurrentIndex(i)
                break

        self.monitor_picker.currentIndexChanged.connect(self._on_monitor_changed)
        form_layout.addWidget(self.monitor_picker)

        self._monitor_hint = QLabel(
            "Takes effect the next time you launch SeenSlide."
        )
        self._monitor_hint.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px; background: transparent;"
        )
        self._monitor_hint.setVisible(False)
        form_layout.addWidget(self._monitor_hint)

    def _on_monitor_changed(self, _index: int):
        if not hasattr(self, "monitor_picker"):
            return
        new_id = self.monitor_picker.currentData()
        try:
            app_settings.set_value("monitor_id", int(new_id))
            logger.info(f"Saved monitor_id={new_id} to app settings")
            if hasattr(self, "_monitor_hint"):
                self._monitor_hint.setVisible(True)
        except Exception as e:
            logger.warning(f"could not save monitor preference: {e}")

    # ── Dedup-comparison area picker ───────────────────────────────

    def _resolve_dedup_region(self, monitor_width: int, monitor_height: int) -> dict:
        """Read the saved dedup region, falling back to 50% centered.

        Validates against the current monitor size — if the user changed
        monitors between launches, the saved coords may not fit. In that
        case we silently fall back to the default and let the user re-pick.
        """
        saved = app_settings.get("dedup_region", None)
        if isinstance(saved, dict):
            ok, _ = validate_region(saved, monitor_width, monitor_height)
            if ok:
                return saved
        return calculate_default_region(monitor_width, monitor_height, 0.5)

    def _region_summary(self, region: dict) -> str:
        if not region:
            return "Not set"
        return (
            f"{region.get('width', '?')}×{region.get('height', '?')} "
            f"at ({region.get('x', '?')}, {region.get('y', '?')})"
        )

    def _build_dedup_area_picker(self, form_layout: QVBoxLayout) -> None:
        """Insert the dedup-area row into the Setup form.

        Shows a button to open the RegionSelector overlay, a status label
        with the currently-saved region (or "Default — middle 50%" when
        none saved), and an inline hint that appears once after the user
        confirms a new region.
        """
        form_layout.addWidget(self._field_label("CAPTURE AREA"))

        row = QHBoxLayout()
        row.setSpacing(10)

        self.btn_choose_region = QPushButton("Choose region…")
        self.btn_choose_region.setCursor(Qt.PointingHandCursor)
        self.btn_choose_region.setFixedHeight(34)
        self.btn_choose_region.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {BLUE};"
            f" border: 1px solid {BLUE}; border-radius: 6px;"
            f" padding: 0 14px; font-size: 12px; }}"
            f"QPushButton:hover {{ background: {BLUE_LIGHT}; }}"
        )
        self.btn_choose_region.clicked.connect(self._on_choose_region_clicked)
        row.addWidget(self.btn_choose_region)

        saved = app_settings.get("dedup_region", None)
        if isinstance(saved, dict):
            current_text = self._region_summary(saved)
        else:
            current_text = "Default — middle 50% of screen"

        self.region_status = QLabel(current_text)
        self.region_status.setStyleSheet(
            f"color: {TEXT_FAINT}; font-size: 12px; background: transparent;"
        )
        row.addWidget(self.region_status)
        row.addStretch()
        form_layout.addLayout(row)

        self._region_hint = QLabel(
            "Takes effect the next time you launch SeenSlide."
        )
        self._region_hint.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px; background: transparent;"
        )
        self._region_hint.setVisible(False)
        form_layout.addWidget(self._region_hint)

    def _on_choose_region_clicked(self):
        """Take a fresh screenshot of the selected monitor and open the
        RegionSelector overlay so the user can drag out a rectangle.
        """
        monitor_id = self._resolve_monitor_id()
        try:
            screenshot = capture_screenshot(monitor_id)
        except Exception as e:
            logger.error(f"Could not capture screenshot for region picker: {e}")
            QMessageBox.warning(
                self, "Capture Failed",
                "Couldn't grab a screenshot of the selected monitor. "
                "Check that the capture provider is available.",
            )
            return
        if screenshot is None:
            QMessageBox.warning(
                self, "Capture Failed",
                "The screenshot came back empty. Try again — the capture "
                "provider may still be initializing.",
            )
            return

        default = self._resolve_dedup_region(screenshot.width, screenshot.height)

        # RegionSelector is a fullscreen overlay; we hold a reference to
        # prevent GC while it's visible, and connect to its signals so
        # we can persist or skip the result.
        self._region_selector = RegionSelector(
            screenshot=screenshot,
            default_region=default,
            parent=None,
        )
        self._region_selector.region_confirmed.connect(self._on_region_confirmed)
        self._region_selector.selection_cancelled.connect(self._on_region_cancelled)
        self._region_selector.showFullScreen()

    def _on_region_confirmed(self, region: dict):
        """RegionSelector closed with a chosen rectangle."""
        try:
            app_settings.set_value(
                "dedup_region",
                {
                    "x": int(region.get("x", 0)),
                    "y": int(region.get("y", 0)),
                    "width": int(region.get("width", 0)),
                    "height": int(region.get("height", 0)),
                },
            )
            logger.info(f"Saved dedup_region={region} to app settings")
            if hasattr(self, "region_status"):
                self.region_status.setText(self._region_summary(region))
            if hasattr(self, "_region_hint"):
                self._region_hint.setVisible(True)
        except Exception as e:
            logger.warning(f"could not save dedup region: {e}")
        finally:
            self._region_selector = None

    def _on_region_cancelled(self):
        """RegionSelector closed without a choice."""
        self._region_selector = None

    def _get_greeting(self):
        # Personalize from the cached identity record so the greeting is
        # set synchronously at build time (no network). For a signed-in
        # user we prefer full_name, then email, then phone. Anonymous
        # accounts fall back to the generic greeting.
        try:
            rec = identity().record
            if rec and not rec.is_anonymous:
                name = rec.full_name or rec.email or rec.phone_number
                if name:
                    return f"Welcome back, {name}"
        except Exception as e:
            logger.debug(f"Could not personalize greeting: {e}")
        return "Welcome to SeenSlide"

    # ── Navigation ─────────────────────────────────────────────────

    def _switch_view(self, index):
        self.view_stack.setCurrentIndex(index)

        # Refresh sessions list when navigating to sessions view
        if index == 4:
            self._refresh_sessions_list()
        elif index == 5:
            self._refresh_account_view()

        # Update sidebar active state
        view_to_nav = {0: 0, 1: 0, 2: 0, 3: 1, 4: 2, 5: 3}
        active_nav = view_to_nav.get(index, 0)
        for i, btn in enumerate(self.nav_buttons):
            btn.active = (i == active_nav)

    def _show_setup(self):
        self._switch_view(1)

    # ── Actions ────────────────────────────────────────────────────

    def _on_start_clicked(self):
        if not self.orchestrator:
            return

        # Store form values for use after countdown
        self._pending_title = self.in_title.text().strip() or "Untitled Talk"
        self._pending_presenter = self.in_presenter.text().strip() or "Presenter"
        self._pending_desc = self.in_desc.toPlainText()
        self._pending_sensitivity = self.slider_sens.value()

        # Show countdown overlay on the live view
        self._switch_view(2)
        self.live_title.setText("Starting soon...")

        # Create and show countdown
        self._countdown = CountdownWidget(duration=10, title="Switch to your presentation window", parent=self.view_stack.widget(2))
        self._countdown.setStyleSheet(f"background: rgba(15,18,25,0.92); border-radius: 12px;")
        self._countdown.setGeometry(self.view_stack.widget(2).rect())
        self._countdown.countdown_finished.connect(self._start_recording_after_countdown)
        self._countdown.countdown_cancelled.connect(self._cancel_countdown)
        self._countdown.show()
        self._countdown.raise_()
        self._countdown.start()

    def _cancel_countdown(self):
        """Handle countdown cancellation — go back to setup."""
        if hasattr(self, '_countdown'):
            self._countdown.hide()
            self._countdown.deleteLater()
        self._switch_view(1)

    def _start_recording_after_countdown(self):
        """Start the actual recording after countdown finishes."""
        if hasattr(self, '_countdown'):
            self._countdown.hide()
            self._countdown.deleteLater()

        title = self._pending_title
        presenter = self._pending_presenter

        # Apply sensitivity
        threshold = (100 - self._pending_sensitivity) / 100.0
        if 'deduplication' not in self.orchestrator.config:
            self.orchestrator.config['deduplication'] = {}
        self.orchestrator.config['deduplication']['perceptual_threshold'] = threshold
        logger.info(f"Applied dedup threshold: {threshold:.2f} (sensitivity {self._pending_sensitivity}%)")

        # Resolve which cloud collection this talk should attach to.
        # The user may have switched the current collection since the
        # orchestrator was last started; we honor that choice here.
        current_col = self.collection_registry.get_current_collection()
        target_cloud_id = current_col.cloud_collection_id if current_col else None

        session = self.orchestrator.session
        session.name = title
        session.presenter_name = presenter
        session.description = self._pending_desc

        if target_cloud_id and session.cloud_session_id != target_cloud_id:
            # User selected a different cloud session than the orchestrator
            # is currently pointed at. Re-point orchestrator.session at a
            # local session row matching this cloud_id — reusing an existing
            # row if there is one, otherwise creating a fresh local row.
            self._switch_orchestrator_to_cloud(target_cloud_id)
        elif not session.cloud_session_id:
            # No collection selected and nothing on the session yet — fall
            # back to whatever the cloud provider already has (legacy path).
            if hasattr(self.orchestrator, 'storage_manager') and self.orchestrator.storage_manager._cloud.enabled:
                session.cloud_session_id = self.orchestrator.storage_manager._cloud.cloud_session_id

        self.orchestrator.update_session(session)

        # Start voice recording BEFORE switching capture to ACTIVE. Voice
        # subscribes its SLIDE_UNIQUE handler inside start_voice_recording;
        # if captures are already firing, slide 1's SLIDE_UNIQUE can fire
        # before that subscription lands, and the handler will only see
        # sequence_number=2 onward. Subscribing first guarantees slide 1's
        # event is observed.
        if self.voice_toggle.isChecked():
            self.orchestrator.set_voice_enabled(True)
            if self.orchestrator.start_voice_recording():
                logger.info("Voice recording started")
            else:
                logger.warning("Voice recording failed to start")

        self.orchestrator.set_capture_mode(CaptureMode.ACTIVE)

        # Update live view
        self.live_title.setText(title)
        self.slide_count = 0

        # Show session code
        cloud_id = ""
        if hasattr(self.orchestrator, 'storage_manager') and self.orchestrator.storage_manager._cloud.enabled:
            cloud_id = self.orchestrator.storage_manager._cloud.cloud_session_id or ""
        if cloud_id:
            self.share_code.setText(cloud_id)
            self.sidebar_session_code.setText(cloud_id)
            self.sidebar_live_box.setVisible(True)

        # Update active session banner on home page
        self._update_session_banner(title, cloud_id or "Local")

        # Update sidebar to show live indicator
        self.btn_home.active = False

        # Start timer
        self.start_time = time.time()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_stats)
        self.timer.start(1000)

        # Update status bar
        self.status_text.setText("Recording...")
        self.status_text.setStyleSheet(f"color: {RED}; font-size: 11px; background: transparent;")

    def _stop_recording(self):
        # Re-entry guard. End is finalized on a background thread; without
        # this check, a second click while the worker is in flight would
        # call orchestrator.stop_voice_recording() again (sees recording
        # already stopped → drops a duplicate chunk), end_talk() twice,
        # and switch_view(0) on a partially-finalized state.
        if getattr(self, "_finalizing", False):
            return
        self._finalizing = True
        self.btn_stop.setEnabled(False)
        self.btn_stop.setText("Finalizing…")
        self.btn_stop.setCursor(Qt.ArrowCursor)

        if hasattr(self, 'timer'):
            self.timer.stop()

        self.orchestrator.set_capture_mode(CaptureMode.IDLE)

        # Show progress while voice is being finalized
        self.status_text.setText("Finalizing audio...")
        self.status_text.setStyleSheet(f"color: {BLUE}; font-size: 11px; background: transparent;")
        self.status_dot.setStyleSheet(f"background: {BLUE}; border-radius: 4px;")

        # Run voice stop in background thread to avoid GUI freeze
        import threading
        def _finalize_voice():
            try:
                self.orchestrator.stop_voice_recording()
            except Exception as e:
                logger.error(f"Voice finalization error: {e}")
            # Tell the cloud the talk is over. Done AFTER voice stop so the
            # final OGG and any trailing chunk land in voice_recordings
            # before cloud_talks flips to status='completed'. Otherwise
            # viewers stop seeing LIVE but the audio for the final stretch
            # might still be uploading.
            try:
                if (
                    self.orchestrator
                    and hasattr(self.orchestrator, "storage_manager")
                    and self.orchestrator.storage_manager
                ):
                    cloud = self.orchestrator.storage_manager._cloud
                    if cloud and cloud.current_talk_id:
                        cloud.end_talk()
            except Exception as e:
                logger.error(f"end_talk error: {e}")
            # Update UI from main thread
            QTimer.singleShot(0, self._on_recording_stopped)

        threading.Thread(target=_finalize_voice, daemon=True).start()

    def _on_recording_stopped(self):
        """Called after voice recording is fully finalized."""
        self.sidebar_live_box.setVisible(False)
        self.active_session_card.setVisible(False)
        self.status_text.setText("Server Connected")
        self.status_text.setStyleSheet(f"color: {GREEN}; font-size: 11px; background: transparent;")
        self.status_dot.setStyleSheet(f"background: {GREEN}; border-radius: 4px;")

        # Restore the End button so the next talk can use it.
        self.btn_stop.setEnabled(True)
        self.btn_stop.setText("End Presentation")
        self.btn_stop.setCursor(Qt.PointingHandCursor)
        self._finalizing = False

        self._switch_view(0)

    def _update_stats(self):
        elapsed = int(time.time() - self.start_time)
        mins, secs = divmod(elapsed, 60)
        self.stat_elapsed.val.setText(f"{mins:02d}:{secs:02d}")
        self.voice_elapsed.setText(f"{mins:02d}:{secs:02d} elapsed")

        stats = self.orchestrator.get_statistics()
        slides = stats.get('storage', {}).get('slides_stored', 0)
        self.stat_slides.val.setText(str(slides))

    def _on_slide_stored(self, event):
        # Record for nudge logic regardless of UI state.
        self.nudge_state.record_slide()
        # Defer to event loop so the dialog (if any) doesn't block the
        # signal handler thread.
        QTimer.singleShot(0, self._evaluate_nudge)

        slide = event.data.get("slide")
        if slide and slide.image_path:
            # Update preview
            pix = QPixmap(slide.image_path)
            if not pix.isNull():
                self.slide_preview.setPixmap(
                    pix.scaled(self.slide_preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )

            # Add thumbnail
            self.slide_count += 1
            thumb = SlideThumbnail(self.slide_count, is_current=True)
            if not pix.isNull():
                thumb.img_label.setPixmap(
                    pix.scaled(88, 50, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )

            # Un-highlight previous current
            for i in range(self.thumb_layout.count()):
                item = self.thumb_layout.itemAt(i)
                if item and item.widget() and isinstance(item.widget(), SlideThumbnail):
                    item.widget().setStyleSheet(f"QFrame {{ background: {BG_WHITE}; border: 1px solid {BORDER}; border-radius: 6px; }}")

            # Insert at top (before stretch)
            self.thumb_layout.insertWidget(0, thumb)

    def _on_upload_clicked(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Slide File", "",
            "Presentation Files (*.pdf *.pptx *.ppt)"
        )
        if path:
            logger.info(f"File selected for upload: {path}")

    def _on_sensitivity_changed(self, value):
        # Persist so the choice survives launches. The value is read at
        # talk-start time and translated to perceptual_threshold via
        # threshold = (100 - sensitivity) / 100.0 — higher slider = lower
        # threshold = treats smaller pixel differences as a new slide.
        try:
            app_settings.set_value("dedup_sensitivity", int(value))
        except Exception as e:
            logger.debug(f"could not save dedup_sensitivity: {e}")

        if value < 33:
            label = "Low"
            tail = "treats small differences as the same slide"
        elif value < 66:
            label = "Medium"
            tail = "balanced — good default for typical decks"
        else:
            label = "High"
            tail = "treats even subtle changes as a new slide"
        self.sens_hint.setText(f"{label} — {tail}")

    def _on_voice_toggle(self):
        if self.voice_toggle.isChecked():
            self.voice_toggle.setText("Enabled")
        else:
            self.voice_toggle.setText("Disabled")

    # ── Orchestrator Init ──────────────────────────────────────────

    def _init_orchestrator(self):
        current = self.collection_registry.get_current_collection()
        width, height = get_primary_screen_size()
        # Honor the user's saved dedup region if any (set via the Setup
        # view's "Choose region…" button). Falls back to 50% centered
        # when no saved value or when the saved value doesn't fit the
        # current monitor.
        crop = self._resolve_dedup_region(width, height)
        monitor_id = self._resolve_monitor_id()
        self.worker = OrchestratorStartWorker(monitor_id, crop, current)
        self.worker.ready.connect(self._on_orch_ready)
        self.worker.error.connect(lambda e: logger.error(f"Orchestrator init failed: {e}"))
        self.worker.start()

    def _on_orch_ready(self):
        self.orchestrator = self.worker.orchestrator
        self.orchestrator.event_bus.subscribe(EventType.SLIDE_STORED, self._on_slide_stored)

        # If the cloud sessions sync finished before the orchestrator did,
        # the registry's current_collection may already point at a different
        # cloud session than the one the orchestrator booted with. Re-apply
        # it now so the next talk targets the right collection.
        current = self.collection_registry.get_current_collection()
        if current and current.cloud_collection_id:
            self._apply_current_session_to_orchestrator(current.cloud_collection_id)

        # If the user already opened the Sessions tab and selected a session
        # before we were ready, the talk-list lookup short-circuited to "no
        # talks". Re-run it now that storage_manager is available.
        if self._selected_session is not None:
            if isinstance(self._selected_session, Collection):
                cloud_id = self._selected_session.cloud_collection_id
                if cloud_id:
                    self._load_talks_for_cloud_id(cloud_id)
            else:
                self._load_talks_for_session(self._selected_session.session_id)

        # Show active session on home page if one exists
        cloud_id = self.worker.cloud_id
        if cloud_id:
            session_name = ""
            if hasattr(self.orchestrator, 'session') and self.orchestrator.session:
                session_name = getattr(self.orchestrator.session, 'name', '') or ''
            self._update_session_banner(session_name or "Active Session", cloud_id)
        else:
            # Show the current/most recent collection from registry
            self._show_last_collection()

        logger.info(f"Orchestrator ready. Cloud ID: {cloud_id}")

    def _show_last_collection(self):
        """Show the current collection (defaults to most recent) on the home banner."""
        try:
            # First check if there's an explicitly set current collection
            current = self.collection_registry.get_current_collection()
            if current:
                self._update_session_banner(current.name, current.cloud_collection_id)
                return

            # Fall back to most recently accessed
            collections = self.collection_registry.list_collections()
            if not collections:
                return
            collections.sort(key=lambda c: c.last_accessed, reverse=True)
            latest = collections[0]
            self._update_session_banner(latest.name, latest.cloud_collection_id)
        except Exception as e:
            logger.debug(f"Could not load last collection: {e}")

    def _update_session_banner(self, name: str, session_id: str):
        """Update the current session banner on the home page."""
        self.as_name.setText(name or "Unnamed Session")
        self.as_id.setText(f"Session: {session_id}")
        self.active_session_card.setVisible(True)


if __name__ == "__main__":
    import sys
    from PyQt5.QtWidgets import QApplication
    app = QApplication(sys.argv)
    window = MainDashboard()
    window.show()
    sys.exit(app.exec_())
