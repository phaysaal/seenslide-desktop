"""Edit account identifiers dialog.

Used when a claimed user wants to change email, change phone, or change
their secret. Requires the current secret as confirmation.
"""

from typing import Optional

from PyQt5.QtCore import Qt, pyqtSignal, QThread
from PyQt5.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from core.identity import identity, IdentityError


class _EditWorker(QThread):
    succeeded = pyqtSignal()
    failed = pyqtSignal(int, str)

    def __init__(self, current_secret, new_email, new_phone, new_secret):
        super().__init__()
        self.current_secret = current_secret
        self.new_email = new_email
        self.new_phone = new_phone
        self.new_secret = new_secret

    def run(self):
        try:
            identity().update_identifiers(
                current_secret=self.current_secret,
                new_email=self.new_email,
                new_phone=self.new_phone,
                new_secret=self.new_secret,
            )
            self.succeeded.emit()
        except IdentityError as e:
            self.failed.emit(e.status, str(e))
        except Exception as e:
            self.failed.emit(0, str(e))


class EditAccountDialog(QDialog):
    """Edit any subset of {email, phone, secret} for the authenticated user."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Account")
        self.setModal(True)
        self.setMinimumWidth(440)

        self._worker: Optional[_EditWorker] = None
        rec = identity().record

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(10)

        title = QLabel("Edit account")
        title.setStyleSheet("font-size: 17px; color: #1e293b;")
        layout.addWidget(title)

        hint = QLabel(
            "Leave a field blank to keep its current value. The current PIN/password "
            "is required to confirm any change."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #64748b; font-size: 12px;")
        layout.addWidget(hint)

        layout.addSpacing(4)

        layout.addWidget(self._field_label("Email"))
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText(rec.email or "you@example.com")
        if rec.email:
            self.email_input.setText(rec.email)
        self._style_input(self.email_input)
        layout.addWidget(self.email_input)

        layout.addWidget(self._field_label("Phone"))
        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText(rec.phone_number or "+8801XXXXXXXXX")
        if rec.phone_number:
            self.phone_input.setText(rec.phone_number)
        self._style_input(self.phone_input)
        layout.addWidget(self.phone_input)

        layout.addWidget(self._field_label("New PIN/password (optional)"))
        self.new_secret_input = QLineEdit()
        self.new_secret_input.setEchoMode(QLineEdit.Password)
        self.new_secret_input.setPlaceholderText("Leave blank to keep")
        self._style_input(self.new_secret_input)
        layout.addWidget(self.new_secret_input)

        layout.addSpacing(4)

        layout.addWidget(self._field_label("Current PIN/password (required)"))
        self.current_secret_input = QLineEdit()
        self.current_secret_input.setEchoMode(QLineEdit.Password)
        self.current_secret_input.setPlaceholderText("••••••")
        self._style_input(self.current_secret_input)
        self.current_secret_input.returnPressed.connect(self._submit)
        layout.addWidget(self.current_secret_input)

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

        self.submit_btn = QPushButton("Save")
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

    def _style_input(self, w: QLineEdit):
        w.setMinimumHeight(34)
        w.setStyleSheet(
            "QLineEdit { padding: 6px 10px; border: 1px solid #e2e8f0;"
            " border-radius: 6px; font-size: 13px; background: #f8fafc; }"
            "QLineEdit:focus { border-color: #3b82f6; background: white; }"
        )

    def _field_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #475569; font-size: 12px;")
        return lbl

    def _submit(self):
        if self._worker and self._worker.isRunning():
            return

        rec = identity().record
        new_email = self.email_input.text().strip() or None
        new_phone = self.phone_input.text().strip() or None
        new_secret = self.new_secret_input.text() or None
        current = self.current_secret_input.text()

        # Only send fields the user actually changed.
        email_arg = new_email if new_email != (rec.email or None) else None
        phone_arg = new_phone if new_phone != (rec.phone_number or None) else None
        secret_arg = new_secret if new_secret else None

        if email_arg is None and phone_arg is None and secret_arg is None:
            self.status_label.setText("Nothing to update.")
            return
        if not current:
            self.status_label.setText("Current PIN/password is required.")
            return

        self.status_label.setStyleSheet("color: #64748b; font-size: 12px;")
        self.status_label.setText("Saving…")
        self.submit_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)

        self._worker = _EditWorker(current, email_arg, phone_arg, secret_arg)
        self._worker.succeeded.connect(self.accept)
        self._worker.failed.connect(self._on_failure)
        self._worker.start()

    def _on_failure(self, status: int, message: str):
        self.submit_btn.setEnabled(True)
        self.cancel_btn.setEnabled(True)
        self.status_label.setStyleSheet("color: #ef4444; font-size: 12px;")
        if status == 401:
            message = "Current PIN/password is incorrect."
        self.status_label.setText(message or "Update failed.")
