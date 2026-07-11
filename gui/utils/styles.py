"""Shared visual constants and helpers for SeenSlide desktop UI.

All windows should use these to maintain a consistent look.
"""

from PyQt5.QtWidgets import QWidget, QFrame, QGraphicsDropShadowEffect
from PyQt5.QtGui import QPalette, QColor, QFont


# ── Colour palette ──────────────────────────────────────────────────

# Dark theme matched to seenslide.com.
BG          = "#07070a"
CARD_BG     = "#14141e"
CARD_BORDER = "rgba(255, 255, 255, 0.09)"

# One accent for all interaction — emerald green.
PRIMARY         = "#10b981"
PRIMARY_HOVER   = "#12c88d"
PRIMARY_PRESSED = "#059669"
PRIMARY_TINT    = "rgba(16, 185, 129, 0.14)"

SECONDARY       = "#191922"
SECONDARY_HOVER = "#20202b"

# Semantic — state only, never used as the accent.
DANGER          = "#f0526b"
DANGER_HOVER    = "#e5484d"

SUCCESS         = "#10b981"
SUCCESS_HOVER   = "#059669"

TEXT        = "rgba(255, 255, 255, 0.95)"
TEXT_MUTED  = "rgba(255, 255, 255, 0.60)"
TEXT_FAINT  = "rgba(255, 255, 255, 0.40)"

INPUT_BG           = "#101019"
INPUT_BORDER       = "rgba(255, 255, 255, 0.14)"
INPUT_FOCUS_BORDER = PRIMARY
DISABLED_BG        = "#2b2b36"

# Monospace face for technical identifiers (codes, IDs, specs).
MONO = "'JetBrains Mono', 'Cascadia Code', 'DejaVu Sans Mono', Menlo, Consolas, monospace"

CARD_RADIUS  = 14
BTN_RADIUS   = 10
INPUT_RADIUS = 10

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
            background: {SECONDARY}; color: {TEXT}; border: 1px solid {CARD_BORDER};
            border-radius: {BTN_RADIUS}px; padding: 8px 18px;
            font-size: 13px;
            {extra}
        }}
        QPushButton:hover {{ background: #20202b; }}
    """


def input_style() -> str:
    return f"""
        QLineEdit, QComboBox, QTextEdit {{
            background: {INPUT_BG};
            border: 1px solid {INPUT_BORDER};
            border-radius: {INPUT_RADIUS}px;
            padding: 10px 13px;
            color: {TEXT};
            font-size: 13px;
        }}
        QLineEdit:focus, QComboBox:focus, QTextEdit:focus {{
            border: 2px solid {INPUT_FOCUS_BORDER};
            background: {CARD_BG};
            padding: 9px 12px;
        }}
        QLineEdit::placeholder {{ color: {TEXT_FAINT}; }}
    """


def mono_style(size: int = 12, color: str = None) -> str:
    """Inline style for technical identifiers (codes, IDs, specs)."""
    return f"font-family: {MONO}; font-size: {size}px; letter-spacing: 0.3px; color: {color or TEXT_MUTED};"


def chip_style(kind: str = "ok") -> str:
    """Pill that encodes state at a glance: ok | live | local | accent."""
    palette = {
        "ok":     ("#34d399", "rgba(16, 185, 129, 0.14)"),
        "live":   ("#ff8494", "rgba(240, 82, 107, 0.14)"),
        "local":  ("#fbbf5a", "rgba(245, 158, 11, 0.14)"),
        "accent": ("#34d399", PRIMARY_TINT),
    }
    fg, bg = palette.get(kind, palette["ok"])
    return (f"QLabel {{ color: {fg}; background: {bg}; border-radius: 999px;"
            f" padding: 3px 9px; font-size: 11px; font-weight: 600; }}")


def section_title_style() -> str:
    return f"color: {TEXT}; font-size: 12px; font-weight: bold;"


def hint_style() -> str:
    return f"color: {TEXT_MUTED}; font-size: 11px;"
