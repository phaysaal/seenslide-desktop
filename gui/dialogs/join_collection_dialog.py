"""Dialog for joining an existing collection."""

import logging
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QMessageBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

logger = logging.getLogger(__name__)


class JoinCollectionDialog(QDialog):
    """Dialog for joining an existing collection."""

    def __init__(self, parent=None):
        """Initialize join collection dialog.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)

        self.join_info = None

        self._setup_ui()

    def _setup_ui(self):
        """Setup the UI components."""
        self.setWindowTitle("Join Existing Collection")
        self.setMinimumWidth(500)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(30, 30, 30, 30)

        # Title
        title_label = QLabel("Join Existing Collection", self)
        title_label.setFont(QFont("Arial", 16, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        # Description
        desc_label = QLabel(
            "Enter the collection ID or alias and password to join a collection\n"
            "that's shared with you or from another device.",
            self
        )
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #666; font-size: 12px;")
        desc_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(desc_label)

        # Collection ID/Alias
        id_layout = QVBoxLayout()
        id_label = QLabel("Collection ID or Alias:", self)
        id_label.setStyleSheet("font-weight: bold;")
        id_layout.addWidget(id_label)

        self.id_input = QLineEdit(self)
        self.id_input.setPlaceholderText("e.g., AUA-6538 or my-conference-2026")
        id_layout.addWidget(self.id_input)

        id_help = QLabel(
            "The collection owner will provide this ID or alias.",
            self
        )
        id_help.setStyleSheet("color: #666; font-size: 11px;")
        id_layout.addWidget(id_help)

        layout.addLayout(id_layout)

        # Password
        password_layout = QVBoxLayout()
        password_label = QLabel("Password:", self)
        password_label.setStyleSheet("font-weight: bold;")
        password_layout.addWidget(password_label)

        self.password_input = QLineEdit(self)
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("Enter collection password")
        password_layout.addWidget(self.password_input)

        password_help = QLabel(
            "The password was set by the collection owner for sharing.",
            self
        )
        password_help.setStyleSheet("color: #666; font-size: 11px;")
        password_layout.addWidget(password_help)

        layout.addLayout(password_layout)

        # Info box
        info_box = QLabel(
            "ℹ️  After joining, you'll be able to add talks to this collection.",
            self
        )
        info_box.setStyleSheet("""
            QLabel {
                background-color: #e3f2fd;
                padding: 10px;
                border-radius: 5px;
                color: #1565C0;
                font-size: 12px;
            }
        """)
        info_box.setWordWrap(True)
        layout.addWidget(info_box)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_button = QPushButton("Cancel", self)
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)

        self.join_button = QPushButton("Join", self)
        self.join_button.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                padding: 10px 30px;
                font-size: 14px;
                font-weight: bold;
                border-radius: 5px;
                min-width: 100px;
            }
            QPushButton:hover {
                background-color: #0b7dda;
            }
        """)
        self.join_button.clicked.connect(self._on_join_clicked)
        button_layout.addWidget(self.join_button)

        layout.addLayout(button_layout)

    def _on_join_clicked(self):
        """Handle join button click."""
        # Validate inputs
        collection_id = self.id_input.text().strip()
        password = self.password_input.text()

        if not collection_id:
            QMessageBox.warning(
                self,
                "Missing Information",
                "Please enter a collection ID or alias."
            )
            self.id_input.setFocus()
            return

        if not password:
            QMessageBox.warning(
                self,
                "Missing Password",
                "Please enter the collection password."
            )
            self.password_input.setFocus()
            return

        # Store results
        self.join_info = {
            'collection_id': collection_id,
            'password': password
        }

        # Accept dialog
        self.accept()

    def get_join_info(self):
        """Get the join information entered by user.

        Returns:
            Dictionary with join info
        """
        return self.join_info
