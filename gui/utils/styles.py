"""Shared visual constants and helpers for SeenSlide desktop UI.

All windows should use these to maintain a consistent look.
"""

from PyQt5.QtWidgets import QWidget, QFrame, QGraphicsDropShadowEffect
from PyQt5.QtGui import QPalette, QColor, QFont


# ── Colour palette ──────────────────────────────────────────────────

BG          = "#f4f6f9"
CARD_BG     = "#ffffff"
CARD_BORDER = "#e3e7ee"

# One accent for all interaction — a deep cerulean, not the bright SaaS blue.
PRIMARY         = "#2266d4"
PRIMARY_HOVER   = "#1b54b3"
PRIMARY_PRESSED = "#164393"
PRIMARY_TINT    = "#e9f1fe"

SECONDARY       = "#171b22"
SECONDARY_HOVER = "#2b313c"

# Semantic — state only, never used as the accent.
DANGER          = "#e5484d"
DANGER_HOVER    = "#cf3b40"

SUCCESS         = "#2e9e6b"
SUCCESS_HOVER   = "#268257"

TEXT        = "#171b22"
TEXT_MUTED  = "#5b6472"
TEXT_FAINT  = "#8b94a4"

INPUT_BG           = "#f5f7fb"
INPUT_BORDER       = "#cfd6e0"
INPUT_FOCUS_BORDER = PRIMARY
DISABLED_BG        = "#aab4c5"

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
        "ok":     (SUCCESS, "#e7f6ee"),
        "live":   (DANGER,  "#fdecec"),
        "local":  ("#c07d12", "#fbf1dd"),
        "accent": (PRIMARY, PRIMARY_TINT),
    }
    fg, bg = palette.get(kind, palette["ok"])
    return (f"QLabel {{ color: {fg}; background: {bg}; border-radius: 999px;"
            f" padding: 3px 9px; font-size: 11px; font-weight: 600; }}")


def section_title_style() -> str:
    return f"color: {TEXT}; font-size: 12px; font-weight: bold;"


def hint_style() -> str:
    return f"color: {TEXT_MUTED}; font-size: 11px;"
