"""Dialog for choosing who may view a cloud session (viewer access).

Three modes, mirroring the server's access_type:

  public              anyone with the link
  password_protected  anyone with the link AND the password
  private             only the presenter (invitations will extend this)

The password set here is the VIEWER password that students type into the
web or Android viewer. It is unrelated to the collection admin credential
used for multi-device re-attach.
"""

from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QButtonGroup,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

ACCESS_LABELS = {
    "public": "Public",
    "password_protected": "Password protected",
    "private": "Private",
}


def access_badge(access_type: Optional[str]) -> str:
    """Short human label for a session's access_type ('' for public/unknown)."""
    if access_type == "password_protected":
        return "🔒 Password"
    if access_type == "private":
        return "🔒 Private"
    return ""


class SessionAccessDialog(QDialog):
    """Pick an access mode (and a password when needed)."""

    MIN_PASSWORD = 6

    def __init__(self, session_name: str, session_id: str, current_access: str = "public", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Viewer Access")
        self.setModal(True)
        self.setMinimumWidth(460)

        self._access_type: str = current_access if current_access in ACCESS_LABELS else "public"
        self._password: Optional[str] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)

        heading = QLabel(f"Who can view “{session_name}”?")
        heading.setStyleSheet("font-size: 16px; color: #1e293b;")
        heading.setWordWrap(True)
        layout.addWidget(heading)

        sub = QLabel(f"Session {session_id}. Viewers open it from the shared link.")
        sub.setStyleSheet("color: #64748b; font-size: 12px;")
        sub.setWordWrap(True)
        layout.addWidget(sub)
        layout.addSpacing(4)

        self._group = QButtonGroup(self)
        self.radio_public = self._radio(
            "Public", "Anyone with the link can view.", "public", layout)
        self.radio_password = self._radio(
            "Password protected", "Anyone with the link who also enters the password.",
            "password_protected", layout)

        # Password fields (shown only for password mode)
        self.password_box = QWidget()
        pw_layout = QVBoxLayout(self.password_box)
        pw_layout.setContentsMargins(28, 0, 0, 0)
        pw_layout.setSpacing(6)
        self.password_input = self._password_field("New viewer password (min 6 characters)")
        self.password_confirm = self._password_field("Confirm password")
        pw_layout.addWidget(self.password_input)
        pw_layout.addWidget(self.password_confirm)
        self.password_note = QLabel(
            "Changing the password signs out current viewers within 12 hours."
            if current_access == "password_protected" else
            "Share the password out of band, e.g. write it on the board."
        )
        self.password_note.setStyleSheet("color: #64748b; font-size: 11px;")
        self.password_note.setWordWrap(True)
        pw_layout.addWidget(self.password_note)
        layout.addWidget(self.password_box)

        self.radio_private = self._radio(
            "Private", "Only you (signed in as the presenter) can view. "
            "Use this to hide a talk until it is ready.", "private", layout)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #dc2626; font-size: 12px;")
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

        layout.addSpacing(6)
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

        self.save_btn = QPushButton("Save")
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.setFixedHeight(32)
        self.save_btn.setDefault(True)
        self.save_btn.setStyleSheet(
            "QPushButton { background: #3b82f6; color: white; border: none;"
            " border-radius: 6px; padding: 0 20px; font-size: 12px; }"
            "QPushButton:hover { background: #2563eb; }"
            "QPushButton:disabled { background: #cbd5e1; }"
        )
        self.save_btn.clicked.connect(self._try_accept)
        btn_row.addWidget(self.save_btn)
        layout.addLayout(btn_row)

        # Initial state
        {"public": self.radio_public,
         "password_protected": self.radio_password,
         "private": self.radio_private}[self._access_type].setChecked(True)
        self._on_mode_changed()
        self._group.buttonToggled.connect(lambda *_: self._on_mode_changed())

    # ── UI helpers ────────────────────────────────────────────────

    def _radio(self, title: str, hint: str, value: str, layout: QVBoxLayout) -> QRadioButton:
        rb = QRadioButton(title)
        rb.setStyleSheet("font-size: 13px; color: #1e293b;")
        rb.setProperty("access_value", value)
        self._group.addButton(rb)
        layout.addWidget(rb)
        hint_label = QLabel(hint)
        hint_label.setStyleSheet("color: #64748b; font-size: 11px; margin-left: 24px;")
        hint_label.setWordWrap(True)
        layout.addWidget(hint_label)
        return rb

    @staticmethod
    def _password_field(placeholder: str) -> QLineEdit:
        edit = QLineEdit()
        edit.setEchoMode(QLineEdit.Password)
        edit.setPlaceholderText(placeholder)
        edit.setMinimumHeight(32)
        edit.setStyleSheet(
            "QLineEdit { padding: 6px 10px; border: 1px solid #e2e8f0;"
            " border-radius: 6px; font-size: 13px; background: #f8fafc; }"
            "QLineEdit:focus { border-color: #3b82f6; background: white; }"
        )
        return edit

    def _selected_mode(self) -> str:
        btn = self._group.checkedButton()
        return btn.property("access_value") if btn else "public"

    def _on_mode_changed(self):
        is_pw = self._selected_mode() == "password_protected"
        self.password_box.setVisible(is_pw)
        self.error_label.setVisible(False)
        if is_pw:
            self.password_input.setFocus()

    def _show_error(self, text: str):
        self.error_label.setText(text)
        self.error_label.setVisible(True)

    # ── Result ────────────────────────────────────────────────────

    def _try_accept(self):
        mode = self._selected_mode()
        if mode == "password_protected":
            pw = self.password_input.text()
            if len(pw) < self.MIN_PASSWORD:
                self._show_error(f"Password must be at least {self.MIN_PASSWORD} characters.")
                self.password_input.setFocus()
                return
            if pw != self.password_confirm.text():
                self._show_error("Passwords do not match.")
                self.password_confirm.setFocus()
                return
            self._password = pw
        else:
            self._password = None
        self._access_type = mode
        self.accept()

    @property
    def access_type(self) -> str:
        return self._access_type

    @property
    def password(self) -> Optional[str]:
        return self._password
