"""Sign-in / register dialog.

Driven by `core.identity`. Used to claim an anonymous device account by
attaching an email or phone + secret. The same dialog is used to log in
to an existing account on a fresh device — the cloud distinguishes the
two cases internally based on whether the identifier already exists.
"""

from typing import Optional

from PyQt5.QtCore import Qt, pyqtSignal, QThread
from PyQt5.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
)

from core.identity import identity, IdentityError


class _SignInWorker(QThread):
    succeeded = pyqtSignal(str)  # action ("upgraded" | "merged" | "login")
    failed = pyqtSignal(int, str)  # http status, message

    def __init__(self, mode: str, email: Optional[str], phone: Optional[str], secret: str):
        super().__init__()
        self.mode = mode  # "claim" | "login"
        self.email = email
        self.phone = phone
        self.secret = secret

    def run(self):
        try:
            if self.mode == "claim":
                action = identity().claim(self.email, self.phone, self.secret)
                self.succeeded.emit(action or "")
            else:
                identity().login(self.email, self.phone, self.secret)
                self.succeeded.emit("login")
        except IdentityError as e:
            self.failed.emit(e.status, str(e))
        except Exception as e:
            self.failed.emit(0, str(e))


class SignInDialog(QDialog):
    """Dialog for claim (anon → claimed) or login (fresh device → existing user)."""

    def __init__(self, parent=None, mode: str = "claim"):
        super().__init__(parent)
        self.mode = mode
        self.setWindowTitle("Sign In or Register" if mode == "claim" else "Sign In")
        self.setModal(True)
        self.setMinimumWidth(440)

        self._worker: Optional[_SignInWorker] = None
        self._result_action: str = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)

        title = QLabel(
            "Register or sign in" if mode == "claim" else "Sign in to your account"
        )
        title.setStyleSheet("font-size: 17px; color: #1e293b;")
        layout.addWidget(title)

        hint = QLabel(
            "Enter your email or phone, plus a 6-digit PIN. If the identifier is "
            "already registered, your existing account will be linked. Otherwise a "
            "new account is created and your current device data stays with it."
            if mode == "claim"
            else
            "Sign in to attach this device to your existing account."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #64748b; font-size: 12px;")
        layout.addWidget(hint)

        # Email/phone toggle
        toggle = QHBoxLayout()
        toggle.setSpacing(0)
        self.btn_email = QPushButton("Email")
        self.btn_phone = QPushButton("Phone")
        for b in (self.btn_email, self.btn_phone):
            b.setCursor(Qt.PointingHandCursor)
            b.setCheckable(True)
            b.setFixedHeight(32)
        self.btn_email.setChecked(True)
        self._apply_toggle_style()
        self.btn_email.clicked.connect(lambda: self._set_identifier_mode("email"))
        self.btn_phone.clicked.connect(lambda: self._set_identifier_mode("phone"))
        toggle.addWidget(self.btn_email)
        toggle.addWidget(self.btn_phone)
        toggle.addStretch()
        layout.addLayout(toggle)

        # Identifier field (stacked: email vs phone)
        self.id_stack = QStackedWidget()
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("you@example.com")
        self._style_input(self.email_input)
        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("+8801XXXXXXXXX")
        self._style_input(self.phone_input)
        self.id_stack.addWidget(self.email_input)
        self.id_stack.addWidget(self.phone_input)
        layout.addWidget(self.id_stack)

        # Secret field
        secret_label = QLabel("PIN (4–8 digits) or password")
        secret_label.setStyleSheet("color: #475569; font-size: 12px;")
        layout.addWidget(secret_label)
        self.secret_input = QLineEdit()
        self.secret_input.setEchoMode(QLineEdit.Password)
        self.secret_input.setPlaceholderText("••••••")
        self._style_input(self.secret_input)
        self.secret_input.returnPressed.connect(self._submit)
        layout.addWidget(self.secret_input)

        # Status / error
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #ef4444; font-size: 12px;")
        layout.addWidget(self.status_label)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.setFixedHeight(32)
        self.cancel_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #475569;"
            " border: 1px solid #e2e8f0; border-radius: 6px; padding: 0 16px; font-size: 12px; }"
            "QPushButton:hover { background: #f1f5f9; }"
        )
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.cancel_btn)

        self.submit_btn = QPushButton("Continue")
        self.submit_btn.setCursor(Qt.PointingHandCursor)
        self.submit_btn.setFixedHeight(32)
        self.submit_btn.setStyleSheet(
            "QPushButton { background: #3b82f6; color: white; border: none;"
            " border-radius: 6px; padding: 0 18px; font-size: 12px; }"
            "QPushButton:hover { background: #2563eb; }"
            "QPushButton:disabled { background: #cbd5e1; }"
        )
        self.submit_btn.clicked.connect(self._submit)
        btn_row.addWidget(self.submit_btn)
        layout.addLayout(btn_row)

        self.email_input.setFocus()

    # ── Helpers ────────────────────────────────────────────────────

    def _style_input(self, w: QLineEdit):
        w.setMinimumHeight(34)
        w.setStyleSheet(
            "QLineEdit { padding: 6px 10px; border: 1px solid #e2e8f0;"
            " border-radius: 6px; font-size: 13px; background: #f8fafc; }"
            "QLineEdit:focus { border-color: #3b82f6; background: white; }"
        )

    def _apply_toggle_style(self):
        on, off = (
            "QPushButton { background: #eff6ff; color: #2563eb; border: 1px solid #93c5fd;"
            " border-radius: 6px; padding: 0 14px; font-size: 12px; font-weight: 600; }",
            "QPushButton { background: transparent; color: #475569; border: 1px solid #e2e8f0;"
            " border-radius: 6px; padding: 0 14px; font-size: 12px; }",
        )
        self.btn_email.setStyleSheet(on if self.btn_email.isChecked() else off)
        self.btn_phone.setStyleSheet(on if self.btn_phone.isChecked() else off)

    def _set_identifier_mode(self, mode: str):
        self.btn_email.setChecked(mode == "email")
        self.btn_phone.setChecked(mode == "phone")
        self.id_stack.setCurrentIndex(0 if mode == "email" else 1)
        self._apply_toggle_style()
        (self.email_input if mode == "email" else self.phone_input).setFocus()

    # ── Submission ─────────────────────────────────────────────────

    def _submit(self):
        if self._worker and self._worker.isRunning():
            return

        email = phone = None
        if self.btn_email.isChecked():
            email = self.email_input.text().strip()
            if not email:
                self.status_label.setText("Please enter an email.")
                return
        else:
            phone = self.phone_input.text().strip()
            if not phone:
                self.status_label.setText("Please enter a phone number.")
                return

        secret = self.secret_input.text()
        if len(secret) < 4:
            self.status_label.setText("Secret must be at least 4 characters.")
            return

        self.status_label.setStyleSheet("color: #64748b; font-size: 12px;")
        self.status_label.setText("Working…")
        self.submit_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)

        self._worker = _SignInWorker(self.mode, email, phone, secret)
        self._worker.succeeded.connect(self._on_success)
        self._worker.failed.connect(self._on_failure)
        self._worker.start()

    def _on_success(self, action: str):
        self._result_action = action
        self.accept()

    def _on_failure(self, status: int, message: str):
        self.submit_btn.setEnabled(True)
        self.cancel_btn.setEnabled(True)
        self.status_label.setStyleSheet("color: #ef4444; font-size: 12px;")
        # Friendlier copy for common cases
        if status == 401:
            message = "Invalid PIN/password for that identifier."
        elif status == 429:
            # Lockout message
            pass  # message already informative
        self.status_label.setText(message or "Sign-in failed. Please try again.")

    def get_action(self) -> str:
        return self._result_action
