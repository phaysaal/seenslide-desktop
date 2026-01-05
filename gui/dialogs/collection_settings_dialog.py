"""Dialog for collection settings (alias, password, sharing)."""

import logging
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QCheckBox, QMessageBox, QGroupBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QApplication
import bcrypt

from core.session.collection_registry import Collection

logger = logging.getLogger(__name__)


class CollectionSettingsDialog(QDialog):
    """Dialog for managing collection settings."""

    def __init__(self, collection: Collection, parent=None):
        """Initialize collection settings dialog.

        Args:
            collection: Collection to manage
            parent: Parent widget
        """
        super().__init__(parent)

        self.collection = collection

        self._setup_ui()

    def _setup_ui(self):
        """Setup the UI components."""
        self.setWindowTitle(f"Settings - {self.collection.name}")
        self.setMinimumWidth(550)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(30, 30, 30, 30)

        # Title
        title_label = QLabel(f"Collection Settings", self)
        title_label.setFont(QFont("Arial", 16, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        # Collection info
        info_group = QGroupBox("Collection Information", self)
        info_layout = QVBoxLayout()

        info_text = f"Name: {self.collection.name}\n"
        info_text += f"Cloud ID: {self.collection.cloud_collection_id}\n"
        info_text += f"Owner: {self.collection.owner_username}\n"
        info_text += f"Status: {'Owner' if self.collection.is_owner else 'Contributor'}"

        info_label = QLabel(info_text, self)
        info_label.setStyleSheet("padding: 10px; background-color: #f5f5f5; border-radius: 5px;")
        info_layout.addWidget(info_label)

        info_group.setLayout(info_layout)
        layout.addWidget(info_group)

        # Sharing settings (only for owners)
        if self.collection.is_owner:
            sharing_group = QGroupBox("Sharing Settings", self)
            sharing_layout = QVBoxLayout()

            # Alias
            alias_layout = QVBoxLayout()
            alias_label = QLabel("Collection Alias (for easier sharing):", self)
            alias_label.setStyleSheet("font-weight: bold;")
            alias_layout.addWidget(alias_label)

            self.alias_input = QLineEdit(self)
            self.alias_input.setText(self.collection.alias or "")
            self.alias_input.setPlaceholderText("e.g., ml-conference-2026")
            alias_layout.addWidget(self.alias_input)

            alias_help = QLabel(
                "An alias makes it easier to share your collection (instead of the random ID).",
                self
            )
            alias_help.setStyleSheet("color: #666; font-size: 11px;")
            alias_help.setWordWrap(True)
            alias_layout.addWidget(alias_help)

            sharing_layout.addLayout(alias_layout)

            # Password
            self.password_checkbox = QCheckBox(
                "Set/Change password for multi-device access and sharing",
                self
            )
            self.password_checkbox.setChecked(self.collection.has_password)
            self.password_checkbox.toggled.connect(self._on_password_checkbox_toggled)
            sharing_layout.addWidget(self.password_checkbox)

            # Password inputs (hidden by default)
            self.password_widget = QWidget(self)
            password_layout = QVBoxLayout(self.password_widget)
            password_layout.setContentsMargins(20, 0, 0, 0)

            password_label = QLabel("New Password:", self)
            password_label.setStyleSheet("font-weight: bold;")
            password_layout.addWidget(password_label)

            self.password_input = QLineEdit(self)
            self.password_input.setEchoMode(QLineEdit.Password)
            self.password_input.setPlaceholderText("Enter new password")
            password_layout.addWidget(self.password_input)

            password_confirm_label = QLabel("Confirm Password:", self)
            password_confirm_label.setStyleSheet("font-weight: bold;")
            password_layout.addWidget(password_confirm_label)

            self.password_confirm_input = QLineEdit(self)
            self.password_confirm_input.setEchoMode(QLineEdit.Password)
            self.password_confirm_input.setPlaceholderText("Confirm password")
            password_layout.addWidget(self.password_confirm_input)

            self.password_widget.setVisible(False)
            sharing_layout.addWidget(self.password_widget)

            sharing_group.setLayout(sharing_layout)
            layout.addWidget(sharing_group)

            # Sharing info
            sharing_info_group = QGroupBox("Share Collection", self)
            sharing_info_layout = QVBoxLayout()

            share_text = "Share this information with others to let them join:\n\n"
            share_id = self.collection.alias if self.collection.alias else self.collection.cloud_collection_id
            share_text += f"Collection ID/Alias: {share_id}\n"

            if self.collection.has_password:
                share_text += "Password: (the password you set)\n"
            else:
                share_text += "Password: (No password set - set one above for sharing)\n"

            share_label = QLabel(share_text, self)
            share_label.setStyleSheet("""
                padding: 15px;
                background-color: #e3f2fd;
                border-radius: 5px;
                color: #1565C0;
                font-family: monospace;
            """)
            share_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            sharing_info_layout.addWidget(share_label)

            # Copy button
            copy_button = QPushButton("Copy Collection ID to Clipboard", self)
            copy_button.clicked.connect(lambda: self._copy_to_clipboard(share_id))
            sharing_info_layout.addWidget(copy_button)

            sharing_info_group.setLayout(sharing_info_layout)
            layout.addWidget(sharing_info_group)
        else:
            # Not owner - show read-only message
            readonly_label = QLabel(
                "ℹ️  You are a contributor to this collection.\n"
                "Only the owner can change sharing settings.",
                self
            )
            readonly_label.setStyleSheet("""
                padding: 15px;
                background-color: #fff3cd;
                border-radius: 5px;
                color: #856404;
            """)
            readonly_label.setWordWrap(True)
            layout.addWidget(readonly_label)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_button = QPushButton("Cancel", self)
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)

        if self.collection.is_owner:
            self.save_button = QPushButton("Save Changes", self)
            self.save_button.setStyleSheet("""
                QPushButton {
                    background-color: #4CAF50;
                    color: white;
                    border: none;
                    padding: 10px 30px;
                    font-size: 14px;
                    font-weight: bold;
                    border-radius: 5px;
                    min-width: 120px;
                }
                QPushButton:hover {
                    background-color: #45a049;
                }
            """)
            self.save_button.clicked.connect(self._on_save_clicked)
            button_layout.addWidget(self.save_button)
        else:
            close_button = QPushButton("Close", self)
            close_button.clicked.connect(self.reject)
            button_layout.addWidget(close_button)

        layout.addLayout(button_layout)

    def _on_password_checkbox_toggled(self, checked: bool):
        """Handle password checkbox toggle.

        Args:
            checked: Whether checkbox is checked
        """
        self.password_widget.setVisible(checked)

    def _copy_to_clipboard(self, text: str):
        """Copy text to clipboard.

        Args:
            text: Text to copy
        """
        clipboard = QApplication.clipboard()
        clipboard.setText(text)

        QMessageBox.information(
            self,
            "Copied",
            f"'{text}' copied to clipboard!"
        )

    def _on_save_clicked(self):
        """Handle save button click."""
        # Validate alias
        alias = self.alias_input.text().strip()

        if alias:
            # Basic validation for alias
            if not alias.replace('-', '').replace('_', '').isalnum():
                QMessageBox.warning(
                    self,
                    "Invalid Alias",
                    "Alias can only contain letters, numbers, hyphens, and underscores."
                )
                self.alias_input.setFocus()
                return

        # Validate password if checkbox is checked
        password_hash = None
        if self.password_checkbox.isChecked():
            password = self.password_input.text()
            password_confirm = self.password_confirm_input.text()

            if password or password_confirm:  # Only validate if user entered something
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

        # Update collection via cloud API
        try:
            # Load config to get cloud settings
            from pathlib import Path
            import yaml

            config_paths = [
                Path.home() / ".config" / "seenslide" / "config.yaml",
                Path(__file__).parent.parent.parent / "config" / "config.yaml",
            ]

            config = {}
            for path in config_paths:
                if path.exists():
                    with open(path, 'r') as f:
                        config = yaml.safe_load(f)
                    break

            # Initialize cloud provider
            from modules.storage.providers.cloud_provider import CloudStorageProvider
            from core.session.collection_registry import CollectionRegistry
            from core.session.credential_manager import CredentialManager

            cloud = CloudStorageProvider()
            cloud.initialize(config.get('cloud', {}))

            # Update alias if changed
            if alias != self.collection.alias:
                logger.info(f"Updating alias: {self.collection.alias} → {alias}")
                success = cloud.update_collection_alias(
                    self.collection.cloud_collection_id,
                    alias if alias else None
                )

                if success:
                    # Update local registry
                    registry = CollectionRegistry()
                    registry.update_collection(
                        self.collection.collection_id,
                        alias=alias if alias else None
                    )
                    logger.info("✅ Alias updated locally")
                else:
                    QMessageBox.warning(
                        self,
                        "Partial Success",
                        "Failed to update alias in cloud. Local changes saved."
                    )

            # Update password if provided
            if password_hash:
                logger.info("Updating collection password")
                success = cloud.update_collection_password(
                    self.collection.cloud_collection_id,
                    self.collection.owner_username,
                    password_hash
                )

                if success:
                    # Update local registry
                    registry = CollectionRegistry()
                    registry.update_collection(
                        self.collection.collection_id,
                        has_password=True
                    )

                    # Store password hash locally
                    cred_manager = CredentialManager()
                    cred_manager.store_password_hash(
                        self.collection.cloud_collection_id,
                        password_hash
                    )

                    logger.info("✅ Password updated locally")
                else:
                    QMessageBox.warning(
                        self,
                        "Partial Success",
                        "Failed to update password in cloud. Local changes saved."
                    )

            QMessageBox.information(
                self,
                "Settings Updated",
                "Collection settings updated successfully!\n\n"
                f"Alias: {alias or '(none)'}\n"
                f"Password: {'Updated' if password_hash else 'Not changed'}"
            )

            # Accept dialog
            self.accept()

        except Exception as e:
            logger.error(f"Error updating collection settings: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Error",
                f"An error occurred while updating settings:\n{str(e)}"
            )
