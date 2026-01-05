"""Dialog for creating a new collection."""

import logging
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QCheckBox, QMessageBox, QWidget
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
import bcrypt

logger = logging.getLogger(__name__)


class CreateCollectionDialog(QDialog):
    """Dialog for creating a new collection."""

    def __init__(self, parent=None):
        """Initialize create collection dialog.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)

        self.collection_info = None

        self._setup_ui()

    def _setup_ui(self):
        """Setup the UI components."""
        self.setWindowTitle("Create New Collection")
        self.setMinimumWidth(500)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(30, 30, 30, 30)

        # Title
        title_label = QLabel("Create New Collection", self)
        title_label.setFont(QFont("Arial", 16, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        # Collection name
        name_layout = QVBoxLayout()
        name_label = QLabel("Collection Name:", self)
        name_label.setStyleSheet("font-weight: bold;")
        name_layout.addWidget(name_label)

        self.name_input = QLineEdit(self)
        self.name_input.setPlaceholderText("e.g., Conference 2026")
        name_layout.addWidget(self.name_input)
        layout.addLayout(name_layout)

        # Password checkbox
        self.password_checkbox = QCheckBox(
            "Set a password (for sharing with others or multi-device access)",
            self
        )
        self.password_checkbox.toggled.connect(self._on_password_checkbox_toggled)
        layout.addWidget(self.password_checkbox)

        # Password input (hidden by default)
        self.password_widget = QWidget(self)
        password_layout = QVBoxLayout(self.password_widget)
        password_layout.setContentsMargins(20, 0, 0, 0)

        password_label = QLabel("Password:", self)
        password_label.setStyleSheet("font-weight: bold;")
        password_layout.addWidget(password_label)

        self.password_input = QLineEdit(self)
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("Enter a password")
        password_layout.addWidget(self.password_input)

        password_confirm_label = QLabel("Confirm Password:", self)
        password_confirm_label.setStyleSheet("font-weight: bold;")
        password_layout.addWidget(password_confirm_label)

        self.password_confirm_input = QLineEdit(self)
        self.password_confirm_input.setEchoMode(QLineEdit.Password)
        self.password_confirm_input.setPlaceholderText("Confirm password")
        password_layout.addWidget(self.password_confirm_input)

        self.password_widget.setVisible(False)
        layout.addWidget(self.password_widget)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_button = QPushButton("Cancel", self)
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)

        self.create_button = QPushButton("Create", self)
        self.create_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 10px 30px;
                font-size: 14px;
                font-weight: bold;
                border-radius: 5px;
                min-width: 100px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        self.create_button.clicked.connect(self._on_create_clicked)
        button_layout.addWidget(self.create_button)

        layout.addLayout(button_layout)

    def _on_password_checkbox_toggled(self, checked: bool):
        """Handle password checkbox toggle.

        Args:
            checked: Whether checkbox is checked
        """
        self.password_widget.setVisible(checked)

    def _on_create_clicked(self):
        """Handle create button click."""
        # Validate inputs
        collection_name = self.name_input.text().strip()

        if not collection_name:
            QMessageBox.warning(
                self,
                "Missing Information",
                "Please enter a collection name."
            )
            self.name_input.setFocus()
            return

        # Validate password if enabled
        password_hash = None
        if self.password_checkbox.isChecked():
            password = self.password_input.text()
            password_confirm = self.password_confirm_input.text()

            if not password:
                QMessageBox.warning(
                    self,
                    "Missing Password",
                    "Please enter a password or uncheck the password option."
                )
                self.password_input.setFocus()
                return

            if password != password_confirm:
                QMessageBox.warning(
                    self,
                    "Password Mismatch",
                    "Passwords do not match. Please try again."
                )
                self.password_confirm_input.clear()
                self.password_confirm_input.setFocus()
                return

            if len(password) < 6:
                QMessageBox.warning(
                    self,
                    "Weak Password",
                    "Password must be at least 6 characters long."
                )
                self.password_input.setFocus()
                return

            # Hash password
            try:
                password_hash = bcrypt.hashpw(
                    password.encode('utf-8'),
                    bcrypt.gensalt()
                ).decode('utf-8')
            except Exception as e:
                logger.error(f"Failed to hash password: {e}")
                QMessageBox.critical(
                    self,
                    "Error",
                    "Failed to process password. Please try again."
                )
                return

        # Store results
        self.collection_info = {
            'name': collection_name,
            'password_hash': password_hash,
            'has_password': self.password_checkbox.isChecked()
        }

        # Accept dialog
        self.accept()

    def get_collection_info(self):
        """Get the collection information entered by user.

        Returns:
            Dictionary with collection info
        """
        return self.collection_info
