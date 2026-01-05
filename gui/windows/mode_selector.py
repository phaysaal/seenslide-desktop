"""Mode selector window - choose between modes."""

import os
from typing import Optional
from pathlib import Path
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QSizePolicy, QGraphicsDropShadowEffect, QToolButton
)
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QPixmap, QPalette, QColor
from PyQt5.QtCore import QFile
import logging


logger = logging.getLogger(__name__)


class ModeSelector(QWidget):
    """Window for selecting between modes."""

    # Signals
    direct_talk_selected = pyqtSignal()
    conference_mode_selected = pyqtSignal()
    manage_talks_selected = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        """Initialize mode selector.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)

        self._setup_ui()
        self._setup_shortcuts()

        logger.info("ModeSelector initialized")

    def _setup_ui(self):
        """Setup the UI components."""
        self.setWindowTitle("SeenSlide")
        self.setFixedSize(520, 460)

        # Light background with subtle gradient
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor("#f6f7fb"))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Window card
        window_card = QFrame()
        window_card.setObjectName("windowCard")
        window_card.setStyleSheet("""
            #windowCard {
                background: white;
                border: 1px solid rgba(15, 23, 42, 0.12);
                border-radius: 18px;
            }
        """)

        card_layout = QVBoxLayout(window_card)
        card_layout.setSpacing(0)
        card_layout.setContentsMargins(0, 0, 0, 0)

        # Title bar
        titlebar = self._create_titlebar()
        card_layout.addWidget(titlebar)

        # Content
        content = self._create_content()
        card_layout.addWidget(content, 1)

        # Footer
        footer = self._create_footer()
        card_layout.addWidget(footer)

        # Center the window card with padding
        main_layout.addWidget(window_card)

    def _resource_path(self, *parts: str) -> str:
        # mode_selector.py is in gui/windows/
        # project resources are in gui/resources/
        base = Path(__file__).resolve().parents[1] / "resources"
        return str(base.joinpath(*parts))

    def _load_gear_icon(self) -> QIcon:
        p = self._resource_path("icons", "gear.svg")
        return QIcon(p)

    def _create_titlebar(self) -> QWidget:
        """
        Unified titlebar that contains:
        - Left: logo + (SeenSlide + slogan)
        - Right: version
        Fixed height so the overall GUI can be fixed height without clipping.
        """
        TITLEBAR_H = 76

        titlebar = QWidget()
        titlebar.setFixedHeight(TITLEBAR_H)

        # IMPORTANT: no padding here; only visuals. Use layout margins for spacing.
        #titlebar.setStyleSheet("""
        #    background: qlineargradient(
        #        x1:0, y1:0, x2:0, y2:1,
        #        stop:0 rgba(2, 6, 23, 0.03),
        #        stop:1 transparent
        #    );
        #    border-bottom: 1px solid rgba(15, 23, 42, 0.08);
        #""")

        layout = QHBoxLayout(titlebar)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        # --- Left group: Logo + Text stack ---
        left = QWidget()
        left_layout = QHBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)

        # Logo
        logo_label = QLabel()
        logo_label.setFixedSize(50, 50)

        logo_pixmap = self._load_logo()
        if logo_pixmap:
            scaled = logo_pixmap.scaled(50, 50, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            logo_label.setPixmap(scaled)
        else:
            logo_label.setStyleSheet("""
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #2563eb, stop:1 #7c3aed
                );
                border-radius: 12px;
            """)

        left_layout.addWidget(logo_label, 0, Qt.AlignVCenter)

        # Text stack (title + slogan)
        text_widget = QWidget()
        text_layout = QVBoxLayout(text_widget)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(3)

        title = QLabel("SeenSlide")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        # title.setStyleSheet("color: #0f172a;")
        title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        title.setWordWrap(False)
        title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        slogan = QLabel("Control slides already on screen")
        slogan.setFont(QFont("Arial", 11))
        slogan.setStyleSheet("color: #64748b;")
        slogan.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        slogan.setWordWrap(False)  # keep height stable; no wrapping surprises
        slogan.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        text_layout.addWidget(title)
        text_layout.addWidget(slogan)

        left_layout.addWidget(text_widget, 1)

        # Let left expand and push version to the right
        left.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(left, 1)


        gear = QToolButton()
        gear.setIcon(self._load_gear_icon())
        gear.setCursor(Qt.PointingHandCursor)
        gear.setToolTip("Manage talks")
        gear.setStyleSheet("""
            QToolButton {
                border: none;
                padding: 4px;
                color: #64748b;
            }
            QToolButton:hover {
                color: #334155;
            }
        """)
        gear.clicked.connect(self._on_manage_talks_clicked)
        layout.addWidget(gear, 0, Qt.AlignRight | Qt.AlignVCenter)

        # --- Right: Version ---
        version = QLabel("v0.3.0")
        version.setFont(QFont("Courier", 10))
        version.setStyleSheet("color: #64748b;")
        version.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        version.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        layout.addWidget(version, 0, Qt.AlignRight | Qt.AlignVCenter)

        return titlebar

    def _create_content(self) -> QWidget:
        """Create main content area (launcher content)."""
        content = QWidget()
        layout = QVBoxLayout(content)
        #layout.setContentsMargins(22, 18, 22, 18)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- Local Mode (default / primary) ---
        layout.addSpacing(12)
        local_section = self._create_section(
            "Just One Talk",
            "Quick setup · Closes when done",
            "Default",
            "Start one presentation. Window closes automatically when finished.",
            "▶ Start Presenting",
            self._on_direct_talk_clicked,
            True
        )
        layout.addWidget(local_section)

        # Divider
        layout.addSpacing(20)
        #divider = QFrame()
        #divider.setFrameShape(QFrame.HLine)
        #divider.setFixedHeight(1)
        #divider.setStyleSheet("background: rgba(15, 23, 42, 0.08); border: none;")
        #layout.addWidget(divider)
        #layout.addSpacing(14)

        # --- Conference Mode (secondary) ---
        conf_section = self._create_section(
            "Multiple Talks",
            "Conference & event mode · Stays running",
            None,
            "Manage multiple sessions in sequence. Admin panel runs in background.",
            "⚙ Set up conference…",
            self._on_conference_clicked,
            False
        )
        layout.addWidget(conf_section)

        # Spacer to push the low-visibility row to bottom of content
        layout.addStretch(1)

        # --- Low-visibility row (Manage talks) ---
        bottom_row = QWidget()
        row = QHBoxLayout(bottom_row)
        row.setContentsMargins(0, 10, 0, 0)
        row.setSpacing(10)

        #manage_link = QLabel('<a href="#">Manage talks…</a>')
        #manage_link.setTextFormat(Qt.RichText)
        #manage_link.setTextInteractionFlags(Qt.TextBrowserInteraction)
        #manage_link.setOpenExternalLinks(False)
        #manage_link.linkActivated.connect(lambda _: self._on_manage_talks_clicked())

        #manage_link.setFont(QFont("Arial", 11))
        #manage_link.setStyleSheet("""
        #    QLabel { color: #64748b; }
        #    QLabel:hover { color: #334155; }
        #    a { color: inherit; text-decoration: none; }
        #    a:hover { text-decoration: underline; }
        #""")

        #row.addWidget(manage_link)
        #row.addStretch(1)

        layout.addWidget(bottom_row)

        return content

    def _create_content_obs(self) -> QWidget:
        """Create main content area.

        Returns:
            QWidget containing content
        """
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(22, 22, 22, 18)
        layout.setSpacing(0)

        # Brand section
        #brand = self._create_brand()
        #layout.addWidget(brand)

        # Just One Talk section
        layout.addSpacing(18)
        single_section = self._create_section(
            "Just One Talk",
            "Quick setup · Closes when done",
            "RECOMMENDED",
            "Start one presentation. Window closes automatically when finished.",
            "▶ Start Presenting",
            self._on_direct_talk_clicked,
            True
        )
        layout.addWidget(single_section)

        # Divider
        layout.addSpacing(14)
        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setStyleSheet("background: rgba(15, 23, 42, 0.08); max-height: 1px;")
        layout.addWidget(divider)
        layout.addSpacing(14)

        # Multiple Talks section
        multiple_section = self._create_section(
            "Multiple Talks",
            "Conference & event mode · Stays running",
            None,
            "Manage multiple sessions in sequence. Admin panel runs in background.",
            "⚙ Set up conference…",
            self._on_conference_clicked,
            False
        )
        layout.addWidget(multiple_section)

        # Divider
        layout.addSpacing(14)
        divider2 = QFrame()
        divider2.setFrameShape(QFrame.HLine)
        divider2.setStyleSheet("background: rgba(15, 23, 42, 0.08); max-height: 1px;")
        layout.addWidget(divider2)
        layout.addSpacing(14)

        # Manage Talks section
        manage_section = self._create_section(
            "Manage Past Talks",
            "Edit or delete recorded sessions",
            None,
            "View, rename, or delete previously recorded talks and presentations.",
            "📋 Manage talks…",
            self._on_manage_talks_clicked,
            False
        )
        layout.addWidget(manage_section)

        return content

    def _create_brand(self) -> QWidget:
        """Create brand section with logo and title.

        Returns:
            QWidget containing brand elements
        """
        brand = QWidget()
        layout = QHBoxLayout(brand)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        # Logo
        logo_label = QLabel()
        logo_pixmap = self._load_logo()

        if logo_pixmap:
            scaled_logo = logo_pixmap.scaled(46, 46, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            logo_label.setPixmap(scaled_logo)
        else:
            # Gradient placeholder
            logo_label.setFixedSize(46, 46)
            logo_label.setStyleSheet("""
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #2563eb, stop:1 #7c3aed
                );
                border-radius: 14px;
            """)

        layout.addWidget(logo_label)

        # Text
        text_widget = QWidget()
        text_layout = QVBoxLayout(text_widget)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(6)

        title = QLabel("SeenSlide")
        title.setFont(QFont("Arial", 20, QFont.Bold))
        title.setStyleSheet("color: #0f172a; letter-spacing: -0.2px;")
        text_layout.addWidget(title)

        subtitle = QLabel("Control slides already on screen")
        subtitle.setFont(QFont("Arial", 13))
        subtitle.setStyleSheet("color: #64748b;")
        text_layout.addWidget(subtitle)

        layout.addWidget(text_widget)
        layout.addStretch()

        return brand


    def _create_section(
        self,
        title: str,
        meta: str,
        pill: Optional[str],
        hint: str,
        button_text: str,
        button_callback,
        is_primary: bool
    ) -> QWidget:
        """
        Create a mode selection card (matches target visuals):
        - White card, subtle border, rounded corners
        - Optional pill badge on the right
        - Left-aligned, content-sized button (not full width)
        - Calm spacing and typography
        - Optional soft shadow
        """

        # --- Outer wrapper (just spacing between cards; no visual styling) ---
        section = QWidget()
        section.setStyleSheet("background: transparent;")
        outer = QVBoxLayout(section)
        outer.setContentsMargins(20, 0, 20, 0)
        outer.setSpacing(0)

        # --- Card container ---
        card = QFrame()
        card.setObjectName("Card")
        card.setStyleSheet("""
            QFrame#Card {
                background: #ffffff;
                border: 1px solid rgba(15, 23, 42, 0.10);
                border-radius: 16px;
            }
        """)

        # Optional shadow (nice for launcher; remove if you dislike it)
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(26)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(2, 6, 23, 30))
        card.setGraphicsEffect(shadow)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 16, 18, 16)
        card_layout.setSpacing(10)

        # --- Header row: title/meta on left, pill on right ---
        header = QWidget()
        header.setStyleSheet("background: transparent;")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        #header_layout.setSpacing(20)

        # Left stack (title + meta)
        text_col = QWidget()
        text_col.setStyleSheet("background: transparent;")
        text_col_layout = QVBoxLayout(text_col)
        text_col_layout.setContentsMargins(0, 0, 0, 0)
        text_col_layout.setSpacing(5)

        title_label = QLabel(title)
        title_label.setFont(QFont("Arial", 11, QFont.Bold))
        title_label.setStyleSheet("color: #0f172a; background: transparent;")
        title_label.setWordWrap(False)

        meta_label = QLabel(meta)
        meta_label.setFont(QFont("Arial", 8))
        meta_label.setStyleSheet("color: #64748b; background: transparent;")
        meta_label.setWordWrap(False)

        text_col_layout.addWidget(title_label)
        text_col_layout.addWidget(meta_label)

        header_layout.addWidget(text_col, 1)

        if pill:
            pill_label = QLabel(pill)
            pill_label.setFont(QFont("Arial", 9, QFont.DemiBold))
            pill_label.setStyleSheet("""
                color: rgba(37, 99, 235, 0.7);
                background: rgba(37, 99, 235, 0.1);
                border: 1px solid rgba(37, 99, 235, 0.0);
                padding: 3px 10px;
                border-radius: 50px;
            """)
            pill_label.setAlignment(Qt.AlignCenter)
            pill_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            header_layout.addWidget(pill_label, 0, Qt.AlignTop | Qt.AlignRight)

        card_layout.addWidget(header)

        # --- Button row (left-aligned, NOT full width) ---
        button = QPushButton(button_text)
        button.setCursor(Qt.PointingHandCursor)
        button.setFont(QFont("Arial", 11, QFont.Bold))
        button.setMinimumHeight(42)
        button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)  # <- key difference vs full-width

        if is_primary:
            button.setStyleSheet("""
                QPushButton {
                    background: #2563eb;
                    color: white;
                    border: none;
                    border-radius: 12px;
                    padding: 8px 16px;
                }
                QPushButton:hover { background: #1d4ed8; }
                QPushButton:pressed { background: #1e40af; }
            """)
        else:
            button.setStyleSheet("""
                QPushButton {
                    background: #0f172a;
                    color: white;
                    border: none;
                    border-radius: 12px;
                    padding: 8px 16px;
                }
                QPushButton:hover { background: #1e293b; }
                QPushButton:pressed { background: #0f172a; }
            """)

        button.clicked.connect(button_callback)

        button_row = QWidget()
        button_row.setStyleSheet("background: transparent;")
        br = QHBoxLayout(button_row)
        br.setContentsMargins(0, 2, 0, 0)
        br.setSpacing(0)
        br.addWidget(button, 0, Qt.AlignLeft)
        br.addStretch(1)

        card_layout.addWidget(button_row)

        # --- Hint text (smaller and calmer) ---
        hint_label = QLabel(hint)
        hint_label.setFont(QFont("Arial", 7))
        hint_label.setStyleSheet("color: #64748b; background: transparent;")
        hint_label.setWordWrap(True)
        hint_label.setContentsMargins(0, 2, 0, 0)
        card_layout.addWidget(hint_label)

        outer.addWidget(card)
        return section

    def _create_section_obs(
        self,
        title: str,
        meta: str,
        pill: Optional[str],
        hint: str,
        button_text: str,
        button_callback,
        is_primary: bool
    ) -> QWidget:
        """Create a mode selection section.

        Args:
            title: Section title
            meta: Metadata/subtitle
            pill: Optional pill badge text
            hint: Hint text below button
            button_text: Button label
            button_callback: Button click handler
            is_primary: Whether to use primary button style

        Returns:
            QWidget containing section
        """
        section = QWidget()
        section.setStyleSheet("background: transparent;")

        layout = QVBoxLayout(section)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Container frame with background
        container = QFrame()
        container.setObjectName("sectionContainer")
        container.setStyleSheet("""
            QFrame#sectionContainer {
                background: rgba(2, 6, 23, 0.015);
                border: 1px solid rgba(15, 23, 42, 0.12);
                border-radius: 16px;
            }
        """)

        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(16, 16, 16, 16)
        container_layout.setSpacing(12)

        # Header row
        header = QWidget()
        header.setStyleSheet("background: transparent;")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(10)

        # Title and meta
        title_widget = QWidget()
        title_widget.setStyleSheet("background: transparent;")
        title_layout = QVBoxLayout(title_widget)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(4)

        title_label = QLabel(title)
        title_label.setFont(QFont("Arial", 14, QFont.Bold))
        title_label.setStyleSheet("color: #0f172a; background: transparent;")
        title_layout.addWidget(title_label)

        meta_label = QLabel(meta)
        meta_label.setFont(QFont("Arial", 12))
        meta_label.setStyleSheet("color: #64748b; background: transparent;")
        title_layout.addWidget(meta_label)

        header_layout.addWidget(title_widget, 1)

        # Pill badge
        if pill:
            pill_label = QLabel(pill)
            pill_label.setFont(QFont("Arial", 10))
            pill_label.setFixedHeight(24)
            pill_label.setStyleSheet("""
                color: #1d4ed8;
                background: rgba(37, 99, 235, 0.10);
                border: 1px solid rgba(37, 99, 235, 0.18);
                padding: 4px 8px;
                border-radius: 12px;
            """)
            pill_label.setAlignment(Qt.AlignCenter)
            header_layout.addWidget(pill_label)

        container_layout.addWidget(header)

        # Button
        button = QPushButton(button_text)
        button.setFont(QFont("Arial", 13, QFont.Bold))
        button.setCursor(Qt.PointingHandCursor)
        button.setMinimumHeight(44)

        if is_primary:
            button.setStyleSheet("""
                QPushButton {
                    background: #2563eb;
                    color: white;
                    border: none;
                    border-radius: 12px;
                    padding: 12px 14px;
                }
                QPushButton:hover {
                    background: #1d4ed8;
                }
                QPushButton:pressed {
                    background: #1e40af;
                }
            """)
        else:
            button.setStyleSheet("""
                QPushButton {
                    background: #0f172a;
                    color: white;
                    border: none;
                    border-radius: 12px;
                    padding: 12px 14px;
                }
                QPushButton:hover {
                    background: #1e293b;
                }
                QPushButton:pressed {
                    background: #0f172a;
                }
            """)

        button.clicked.connect(button_callback)
        container_layout.addWidget(button)

        # Hint
        hint_label = QLabel(hint)
        hint_label.setFont(QFont("Arial", 11))
        hint_label.setStyleSheet("color: #64748b; background: transparent;")
        hint_label.setWordWrap(True)
        container_layout.addWidget(hint_label)

        layout.addWidget(container)

        return section

    def _create_footer(self) -> QWidget:
        """Create footer with subtle keyboard hints."""
        footer = QWidget()
        #footer.setStyleSheet("""
        #    background: transparent;
        #    border-top: 1px solid rgba(15, 23, 42, 0.08);
        #""")

        layout = QHBoxLayout(footer)
        layout.setContentsMargins(18, 10, 18, 12)
        layout.setSpacing(12)

        # --- Keyboard hints (left) ---
        hints = QWidget()
        hints_layout = QHBoxLayout(hints)
        hints_layout.setContentsMargins(0, 0, 0, 0)
        hints_layout.setSpacing(10)

        def keycap(text: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setFont(QFont("Courier", 10))
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("""
                QLabel {
                    color: #64748b;
                    background: rgba(2, 6, 23, 0.03);
                    border: 1px solid rgba(15, 23, 42, 0.12);
                    border-bottom-color: rgba(2, 6, 23, 0.18);
                    border-radius: 6px;
                    padding: 2px 8px;
                }
            """)
            return lbl

        def hint(text: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setFont(QFont("Arial", 9))
            lbl.setStyleSheet("color: #64748b;")
            return lbl

        for key, action in [
            ("Enter", "Start"),
            ("C", "Conference"),
            ("Esc", "Quit"),
        ]:
            hints_layout.addWidget(keycap(key))
            hints_layout.addWidget(hint(action))

        layout.addWidget(hints)
        layout.addStretch(1)

        # --- Footer label (right, very quiet) ---
        footer_text = QLabel("SeenSlide")
        footer_text.setFont(QFont("Arial", 11))
        footer_text.setStyleSheet("color: #94a3b8;")
        layout.addWidget(footer_text, 0, Qt.AlignRight | Qt.AlignVCenter)

        return footer

    def _create_footer_obs(self) -> QWidget:
        """Create footer with shortcuts.

        Returns:
            QWidget containing footer
        """
        footer = QWidget()
        footer.setStyleSheet("""
            background: transparent;
            border-top: 1px solid rgba(15, 23, 42, 0.08);
            padding: 12px 18px 14px;
        """)

        layout = QHBoxLayout(footer)
        layout.setContentsMargins(18, 12, 18, 14)
        layout.setSpacing(10)

        # Shortcuts
        shortcuts = QWidget()
        shortcuts_layout = QHBoxLayout(shortcuts)
        shortcuts_layout.setContentsMargins(0, 0, 0, 0)
        shortcuts_layout.setSpacing(0)

        for key, action in [("Enter", "Start"), ("C", "Conference"), ("M", "Manage"), ("Esc", "Quit")]:
            key_label = QLabel(key)
            key_label.setFont(QFont("Courier", 11))
            key_label.setStyleSheet("""
                color: #64748b;
                background: rgba(2, 6, 23, 0.02);
                border: 1px solid rgba(15, 23, 42, 0.12);
                border-bottom-color: rgba(2, 6, 23, 0.18);
                border-radius: 6px;
                padding: 2px 6px;
                margin-right: 6px;
            """)
            shortcuts_layout.addWidget(key_label)

            action_label = QLabel(action)
            action_label.setFont(QFont("Arial", 12))
            action_label.setStyleSheet("color: #64748b; margin-right: 10px;")
            shortcuts_layout.addWidget(action_label)

        layout.addWidget(shortcuts)
        layout.addStretch()

        # Footer text
        footer_text = QLabel("SeenSlide Launcher")
        footer_text.setFont(QFont("Arial", 12))
        footer_text.setStyleSheet("color: #64748b;")
        layout.addWidget(footer_text)

        return footer

    def _load_logo(self) -> Optional[QPixmap]:
        """Load application logo from resources.

        Returns:
            QPixmap with logo, or None if not found
        """
        possible_paths = [
            Path(__file__).parent.parent / "resources" / "icons" / "logo.png",
            Path.home() / ".config" / "seenslide" / "logo.png",
        ]

        for logo_path in possible_paths:
            if logo_path.exists():
                # logger.info(f"Loading logo from: {logo_path}")
                return QPixmap(str(logo_path))

        logger.warning("Logo file not found")
        return None

    def _setup_shortcuts(self):
        """Setup keyboard shortcuts."""
        from PyQt5.QtWidgets import QShortcut
        from PyQt5.QtGui import QKeySequence

        QShortcut(QKeySequence("Return"), self, self._on_direct_talk_clicked)
        QShortcut(QKeySequence("Enter"), self, self._on_direct_talk_clicked)
        QShortcut(QKeySequence("C"), self, self._on_conference_clicked)
        QShortcut(QKeySequence("M"), self, self._on_manage_talks_clicked)
        QShortcut(QKeySequence("Escape"), self, self.close)

        logger.info("Keyboard shortcuts: Enter=Start, C=Conference, M=Manage, Esc=Quit")

    def _on_direct_talk_clicked(self):
        """Handle Direct Talk button click."""
        logger.info("Just One Talk selected")
        self.direct_talk_selected.emit()

    def _on_conference_clicked(self):
        """Handle Conference Mode button click."""
        logger.info("Multiple Talks selected")
        self.conference_mode_selected.emit()

    def _on_manage_talks_clicked(self):
        """Handle Manage Talks button click."""
        logger.info("Manage Past Talks selected")
        self.manage_talks_selected.emit()
