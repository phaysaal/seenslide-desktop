"""Shared visual constants and helpers for SeenSlide desktop UI.

All windows should use these to maintain a consistent look.
"""

from PyQt5.QtWidgets import QWidget, QFrame, QGraphicsDropShadowEffect
from PyQt5.QtGui import QPalette, QColor, QFont


# ── Colour palette ──────────────────────────────────────────────────

BG          = "#f6f7fb"
CARD_BG     = "#ffffff"
CARD_BORDER = "rgba(15, 23, 42, 0.10)"

PRIMARY         = "#2563eb"
PRIMARY_HOVER   = "#1d4ed8"
PRIMARY_PRESSED = "#1e40af"

SECONDARY       = "#0f172a"
SECONDARY_HOVER = "#1e293b"

DANGER          = "#dc2626"
DANGER_HOVER    = "#b91c1c"

SUCCESS         = "#16a34a"
SUCCESS_HOVER   = "#15803d"

TEXT        = "#0f172a"
TEXT_MUTED  = "#64748b"
TEXT_FAINT  = "#94a3b8"

INPUT_BORDER       = "#d1d5db"
INPUT_FOCUS_BORDER = PRIMARY
DISABLED_BG        = "#94a3b8"

CARD_RADIUS  = 16
BTN_RADIUS   = 12
INPUT_RADIUS = 8

SHADOW_BLUR   = 26
SHADOW_OFFSET = 10
SHADOW_COLOR  = QColor(2, 6, 23, 30)


# ── Fonts ───────────────────────────────────────────────────────────

FONT_TITLE    = QFont("Arial", 18, QFont.Bold)
FONT_SECTION  = QFont("Arial", 12, QFont.Bold)
FONT_BODY     = QFont("Arial", 11)
FONT_SMALL    = QFont("Arial", 10)
FONT_HINT     = QFont("Arial", 9)


# ── Helpers ─────────────────────────────────────────────────────────

def set_window_bg(widget: QWidget):
    """Apply the standard #f6f7fb window background."""
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(BG))
    widget.setPalette(pal)
    widget.setAutoFillBackground(True)


def make_card(parent=None) -> QFrame:
    """Return a white rounded card with drop shadow."""
    card = QFrame(parent)
    card.setObjectName("card")
    card.setStyleSheet(f"""
        QFrame#card {{
            background: {CARD_BG};
            border: 1px solid {CARD_BORDER};
            border-radius: {CARD_RADIUS}px;
        }}
    """)
    shadow = QGraphicsDropShadowEffect(card)
    shadow.setBlurRadius(SHADOW_BLUR)
    shadow.setOffset(0, SHADOW_OFFSET)
    shadow.setColor(SHADOW_COLOR)
    card.setGraphicsEffect(shadow)
    return card


def btn_primary(extra: str = "") -> str:
    return f"""
        QPushButton {{
            background: {PRIMARY}; color: white; border: none;
            border-radius: {BTN_RADIUS}px; padding: 8px 18px;
            font-size: 13px; font-weight: bold;
            {extra}
        }}
        QPushButton:hover {{ background: {PRIMARY_HOVER}; }}
        QPushButton:pressed {{ background: {PRIMARY_PRESSED}; }}
        QPushButton:disabled {{ background: {DISABLED_BG}; }}
    """


def btn_secondary(extra: str = "") -> str:
    return f"""
        QPushButton {{
            background: {SECONDARY}; color: white; border: none;
            border-radius: {BTN_RADIUS}px; padding: 8px 18px;
            font-size: 13px; font-weight: bold;
            {extra}
        }}
        QPushButton:hover {{ background: {SECONDARY_HOVER}; }}
        QPushButton:disabled {{ background: {DISABLED_BG}; }}
    """


def btn_danger(extra: str = "") -> str:
    return f"""
        QPushButton {{
            background: {DANGER}; color: white; border: none;
            border-radius: {BTN_RADIUS}px; padding: 8px 18px;
            font-size: 13px; font-weight: bold;
            {extra}
        }}
        QPushButton:hover {{ background: {DANGER_HOVER}; }}
        QPushButton:disabled {{ background: {DISABLED_BG}; }}
    """


def btn_ghost(extra: str = "") -> str:
    return f"""
        QPushButton {{
            background: #e5e7eb; color: {TEXT}; border: none;
            border-radius: {BTN_RADIUS}px; padding: 8px 18px;
            font-size: 13px;
            {extra}
        }}
        QPushButton:hover {{ background: #d1d5db; }}
    """


def input_style() -> str:
    return f"""
        QLineEdit, QComboBox, QTextEdit {{
            background: white;
            border: 1px solid {INPUT_BORDER};
            border-radius: {INPUT_RADIUS}px;
            padding: 8px 12px;
            color: {TEXT};
            font-size: 13px;
        }}
        QLineEdit:focus, QComboBox:focus, QTextEdit:focus {{
            border-color: {INPUT_FOCUS_BORDER};
        }}
    """


def section_title_style() -> str:
    return f"color: {TEXT}; font-size: 12px; font-weight: bold;"


def hint_style() -> str:
    return f"color: {TEXT_MUTED}; font-size: 11px;"
