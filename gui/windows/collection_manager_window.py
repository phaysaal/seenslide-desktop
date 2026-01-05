"""Collection Manager window for managing collections."""

import logging
from typing import Optional
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QMessageBox, QDialog
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont

from core.session.collection_registry import CollectionRegistry, Collection
from core.session.credential_manager import CredentialManager
from gui.dialogs.create_collection_dialog import CreateCollectionDialog
from gui.dialogs.join_collection_dialog import JoinCollectionDialog
from gui.dialogs.collection_settings_dialog import CollectionSettingsDialog

logger = logging.getLogger(__name__)


class CollectionManagerWindow(QWidget):
    """Window for managing collections."""

    # Signal emitted when collection is switched
    collection_switched = pyqtSignal(Collection)

    # Signal emitted when window should close
    close_requested = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        """Initialize collection manager window.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)

        # Collection management
        self.collection_registry = CollectionRegistry()
        self.credential_manager = CredentialManager()

        # Setup UI
        self._setup_ui()

        # Load collections
        self._load_collections()

        logger.info("CollectionManagerWindow initialized")

    def _setup_ui(self):
        """Setup the UI components."""
        self.setWindowTitle("SeenSlide - Collection Manager")
        self.setMinimumSize(600, 500)

        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # Title
        title = QLabel("Collection Manager", self)
        title.setFont(QFont("Arial", 20, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Description
        desc = QLabel(
            "Manage your talk collections. Each collection groups related talks together.",
            self
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #666; font-size: 13px;")
        desc.setAlignment(Qt.AlignCenter)
        layout.addWidget(desc)

        # Collection list
        list_label = QLabel("Your Collections:", self)
        list_label.setFont(QFont("Arial", 14, QFont.Bold))
        layout.addWidget(list_label)

        self.collection_list = QListWidget(self)
        self.collection_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #ddd;
                border-radius: 5px;
                padding: 5px;
            }
            QListWidget::item {
                padding: 10px;
                border-bottom: 1px solid #eee;
            }
            QListWidget::item:selected {
                background-color: #e3f2fd;
                color: #1565C0;
            }
            QListWidget::item:hover {
                background-color: #f5f5f5;
            }
        """)
        self.collection_list.itemDoubleClicked.connect(self._on_collection_double_clicked)
        layout.addWidget(self.collection_list)

        # Action buttons
        button_layout = QHBoxLayout()

        self.create_button = QPushButton("Create New Collection", self)
        self.create_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 10px 20px;
                font-size: 13px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        self.create_button.clicked.connect(self._on_create_clicked)
        button_layout.addWidget(self.create_button)

        self.join_button = QPushButton("Join Existing Collection", self)
        self.join_button.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                padding: 10px 20px;
                font-size: 13px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #0b7dda;
            }
        """)
        self.join_button.clicked.connect(self._on_join_clicked)
        button_layout.addWidget(self.join_button)

        layout.addLayout(button_layout)

        # Collection actions
        action_layout = QHBoxLayout()

        self.switch_button = QPushButton("Switch to Collection", self)
        self.switch_button.setEnabled(False)
        self.switch_button.clicked.connect(self._on_switch_clicked)
        action_layout.addWidget(self.switch_button)

        self.settings_button = QPushButton("Collection Settings", self)
        self.settings_button.setEnabled(False)
        self.settings_button.clicked.connect(self._on_settings_clicked)
        action_layout.addWidget(self.settings_button)

        self.delete_button = QPushButton("Delete Collection", self)
        self.delete_button.setEnabled(False)
        self.delete_button.setStyleSheet("color: #f44336;")
        self.delete_button.clicked.connect(self._on_delete_clicked)
        action_layout.addWidget(self.delete_button)

        layout.addLayout(action_layout)

        # Close button
        close_layout = QHBoxLayout()
        close_layout.addStretch()

        close_button = QPushButton("Close", self)
        close_button.clicked.connect(self.close)
        close_layout.addWidget(close_button)

        layout.addLayout(close_layout)

        # Connect selection change
        self.collection_list.itemSelectionChanged.connect(self._on_selection_changed)

    def _load_collections(self):
        """Load collections into list."""
        self.collection_list.clear()

        collections = self.collection_registry.list_collections()
        current = self.collection_registry.get_current_collection()

        if not collections:
            item = QListWidgetItem("No collections yet. Create or join one to get started!")
            item.setFlags(Qt.NoItemFlags)
            item.setForeground(Qt.gray)
            self.collection_list.addItem(item)
            return

        for collection in collections:
            # Create display text
            text = f"{collection.name}\n"
            text += f"   ID: {collection.cloud_collection_id}"

            if collection.alias:
                text += f"  •  Alias: {collection.alias}"

            if collection.is_owner:
                text += "  •  👤 Owner"
            else:
                text += f"  •  👥 Contributor"

            if current and collection.collection_id == current.collection_id:
                text += "  •  ✅ CURRENT"

            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, collection)
            self.collection_list.addItem(item)

        logger.info(f"Loaded {len(collections)} collections")

    def _on_selection_changed(self):
        """Handle selection change."""
        selected = self.collection_list.currentItem()

        if selected and selected.data(Qt.UserRole):
            self.switch_button.setEnabled(True)
            self.settings_button.setEnabled(True)

            # Only allow delete if owner
            collection = selected.data(Qt.UserRole)
            self.delete_button.setEnabled(collection.is_owner)
        else:
            self.switch_button.setEnabled(False)
            self.settings_button.setEnabled(False)
            self.delete_button.setEnabled(False)

    def _on_collection_double_clicked(self, item: QListWidgetItem):
        """Handle double click on collection.

        Args:
            item: Clicked item
        """
        collection = item.data(Qt.UserRole)
        if collection:
            self._switch_to_collection(collection)

    def _on_create_clicked(self):
        """Handle create new collection button click."""
        dialog = CreateCollectionDialog(self)

        if dialog.exec_() == QDialog.Accepted:
            collection_info = dialog.get_collection_info()

            logger.info(f"Creating new collection: {collection_info['name']}")

            # TODO: Create cloud collection via API
            # For now, show message
            QMessageBox.information(
                self,
                "Coming Soon",
                "Creating new collections from Collection Manager will be available soon.\n\n"
                "You can create a new collection by resetting and restarting the app."
            )

            # Reload list
            self._load_collections()

    def _on_join_clicked(self):
        """Handle join existing collection button click."""
        dialog = JoinCollectionDialog(self)

        if dialog.exec_() == QDialog.Accepted:
            join_info = dialog.get_join_info()

            logger.info(f"Joining collection: {join_info['collection_id']}")

            # Show progress
            progress = QMessageBox(self)
            progress.setWindowTitle("Joining Collection")
            progress.setText("Verifying collection password...")
            progress.setStandardButtons(QMessageBox.NoButton)
            progress.show()
            QApplication.processEvents()

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
                cloud = CloudStorageProvider()
                cloud.initialize(config.get('cloud', {}))

                # Verify collection password
                result = cloud.verify_collection_password(
                    join_info['collection_id'],
                    join_info['password']
                )

                progress.close()

                if result:
                    # Successfully verified - add to registry
                    collection = self.collection_registry.add_collection(
                        cloud_collection_id=result['collection_id'],
                        name=result.get('name', 'Unknown Collection'),
                        owner_username=result['owner_username'],
                        is_owner=False,  # Joining as contributor
                        access_level="contributor",
                        has_password=True
                    )

                    # Store session token
                    if result.get('session_token'):
                        self.credential_manager.store_session_token(
                            result['collection_id'],
                            result['session_token']
                        )

                    logger.info(f"✅ Successfully joined collection: {result['collection_id']}")

                    QMessageBox.information(
                        self,
                        "Collection Joined",
                        f"Successfully joined collection: {result.get('name', 'Unknown')}\n\n"
                        f"You can now add talks to this collection."
                    )

                    # Reload list
                    self._load_collections()
                else:
                    QMessageBox.critical(
                        self,
                        "Join Failed",
                        "Failed to join collection. Please check:\n\n"
                        "• Collection ID/alias is correct\n"
                        "• Password is correct\n"
                        "• Collection exists and is accessible"
                    )

            except Exception as e:
                progress.close()
                logger.error(f"Error joining collection: {e}", exc_info=True)
                QMessageBox.critical(
                    self,
                    "Error",
                    f"An error occurred while joining the collection:\n{str(e)}"
                )

    def _on_switch_clicked(self):
        """Handle switch to collection button click."""
        selected = self.collection_list.currentItem()

        if not selected:
            return

        collection = selected.data(Qt.UserRole)
        if collection:
            self._switch_to_collection(collection)

    def _switch_to_collection(self, collection: Collection):
        """Switch to a collection.

        Args:
            collection: Collection to switch to
        """
        current = self.collection_registry.get_current_collection()

        if current and current.collection_id == collection.collection_id:
            QMessageBox.information(
                self,
                "Already Current",
                f"'{collection.name}' is already the current collection."
            )
            return

        # Switch collection
        success = self.collection_registry.set_current_collection(collection.collection_id)

        if success:
            logger.info(f"Switched to collection: {collection.name}")

            QMessageBox.information(
                self,
                "Collection Switched",
                f"Switched to collection: {collection.name}\n\n"
                f"New talks will be added to this collection.\n\n"
                "Please restart the app for the change to take effect."
            )

            # Reload list to update current marker
            self._load_collections()

            # Emit signal
            self.collection_switched.emit(collection)
        else:
            QMessageBox.critical(
                self,
                "Switch Failed",
                "Failed to switch collection. Please try again."
            )

    def _on_settings_clicked(self):
        """Handle collection settings button click."""
        selected = self.collection_list.currentItem()

        if not selected:
            return

        collection = selected.data(Qt.UserRole)
        if collection:
            dialog = CollectionSettingsDialog(collection, self)

            if dialog.exec_() == QDialog.Accepted:
                # Reload list to show updates
                self._load_collections()

    def _on_delete_clicked(self):
        """Handle delete collection button click."""
        selected = self.collection_list.currentItem()

        if not selected:
            return

        collection = selected.data(Qt.UserRole)
        if not collection:
            return

        # Confirm deletion
        reply = QMessageBox.question(
            self,
            "Delete Collection",
            f"Are you sure you want to delete '{collection.name}'?\n\n"
            f"This will remove the collection from this device only.\n"
            f"The cloud collection and talks will remain accessible.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            # Remove from registry
            success = self.collection_registry.remove_collection(collection.collection_id)

            if success:
                # Delete credentials
                self.credential_manager.delete_credentials(collection.cloud_collection_id)

                logger.info(f"Deleted collection: {collection.name}")

                QMessageBox.information(
                    self,
                    "Collection Deleted",
                    f"Collection '{collection.name}' has been removed from this device."
                )

                # Reload list
                self._load_collections()
            else:
                QMessageBox.critical(
                    self,
                    "Delete Failed",
                    "Failed to delete collection. Please try again."
                )
