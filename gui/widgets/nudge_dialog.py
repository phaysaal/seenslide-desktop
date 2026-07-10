"""Nudge dialog — invites an anonymous user to register.

The same dialog renders three tiers (gentle / reminder / enforce). Only
the copy and the "Later" button differ across tiers. The enforce tier
hides "Later" entirely so the user must sign in or close the app.
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from core.nudge import NudgeTier


_COPY = {
    NudgeTier.GENTLE: {
        "title": "Save your work",
        "body": (
            "You've captured your first slide on this device. SeenSlide is "
            "running as an anonymous account — your sessions live only here. "
            "Add an email or phone number to keep your work safe across devices."
        ),
        "later": "Maybe later",
    },
    NudgeTier.REMINDER: {
        "title": "Still using anonymously?",
        "body": (
            "Your sessions on this device are still tied to a single anonymous "
            "account. If anything happens to this machine, you'll lose them. "
            "It only takes a moment to register an email or phone."
        ),
        "later": "Remind me later",
    },
    NudgeTier.ENFORCE: {
        "title": "Please register to continue",
        "body": (
            "You've captured a substantial number of slides on this device. "
            "To keep using SeenSlide and protect your work, please register "
            "an email or phone number now."
        ),
        "later": None,  # No skip path
    },
}


class NudgeDialog(QDialog):
    def __init__(self, parent=None, tier: NudgeTier = NudgeTier.GENTLE):
        super().__init__(parent)
        self.tier = tier
        self.setWindowTitle("Sign In or Register")
        self.setModal(True)
        self.setMinimumWidth(460)

        copy = _COPY[tier]
        is_enforce = tier == NudgeTier.ENFORCE
        if is_enforce:
            # Block close via window decorations / Esc.
            self.setWindowFlags(self.windowFlags() | Qt.CustomizeWindowHint)
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowCloseButtonHint)

        self._signed_in = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 22)
        layout.setSpacing(12)

        title = QLabel(copy["title"])
        title.setStyleSheet("font-size: 18px; color: #1e293b;")
        layout.addWidget(title)

        body = QLabel(copy["body"])
        body.setWordWrap(True)
        body.setStyleSheet("color: #475569; font-size: 13px;")
        layout.addWidget(body)

        layout.addSpacing(6)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        if copy["later"]:
            self.later_btn = QPushButton(copy["later"])
            self.later_btn.setCursor(Qt.PointingHandCursor)
            self.later_btn.setFixedHeight(34)
            self.later_btn.setStyleSheet(
                "QPushButton { background: transparent; color: #475569;"
                " border: 1px solid #e2e8f0; border-radius: 6px; padding: 0 16px; font-size: 12px; }"
                "QPushButton:hover { background: #f1f5f9; }"
            )
            self.later_btn.clicked.connect(self.reject)
            btn_row.addWidget(self.later_btn)

        self.signin_btn = QPushButton("Sign In or Register")
        self.signin_btn.setCursor(Qt.PointingHandCursor)
        self.signin_btn.setFixedHeight(34)
        self.signin_btn.setStyleSheet(
            "QPushButton { background: #3b82f6; color: white; border: none;"
            " border-radius: 6px; padding: 0 18px; font-size: 12px; }"
            "QPushButton:hover { background: #2563eb; }"
        )
        self.signin_btn.clicked.connect(self._on_signin_clicked)
        btn_row.addWidget(self.signin_btn)

        layout.addLayout(btn_row)

    def _on_signin_clicked(self):
        # Defer to the parent so the existing SignInDialog opens. Caller
        # should check `signed_in()` after `exec_()` returns.
        self._signed_in = True
        self.accept()

    def signed_in(self) -> bool:
        return self._signed_in

    # Block Esc on enforce tier.
    def keyPressEvent(self, event):
        if self.tier == NudgeTier.ENFORCE and event.key() == Qt.Key_Escape:
            event.ignore()
            return
        super().keyPressEvent(event)
