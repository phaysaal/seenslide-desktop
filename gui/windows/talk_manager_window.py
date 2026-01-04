"""Talk Manager window - manage past talks and sessions."""

import logging
from typing import Optional, List, Dict
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QLineEdit, QMessageBox, QDialog, QDialogButtonBox
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QPalette, QColor
from pathlib import Path

from gui.utils.server_manager import ServerManager

logger = logging.getLogger(__name__)


class EditTalkDialog(QDialog):
    """Dialog for editing talk details."""

    def __init__(self, talk_title: str, presenter_name: str = "", parent=None):
        """Initialize edit dialog.

        Args:
            talk_title: Current talk title
            presenter_name: Current presenter name
            parent: Parent widget
        """
        super().__init__(parent)

        self.setWindowTitle("Edit Talk")
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # Title field
        title_label = QLabel("Talk Title:")
        title_label.setStyleSheet("color: #ffffff;")
        layout.addWidget(title_label)

        self.title_edit = QLineEdit(talk_title)
        self.title_edit.setStyleSheet("""
            QLineEdit {
                background: #1a1a24;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 6px;
                padding: 8px;
                color: #ffffff;
                font-size: 14px;
            }
            QLineEdit:focus {
                border-color: #00d4ff;
            }
        """)
        layout.addWidget(self.title_edit)

        # Presenter field
        presenter_label = QLabel("Presenter Name:")
        presenter_label.setStyleSheet("color: #ffffff;")
        layout.addWidget(presenter_label)

        self.presenter_edit = QLineEdit(presenter_name or "")
        self.presenter_edit.setStyleSheet("""
            QLineEdit {
                background: #1a1a24;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 6px;
                padding: 8px;
                color: #ffffff;
                font-size: 14px;
            }
            QLineEdit:focus {
                border-color: #00d4ff;
            }
        """)
        layout.addWidget(self.presenter_edit)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.setStyleSheet("""
            QPushButton {
                background: #00d4ff;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #00b8e6;
            }
        """)
        layout.addWidget(buttons)

        # Dark theme
        self.setStyleSheet("background: #12121a; color: #ffffff;")

    def get_values(self) -> tuple:
        """Get edited values.

        Returns:
            Tuple of (title, presenter_name)
        """
        return (self.title_edit.text(), self.presenter_edit.text())


