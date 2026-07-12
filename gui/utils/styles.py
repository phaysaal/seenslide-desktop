"""Shared visual constants and helpers for SeenSlide desktop UI.

All windows should use these to maintain a consistent look.
"""

from PyQt5.QtWidgets import QWidget, QFrame, QGraphicsDropShadowEffect
from PyQt5.QtGui import QPalette, QColor, QFont


# ── Colour palette ──────────────────────────────────────────────────

# Two palettes with identical keys — DARK (matches seenslide.com) and LIGHT.
# The active one populates the module-level tokens below; apply_mode() swaps
# them so shared dialogs/windows re-theme along with the dashboard.

# Monospace face for technical identifiers (codes, IDs, specs). Theme-free.
MONO = "'JetBrains Mono', 'Cascadia Code', 'DejaVu Sans Mono', Menlo, Consolas, monospace"

_DARK = {
    "BG": "#07070a",
    "CARD_BG": "#14141e",
    "CARD_BORDER": "rgba(255, 255, 255, 0.09)",
    "PRIMARY": "#10b981",
    "PRIMARY_HOVER": "#12c88d",
    "PRIMARY_PRESSED": "#059669",
    "PRIMARY_TINT": "rgba(16, 185, 129, 0.14)",
    "PRIMARY_TEXT_ON": "#06110c",
    "SECONDARY": "#191922",
    "SECONDARY_HOVER": "#20202b",
    "DANGER": "#f0526b",
    "DANGER_HOVER": "#e5484d",
    "SUCCESS": "#10b981",
    "SUCCESS_HOVER": "#059669",
    "TEXT": "rgba(255, 255, 255, 0.95)",
    "TEXT_MUTED": "rgba(255, 255, 255, 0.60)",
    "TEXT_FAINT": "rgba(255, 255, 255, 0.40)",
    "INPUT_BG": "#101019",
    "INPUT_BORDER": "rgba(255, 255, 255, 0.14)",
    "DISABLED_BG": "#2b2b36",
}

_LIGHT = {
    "BG": "#f6f7fb",
    "CARD_BG": "#ffffff",
    "CARD_BORDER": "rgba(15, 23, 42, 0.08)",
    "PRIMARY": "#2563eb",
    "PRIMARY_HOVER": "#3b82f6",
    "PRIMARY_PRESSED": "#1d4ed8",
    "PRIMARY_TINT": "rgba(37, 99, 235, 0.10)",
    "PRIMARY_TEXT_ON": "#ffffff",
    "SECONDARY": "#eef1f6",
    "SECONDARY_HOVER": "#e2e7f0",
    "DANGER": "#dc2626",
    "DANGER_HOVER": "#b91c1c",
    "SUCCESS": "#16a34a",
    "SUCCESS_HOVER": "#15803d",
    "TEXT": "#0f172a",
    "TEXT_MUTED": "#64748b",
    "TEXT_FAINT": "#94a3b8",
    "INPUT_BG": "#ffffff",
    "INPUT_BORDER": "rgba(15, 23, 42, 0.14)",
    "DISABLED_BG": "#e2e8f0",
}

_PALETTES = {"dark": _DARK, "light": _LIGHT}

# Explicit declarations (DARK defaults) so tooling resolves the names;
# apply_mode() overwrites them at runtime when the theme changes.
BG          = _DARK["BG"]
CARD_BG     = _DARK["CARD_BG"]
CARD_BORDER = _DARK["CARD_BORDER"]
PRIMARY         = _DARK["PRIMARY"]
PRIMARY_HOVER   = _DARK["PRIMARY_HOVER"]
PRIMARY_PRESSED = _DARK["PRIMARY_PRESSED"]
PRIMARY_TINT    = _DARK["PRIMARY_TINT"]
PRIMARY_TEXT_ON = _DARK["PRIMARY_TEXT_ON"]
SECONDARY       = _DARK["SECONDARY"]
SECONDARY_HOVER = _DARK["SECONDARY_HOVER"]
DANGER          = _DARK["DANGER"]
DANGER_HOVER    = _DARK["DANGER_HOVER"]
SUCCESS         = _DARK["SUCCESS"]
SUCCESS_HOVER   = _DARK["SUCCESS_HOVER"]
TEXT        = _DARK["TEXT"]
TEXT_MUTED  = _DARK["TEXT_MUTED"]
TEXT_FAINT  = _DARK["TEXT_FAINT"]
INPUT_BG           = _DARK["INPUT_BG"]
INPUT_BORDER       = _DARK["INPUT_BORDER"]
INPUT_FOCUS_BORDER = _DARK["PRIMARY"]
DISABLED_BG        = _DARK["DISABLED_BG"]
THEME_MODE  = "dark"


def apply_mode(mode):
    """Swap the module-level colour tokens to the named palette ('dark'|'light')."""
    pal = _PALETTES.get(mode, _DARK)
    g = globals()
    g.update(pal)
    g["INPUT_FOCUS_BORDER"] = pal["PRIMARY"]
    g["THEME_MODE"] = mode if mode in _PALETTES else "dark"


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
