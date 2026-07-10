"""Dialog for creating a new cloud session."""

from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)


class NewSessionDialog(QDialog):
    """Single-field dialog: ask the user for a session title.

    The title is sent to the cloud as `presenter_name` (which the backend
    treats as the class/session title).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Session")
        self.setModal(True)
        self.setMinimumWidth(420)

        self._title: str = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        heading = QLabel("Create a new session")
        heading.setStyleSheet("font-size: 16px; color: #1e293b;")
        layout.addWidget(heading)

        hint = QLabel(
            "A session is a container for talks (e.g., a class or course). "
            "You can add talks to it later."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #64748b; font-size: 12px;")
        layout.addWidget(hint)

        layout.addSpacing(4)

        label = QLabel("Title")
        label.setStyleSheet("color: #475569; font-size: 12px;")
        layout.addWidget(label)

        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("e.g. Physics 101 — Spring 2026")
        self.title_input.setMinimumHeight(34)
        self.title_input.setStyleSheet(
            "QLineEdit { padding: 6px 10px; border: 1px solid #e2e8f0;"
            " border-radius: 6px; font-size: 13px; background: #f8fafc; }"
            "QLineEdit:focus { border-color: #3b82f6; background: white; }"
        )
        self.title_input.textChanged.connect(self._on_text_changed)
        self.title_input.returnPressed.connect(self._try_accept)
        layout.addWidget(self.title_input)

        layout.addSpacing(8)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setFixedHeight(32)
        cancel_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #475569;"
            " border: 1px solid #e2e8f0; border-radius: 6px; padding: 0 16px; font-size: 12px; }"
            "QPushButton:hover { background: #f1f5f9; }"
        )
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        self.create_btn = QPushButton("Create")
        self.create_btn.setCursor(Qt.PointingHandCursor)
        self.create_btn.setFixedHeight(32)
        self.create_btn.setEnabled(False)
        self.create_btn.setStyleSheet(
            "QPushButton { background: #3b82f6; color: white; border: none;"
            " border-radius: 6px; padding: 0 18px; font-size: 12px; }"
            "QPushButton:hover { background: #2563eb; }"
            "QPushButton:disabled { background: #cbd5e1; }"
        )
        self.create_btn.clicked.connect(self._try_accept)
        btn_row.addWidget(self.create_btn)

        layout.addLayout(btn_row)

        self.title_input.setFocus()

    def _on_text_changed(self, text: str):
        self.create_btn.setEnabled(bool(text.strip()))

    def _try_accept(self):
        text = self.title_input.text().strip()
        if not text:
            return
        self._title = text
        self.accept()

    def get_title(self) -> str:
        return self._title

    @staticmethod
    def get_new_title(parent=None) -> Optional[str]:
        """Show the dialog modally; return the entered title or None on cancel."""
        dlg = NewSessionDialog(parent)
        if dlg.exec_() == QDialog.Accepted:
            return dlg.get_title()
        return None