class TalkManagerWindow(QWidget):
    """Window for managing past talks and sessions."""

    # Signal emitted when window should close
    close_requested = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        """Initialize talk manager.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)

        self.server_manager = ServerManager()
        self.sessions_data: List[Dict] = []

        self._setup_ui()
        self._load_talks()

        logger.info("TalkManagerWindow initialized")

    def _setup_ui(self):
        """Setup the UI components."""
        self.setWindowTitle("Manage Past Talks - SeenSlide")
        self.setMinimumSize(700, 600)

        # Dark background
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor("#0a0a0f"))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # Header
        header = self._create_header()
        main_layout.addWidget(header)

        # Content area (scrollable)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background: #12121a;
                width: 10px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background: #2a2a3a;
                border-radius: 5px;
            }
        """)

        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setSpacing(15)
        self.content_layout.setContentsMargins(0, 0, 0, 0)

        scroll.setWidget(self.content_widget)
        main_layout.addWidget(scroll, 1)

        # Footer with close button
        footer = self._create_footer()
        main_layout.addWidget(footer)

    def _create_header(self) -> QWidget:
        """Create header section.

        Returns:
            QWidget containing header
        """
        header = QWidget()
        header.setStyleSheet("background: #12121a; border-radius: 12px; padding: 20px;")
        layout = QVBoxLayout(header)
        layout.setSpacing(8)

        title = QLabel("📋 Manage Past Talks")
        title.setFont(QFont("Arial", 20, QFont.Bold))
        title.setStyleSheet("color: #ffffff;")
        layout.addWidget(title)

        subtitle = QLabel("View, edit, or delete previously recorded talks and sessions")
        subtitle.setFont(QFont("Arial", 12))
        subtitle.setStyleSheet("color: #8b8b9e;")
        layout.addWidget(subtitle)

        return header

    def _create_footer(self) -> QWidget:
        """Create footer with action buttons.

        Returns:
            QWidget containing footer
        """
        footer = QWidget()
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(0, 15, 0, 0)

        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.setFont(QFont("Arial", 11))
        refresh_btn.setCursor(Qt.PointingHandCursor)
        refresh_btn.setStyleSheet("""
            QPushButton {
                background: #2a2a3a;
                color: #ffffff;
                border: none;
                border-radius: 8px;
                padding: 10px 20px;
            }
            QPushButton:hover {
                background: #3a3a4a;
            }
        """)
        refresh_btn.clicked.connect(self._load_talks)
        layout.addWidget(refresh_btn)

        layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.setFont(QFont("Arial", 11))
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background: #00d4ff;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px 30px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #00b8e6;
            }
        """)
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)

        return footer

    def _load_talks(self):
        """Load all sessions and talks from storage."""
        logger.info("Loading talks from storage...")

        # Clear existing content
        while self.content_layout.count():
            child = self.content_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        try:
            # Get storage path
            from pathlib import Path
            storage_path = Path("/tmp/seenslide")
            db_path = storage_path / "db" / "seenslide.db"

            if not db_path.exists():
                self._show_empty_state(
                    "📭 No Talks Yet",
                    "No database found. Start a presentation to record your first talk!"
                )
                return

            # Load sessions from database
            from modules.storage.providers.sqlite_provider import SQLiteStorageProvider

            db_provider = SQLiteStorageProvider()
            db_provider.initialize({"db_path": str(db_path)})

            # Get all sessions (we need to scan the DB)
            # Since there's no get_all_sessions, we'll need to read from SQLite directly
            import sqlite3
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()

            cursor.execute("""
                SELECT DISTINCT session_id, MAX(created_at) as latest_time
                FROM slides
                GROUP BY session_id
                ORDER BY latest_time DESC
            """)

            session_ids = [row[0] for row in cursor.fetchall()]
            conn.close()

            if not session_ids:
                self._show_empty_state(
                    "📭 No Talks Yet",
                    "You haven't recorded any talks yet.\n\n"
                    "Start a presentation from the launcher to see your talks here."
                )
                return

            # Load talks for each session
            session_count = 0
            for session_id in session_ids:
                session_card = self._create_session_card(session_id, db_provider)
                if session_card:
                    self.content_layout.addWidget(session_card)
                    session_count += 1

            if session_count == 0:
                self._show_empty_state(
                    "📭 No Talks Found",
                    "Sessions exist but contain no talks.\n\n"
                    "This might happen if talks were manually deleted from the database."
                )
                return

            self.content_layout.addStretch()

            logger.info(f"Loaded {session_count} sessions")

        except Exception as e:
            logger.error(f"Failed to load talks: {e}", exc_info=True)
            self._show_empty_state(
                "⚠️ Error Loading Talks",
                f"Failed to load talks from database.\n\n"
                f"Error: {str(e)}\n\n"
                f"Check logs for more details."
            )

    def _show_empty_state(self, title: str, message: str):
        """Show empty state message.

        Args:
            title: Title to display (with emoji)
            message: Detailed message to display
        """
        empty_widget = QWidget()
        empty_layout = QVBoxLayout(empty_widget)
        empty_layout.setContentsMargins(40, 80, 40, 80)
        empty_layout.setSpacing(15)
        empty_layout.setAlignment(Qt.AlignCenter)

        # Title with emoji
        title_label = QLabel(title)
        title_label.setFont(QFont("Arial", 18, QFont.Bold))
        title_label.setStyleSheet("color: #ffffff;")
        title_label.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(title_label)

        # Message
        message_label = QLabel(message)
        message_label.setFont(QFont("Arial", 13))
        message_label.setStyleSheet("color: #8b8b9e; line-height: 1.5;")
        message_label.setAlignment(Qt.AlignCenter)
        message_label.setWordWrap(True)
        empty_layout.addWidget(message_label)

        self.content_layout.addWidget(empty_widget)
        self.content_layout.addStretch()

    def _create_session_card(self, session_id: str, db_provider) -> Optional[QWidget]:
        """Create a card for a session with its talks.

        Args:
            session_id: Session ID
            db_provider: Database provider

        Returns:
            QWidget containing session card or None if no talks
        """
        talks = db_provider.get_talks(session_id)
        if not talks:
            return None

        card = QFrame()
        card.setObjectName("sessionCard")
        card.setStyleSheet("""
            #sessionCard {
                background: #12121a;
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 12px;
                padding: 0px;
            }
        """)

        layout = QVBoxLayout(card)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # Session header
        session_header = QWidget()
        session_header.setStyleSheet("background: rgba(255, 255, 255, 0.02); border-radius: 12px 12px 0 0; padding: 16px;")
        header_layout = QHBoxLayout(session_header)
        header_layout.setContentsMargins(16, 16, 16, 16)

        session_label = QLabel(f"📂 Session: {session_id[:12]}...")
        session_label.setFont(QFont("Courier", 11, QFont.Bold))
        session_label.setStyleSheet("color: #8b8b9e;")
        header_layout.addWidget(session_label)

        talk_count = QLabel(f"{len(talks)} talk{'s' if len(talks) != 1 else ''}")
        talk_count.setFont(QFont("Arial", 10))
        talk_count.setStyleSheet("color: #4a4a5e;")
        header_layout.addWidget(talk_count)

        header_layout.addStretch()

        layout.addWidget(session_header)

        # Talk list
        for talk in talks:
            talk_widget = self._create_talk_item(talk, session_id, db_provider)
            layout.addWidget(talk_widget)

        return card

    def _create_talk_item(self, talk: Dict, session_id: str, db_provider) -> QWidget:
        """Create a single talk item.

        Args:
            talk: Talk data
            session_id: Session ID
            db_provider: Database provider

        Returns:
            QWidget containing talk item
        """
        item = QWidget()
        item.setStyleSheet("""
            background: transparent;
            border-bottom: 1px solid rgba(255, 255, 255, 0.06);
            padding: 16px;
        """)

        layout = QHBoxLayout(item)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        # Talk info
        info_widget = QWidget()
        info_layout = QVBoxLayout(info_widget)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(4)

        title_label = QLabel(talk.get('title', 'Untitled Talk'))
        title_label.setFont(QFont("Arial", 12, QFont.DemiBold))
        title_label.setStyleSheet("color: #ffffff;")
        info_layout.addWidget(title_label)

        presenter = talk.get('presenter_name', '')
        if presenter:
            presenter_label = QLabel(f"👤 {presenter}")
            presenter_label.setFont(QFont("Arial", 10))
            presenter_label.setStyleSheet("color: #8b8b9e;")
            info_layout.addWidget(presenter_label)

        layout.addWidget(info_widget, 1)

        # Action buttons
        edit_btn = QPushButton("✏️ Edit")
        edit_btn.setFont(QFont("Arial", 10))
        edit_btn.setCursor(Qt.PointingHandCursor)
        edit_btn.setStyleSheet("""
            QPushButton {
                background: rgba(0, 212, 255, 0.1);
                color: #00d4ff;
                border: 1px solid rgba(0, 212, 255, 0.3);
                border-radius: 6px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background: rgba(0, 212, 255, 0.2);
            }
        """)
        edit_btn.clicked.connect(lambda: self._edit_talk(talk, session_id, db_provider))
        layout.addWidget(edit_btn)

        delete_btn = QPushButton("🗑️ Delete")
        delete_btn.setFont(QFont("Arial", 10))
        delete_btn.setCursor(Qt.PointingHandCursor)
        delete_btn.setStyleSheet("""
            QPushButton {
                background: rgba(239, 68, 68, 0.1);
                color: #ef4444;
                border: 1px solid rgba(239, 68, 68, 0.3);
                border-radius: 6px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background: rgba(239, 68, 68, 0.2);
            }
        """)
        delete_btn.clicked.connect(lambda: self._delete_talk(talk, session_id, db_provider))
        layout.addWidget(delete_btn)

        return item

    def _edit_talk(self, talk: Dict, session_id: str, db_provider):
        """Edit a talk's details.

        Args:
            talk: Talk data
            session_id: Session ID
            db_provider: Database provider
        """
        dialog = EditTalkDialog(
            talk.get('title', ''),
            talk.get('presenter_name', ''),
            self
        )

        if dialog.exec_() == QDialog.Accepted:
            new_title, new_presenter = dialog.get_values()

            if not new_title.strip():
                QMessageBox.warning(self, "Invalid Input", "Talk title cannot be empty.")
                return

            try:
                # Update in database
                talk_data = {
                    'title': new_title,
                    'presenter_name': new_presenter
                }
                success = db_provider.update_talk(talk['talk_id'], talk_data)

                if success:
                    logger.info(f"Updated talk {talk['talk_id']}: {new_title}")
                    QMessageBox.information(self, "Success", "Talk updated successfully!")
                    self._load_talks()  # Refresh
                else:
                    QMessageBox.critical(self, "Error", "Failed to update talk.")

            except Exception as e:
                logger.error(f"Failed to update talk: {e}")
                QMessageBox.critical(self, "Error", f"Failed to update talk: {str(e)}")

    def _delete_talk(self, talk: Dict, session_id: str, db_provider):
        """Delete a talk.

        Args:
            talk: Talk data
            session_id: Session ID
            db_provider: Database provider
        """
        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to delete the talk '{talk.get('title', 'Untitled')}'?\n\n"
            "This will also delete all slides associated with this talk.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            try:
                success = db_provider.delete_talk(talk['talk_id'])

                if success:
                    logger.info(f"Deleted talk {talk['talk_id']}")
                    QMessageBox.information(self, "Success", "Talk deleted successfully!")
                    self._load_talks()  # Refresh
                else:
                    QMessageBox.critical(self, "Error", "Failed to delete talk.")

            except Exception as e:
                logger.error(f"Failed to delete talk: {e}")
                QMessageBox.critical(self, "Error", f"Failed to delete talk: {str(e)}")

    def closeEvent(self, event):
        """Handle window close event.

        Args:
            event: Close event
        """
        logger.info("Talk manager window closing")
        self.close_requested.emit()
        event.accept()
