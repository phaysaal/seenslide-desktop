"""Slide Deck window — upload PDF/PPTX as slides, with optional live sync and voice."""

import io
import logging
import time
from pathlib import Path
from typing import List, Optional

from PIL import Image
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGroupBox,
    QFileDialog, QRadioButton, QButtonGroup, QCheckBox, QComboBox,
    QLineEdit, QProgressBar, QMessageBox, QApplication, QShortcut, QSizePolicy,
)
from PyQt5.QtCore import Qt, pyqtSignal, QThread, QTimer
from PyQt5.QtGui import QFont, QPixmap, QImage, QKeySequence

from modules.slides.converter import SlideConverter
from modules.storage.providers.cloud_provider import CloudStorageProvider
from modules.voice.recorder import VoiceRecorder
from modules.voice.cloud_uploader import VoiceCloudUploader
from core.bus.event_bus import EventBus
from core.interfaces.events import Event, EventType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Background worker for file conversion
# ---------------------------------------------------------------------------

class ConvertWorker(QThread):
    """Converts a file to slide images in a background thread."""

    finished = pyqtSignal(list)       # List[PIL.Image]
    failed = pyqtSignal(str)          # error message
    progress = pyqtSignal(str)        # status text

    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)
        self.file_path = file_path

    def run(self):
        try:
            self.progress.emit("Converting slides...")
            images = SlideConverter.convert(self.file_path)
            self.finished.emit(images)
        except Exception as e:
            self.failed.emit(str(e))


# ---------------------------------------------------------------------------
# Background worker for bulk upload
# ---------------------------------------------------------------------------

class UploadWorker(QThread):
    """Uploads all slide images to the cloud."""

    progress = pyqtSignal(int, int)     # (current, total)
    finished = pyqtSignal(str)          # viewer URL
    failed = pyqtSignal(str)

    def __init__(self, cloud: CloudStorageProvider, images: List[Image.Image],
                 talk_name: str, presenter: str, parent=None):
        super().__init__(parent)
        self.cloud = cloud
        self.images = images
        self.talk_name = talk_name
        self.presenter = presenter

    def run(self):
        try:
            # Create session
            session_id = self.cloud.start_session(
                session_id="",
                session_name=self.talk_name,
                presenter_name=self.presenter or "Unknown",
            )
            if not session_id:
                self.failed.emit("Failed to create cloud session")
                return

            # Create talk
            self.cloud.create_talk(
                session_id=session_id,
                talk_name=self.talk_name,
                presenter_name=self.presenter,
            )

            # Upload slides
            total = len(self.images)
            for i, img in enumerate(self.images):
                self.progress.emit(i + 1, total)

                # Convert PIL Image to JPEG bytes
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=90)
                jpeg_bytes = buf.getvalue()

                # Build a minimal ProcessedSlide-like object
                from core.models.slide import ProcessedSlide
                slide = ProcessedSlide(
                    slide_id=f"slide-{i+1}",
                    sequence_number=i + 1,
                )
                self.cloud.save_slide(slide, image_data=jpeg_bytes)

            viewer_url = f"{self.cloud.api_url}/{session_id}"
            self.finished.emit(viewer_url)

        except Exception as e:
            self.failed.emit(str(e))


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class SlideDeckWindow(QWidget):
    """Window for uploading PDF/PPTX as slides."""

    close_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._images: List[Image.Image] = []
        self._file_path: Optional[str] = None
        self._cloud: Optional[CloudStorageProvider] = None
        self._current_slide: int = 0
        self._session_id: Optional[str] = None
        self._is_presenting: bool = False
        self._slides_uploaded: int = 0

        # Voice
        self._event_bus = EventBus()
        self._voice_recorder: Optional[VoiceRecorder] = None
        self._voice_uploader: Optional[VoiceCloudUploader] = None

        self._init_cloud()
        self._setup_ui()
        logger.info("SlideDeckWindow initialized")

    def _init_cloud(self):
        """Initialize cloud provider from config."""
        import yaml
        config_path = Path(__file__).parent.parent.parent / "config" / "config.yaml"
        try:
            with open(config_path, "r") as f:
                cfg = yaml.safe_load(f)
            cloud_cfg = cfg.get("cloud", {})
            if cloud_cfg.get("enabled"):
                self._cloud = CloudStorageProvider()
                self._cloud.initialize(cloud_cfg)
        except Exception as e:
            logger.warning(f"Cloud config not loaded: {e}")

    # ------------------------------------------------------------------
    # UI Setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        from gui.utils.styles import (
            set_window_bg, make_card, btn_primary, btn_danger, btn_ghost,
            input_style, section_title_style, hint_style,
            FONT_TITLE, FONT_SECTION, TEXT, TEXT_MUTED, PRIMARY, INPUT_BORDER,
        )

        self.setWindowTitle("Upload Slides — SeenSlide")
        self.setMinimumSize(560, 560)
        set_window_bg(self)

        main = QVBoxLayout(self)
        main.setSpacing(12)
        main.setContentsMargins(20, 20, 20, 20)

        # Title
        title = QLabel("Upload Slides")
        title.setFont(FONT_TITLE)
        title.setStyleSheet(f"color: {TEXT};")
        main.addWidget(title)

        subtitle = QLabel("Import a PDF or PowerPoint file as presentation slides")
        subtitle.setFont(QFont("Arial", 11))
        subtitle.setStyleSheet(f"color: {TEXT_MUTED};")
        main.addWidget(subtitle)

        main.addSpacing(8)

        # --- File picker ---
        file_card = make_card(self)
        fl = QVBoxLayout(file_card)
        fl.setContentsMargins(18, 14, 18, 14)
        ft = QLabel("File")
        ft.setStyleSheet(section_title_style())
        fl.addWidget(ft)
        file_row = QHBoxLayout()
        self._file_label = QLabel("No file selected")
        self._file_label.setStyleSheet(f"color: {TEXT_MUTED}; background: transparent;")
        file_row.addWidget(self._file_label, 1)
        pick_btn = QPushButton("Choose File...")
        pick_btn.setCursor(Qt.PointingHandCursor)
        pick_btn.setStyleSheet(btn_primary())
        pick_btn.clicked.connect(self._pick_file)
        file_row.addWidget(pick_btn)
        fl.addLayout(file_row)
        main.addWidget(file_card)

        # --- Slide count info ---
        self._slide_count_label = QLabel("")
        self._slide_count_label.setFont(QFont("Arial", 11))
        self._slide_count_label.setStyleSheet("color: #16a34a; font-weight: bold;")
        main.addWidget(self._slide_count_label)

        # --- Mode selection ---
        mode_card = make_card(self)
        ml = QVBoxLayout(mode_card)
        ml.setContentsMargins(18, 14, 18, 14)
        mt = QLabel("Upload Mode")
        mt.setStyleSheet(section_title_style())
        ml.addWidget(mt)
        self._mode_group = QButtonGroup(self)
        radio_style = f"QRadioButton {{ color: {TEXT}; font-size: 13px; background: transparent; }}"
        self._radio_all = QRadioButton("Upload all slides at once")
        self._radio_all.setStyleSheet(radio_style)
        self._radio_sync = QRadioButton("Sync with my live talk (advance slides manually)")
        self._radio_sync.setStyleSheet(radio_style)
        self._radio_all.setChecked(True)
        self._mode_group.addButton(self._radio_all, 0)
        self._mode_group.addButton(self._radio_sync, 1)
        ml.addWidget(self._radio_all)
        ml.addWidget(self._radio_sync)
        main.addWidget(mode_card)

        # --- Talk info ---
        info_card = make_card(self)
        il = QVBoxLayout(info_card)
        il.setContentsMargins(18, 14, 18, 14)
        it = QLabel("Talk Information")
        it.setStyleSheet(section_title_style())
        il.addWidget(it)
        self.setStyleSheet(input_style())  # Apply to all inputs in this window
        row1 = QHBoxLayout()
        lbl1 = QLabel("Title:")
        lbl1.setStyleSheet(f"color: {TEXT}; background: transparent;")
        row1.addWidget(lbl1)
        self._title_input = QLineEdit()
        self._title_input.setPlaceholderText("e.g., Lecture 5: Data Structures")
        self._title_input.setFixedHeight(36)
        row1.addWidget(self._title_input)
        il.addLayout(row1)
        row2 = QHBoxLayout()
        lbl2 = QLabel("Presenter:")
        lbl2.setStyleSheet(f"color: {TEXT}; background: transparent;")
        row2.addWidget(lbl2)
        self._presenter_input = QLineEdit()
        self._presenter_input.setPlaceholderText("e.g., Dr. Smith")
        self._presenter_input.setFixedHeight(36)
        row2.addWidget(self._presenter_input)
        il.addLayout(row2)
        main.addWidget(info_card)

        # --- Voice recording ---
        self._voice_check = QCheckBox("Record audio (microphone)")
        self._mic_combo = QComboBox()
        self._mic_combo.addItem("Default microphone", None)
        self._populate_mics()
        self._mic_combo.setVisible(False)
        self._voice_check.toggled.connect(self._mic_combo.setVisible)

        vl = QHBoxLayout()
        vl.addWidget(self._voice_check)
        vl.addWidget(self._mic_combo)
        vl.addStretch()
        main.addLayout(vl)

        # --- Progress bar ---
        self._progress = QProgressBar()
        self._progress.setTextVisible(True)
        self._progress.setVisible(False)
        self._progress.setStyleSheet(f"""
            QProgressBar {{ border: 1px solid {INPUT_BORDER}; border-radius: 6px; height: 22px; text-align: center; background: white; }}
            QProgressBar::chunk {{ background: {PRIMARY}; border-radius: 5px; }}
        """)
        main.addWidget(self._progress)

        # --- Status ---
        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet("color: #64748b; font-size: 12px;")
        main.addWidget(self._status_label)

        # --- Presenter view (hidden until sync mode starts) ---
        self._presenter_frame = QWidget()
        self._presenter_frame.setVisible(False)
        pfl = QVBoxLayout(self._presenter_frame)
        pfl.setContentsMargins(0, 0, 0, 0)

        self._slide_preview = QLabel()
        self._slide_preview.setAlignment(Qt.AlignCenter)
        self._slide_preview.setMinimumHeight(280)
        self._slide_preview.setStyleSheet(
            "background: #0f172a; border-radius: 8px; padding: 4px;"
        )
        pfl.addWidget(self._slide_preview)

        nav = QHBoxLayout()
        self._prev_btn = QPushButton("Prev")
        self._prev_btn.setCursor(Qt.PointingHandCursor)
        self._prev_btn.setStyleSheet(btn_ghost())
        self._prev_btn.clicked.connect(self._prev_slide)
        nav.addWidget(self._prev_btn)

        self._slide_num_label = QLabel("0 / 0")
        self._slide_num_label.setFont(QFont("Arial", 13, QFont.Bold))
        self._slide_num_label.setAlignment(Qt.AlignCenter)
        nav.addWidget(self._slide_num_label, 1)

        self._next_btn = QPushButton("Next")
        self._next_btn.setCursor(Qt.PointingHandCursor)
        self._next_btn.setStyleSheet(btn_primary())
        self._next_btn.clicked.connect(self._next_slide)
        nav.addWidget(self._next_btn)

        pfl.addLayout(nav)

        self._voice_indicator = QLabel("")
        self._voice_indicator.setStyleSheet("color: #dc2626; font-weight: bold;")
        self._voice_indicator.setVisible(False)
        pfl.addWidget(self._voice_indicator)

        hint = QLabel("Keyboard:  \u2190 \u2192  or  Space = Next")
        hint.setStyleSheet("color: #94a3b8; font-size: 11px;")
        hint.setAlignment(Qt.AlignCenter)
        pfl.addWidget(hint)

        main.addWidget(self._presenter_frame)

        # --- Action buttons ---
        main.addStretch()
        btn_row = QHBoxLayout()
        self._start_btn = QPushButton("Start")
        self._start_btn.setFont(QFont("Arial", 12, QFont.Bold))
        self._start_btn.setCursor(Qt.PointingHandCursor)
        self._start_btn.setMinimumHeight(42)
        self._start_btn.setStyleSheet(btn_primary("min-width: 100px;"))
        self._start_btn.clicked.connect(self._on_start)
        self._start_btn.setEnabled(False)

        self._stop_btn = QPushButton("Stop Presenting")
        self._stop_btn.setFont(QFont("Arial", 12, QFont.Bold))
        self._stop_btn.setCursor(Qt.PointingHandCursor)
        self._stop_btn.setMinimumHeight(42)
        self._stop_btn.setStyleSheet(btn_danger("min-width: 100px;"))
        self._stop_btn.clicked.connect(self._on_stop)
        self._stop_btn.setVisible(False)

        close_btn = QPushButton("Close")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(btn_ghost())
        close_btn.clicked.connect(self.close)

        btn_row.addWidget(close_btn)
        btn_row.addStretch()
        btn_row.addWidget(self._stop_btn)
        btn_row.addWidget(self._start_btn)
        main.addLayout(btn_row)

        # --- Keyboard shortcuts ---
        QShortcut(QKeySequence(Qt.Key_Right), self, self._next_slide)
        QShortcut(QKeySequence(Qt.Key_Left), self, self._prev_slide)
        QShortcut(QKeySequence(Qt.Key_Space), self, self._next_slide)

    # ------------------------------------------------------------------
    # File picking & conversion
    # ------------------------------------------------------------------

    def _pick_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Presentation",
            str(Path.home()),
            "Presentations (*.pdf *.pptx *.ppt *.odp);;All Files (*)",
        )
        if not path:
            return

        self._file_path = path
        self._file_label.setText(Path(path).name)
        self._start_btn.setEnabled(False)
        self._slide_count_label.setText("")
        self._status_label.setText("Converting file...")

        # Auto-fill title from filename
        stem = Path(path).stem.replace("_", " ").replace("-", " ")
        if not self._title_input.text().strip():
            self._title_input.setText(stem)

        # Convert in background
        self._worker = ConvertWorker(path)
        self._worker.finished.connect(self._on_convert_done)
        self._worker.failed.connect(self._on_convert_failed)
        self._worker.start()

    def _on_convert_done(self, images: list):
        self._images = images
        n = len(images)
        self._slide_count_label.setText(f"Found {n} slide{'s' if n != 1 else ''}")
        self._status_label.setText("")
        self._start_btn.setEnabled(n > 0)
        logger.info(f"Converted {n} slides from {self._file_path}")

    def _on_convert_failed(self, error: str):
        self._images = []
        self._slide_count_label.setText("")
        self._status_label.setText(f"Conversion failed: {error}")
        QMessageBox.critical(self, "Conversion Failed", error)

    # ------------------------------------------------------------------
    # Start
    # ------------------------------------------------------------------

    def _on_start(self):
        if not self._images:
            return

        title = self._title_input.text().strip()
        if not title:
            QMessageBox.warning(self, "Missing Title", "Please enter a talk title.")
            return

        if not self._cloud or not self._cloud.enabled:
            QMessageBox.warning(self, "Cloud Not Configured",
                                "Cloud sync must be enabled in config.yaml.")
            return

        if self._radio_all.isChecked():
            self._start_upload_all()
        else:
            self._start_sync_mode()

    # ------------------------------------------------------------------
    # Upload All mode
    # ------------------------------------------------------------------

    def _start_upload_all(self):
        title = self._title_input.text().strip()
        presenter = self._presenter_input.text().strip()

        self._start_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._progress.setMaximum(len(self._images))
        self._progress.setValue(0)
        self._status_label.setText("Uploading slides...")

        self._upload_worker = UploadWorker(
            self._cloud, self._images, title, presenter
        )
        self._upload_worker.progress.connect(self._on_upload_progress)
        self._upload_worker.finished.connect(self._on_upload_done)
        self._upload_worker.failed.connect(self._on_upload_failed)
        self._upload_worker.start()

    def _on_upload_progress(self, current: int, total: int):
        self._progress.setValue(current)
        self._status_label.setText(f"Uploading slide {current} of {total}...")

    def _on_upload_done(self, viewer_url: str):
        self._progress.setVisible(False)
        self._session_id = self._cloud.cloud_session_id
        self._status_label.setText(
            f"All {len(self._images)} slides uploaded!\n"
            f"Viewer URL: {viewer_url}"
        )
        QMessageBox.information(
            self, "Upload Complete",
            f"All {len(self._images)} slides uploaded.\n\n"
            f"Viewers can access at:\n{viewer_url}"
        )
        self._start_btn.setEnabled(True)

    def _on_upload_failed(self, error: str):
        self._progress.setVisible(False)
        self._status_label.setText(f"Upload failed: {error}")
        self._start_btn.setEnabled(True)
        QMessageBox.critical(self, "Upload Failed", error)

    # ------------------------------------------------------------------
    # Sync (live presenter) mode
    # ------------------------------------------------------------------

    def _start_sync_mode(self):
        title = self._title_input.text().strip()
        presenter = self._presenter_input.text().strip()

        # Create cloud session + talk
        session_id = self._cloud.start_session(
            session_id="",
            session_name=title,
            presenter_name=presenter or "Unknown",
        )
        if not session_id:
            QMessageBox.critical(self, "Error", "Failed to create cloud session.")
            return

        self._session_id = session_id
        self._cloud.create_talk(
            session_id=session_id,
            talk_name=title,
            presenter_name=presenter,
        )

        # Start voice recording if checked
        if self._voice_check.isChecked():
            self._start_voice(session_id)

        # Switch to presenter UI
        self._is_presenting = True
        self._current_slide = 0
        self._slides_uploaded = 0
        self._start_btn.setVisible(False)
        self._stop_btn.setVisible(True)
        self._presenter_frame.setVisible(True)

        viewer_url = f"{self._cloud.api_url}/{session_id}"
        self._status_label.setText(f"Live session: {viewer_url}")

        # Show and upload first slide
        self._show_slide(0)
        self._upload_current_slide()

        logger.info(f"Sync mode started: {session_id} ({len(self._images)} slides)")

    def _show_slide(self, index: int):
        """Display slide at given index in the preview."""
        if not self._images or index < 0 or index >= len(self._images):
            return
        self._current_slide = index
        self._slide_num_label.setText(f"{index + 1} / {len(self._images)}")

        img = self._images[index]

        # Convert PIL → QPixmap
        data = img.convert("RGB").tobytes("raw", "RGB")
        qimg = QImage(data, img.width, img.height, img.width * 3, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg)

        # Scale to fit preview area
        scaled = pixmap.scaled(
            self._slide_preview.width() - 8,
            self._slide_preview.height() - 8,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self._slide_preview.setPixmap(scaled)

    def _upload_current_slide(self):
        """Upload the current slide to the cloud."""
        if not self._cloud or not self._images:
            return

        idx = self._current_slide
        img = self._images[idx]

        # Convert to JPEG bytes
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        jpeg_bytes = buf.getvalue()

        from core.models.slide import ProcessedSlide
        slide = ProcessedSlide(
            slide_id=f"slide-{idx+1}",
            sequence_number=idx + 1,
        )
        self._cloud.save_slide(slide, image_data=jpeg_bytes)
        self._slides_uploaded += 1
        logger.info(f"Uploaded slide {idx + 1}/{len(self._images)}")

        # Upload voice chunk + marker on slide advance
        if self._voice_recorder and self._voice_recorder.is_recording:
            self._voice_recorder.add_marker(idx + 1)
            if self._voice_uploader:
                chunk = self._voice_recorder.flush_chunk()
                if chunk:
                    markers = self._voice_recorder.markers
                    ts = markers[-1].timestamp_seconds if markers else 0.0
                    self._voice_uploader.upload_chunk(chunk, idx + 1, ts)

    def _next_slide(self):
        if not self._is_presenting:
            return
        if self._current_slide < len(self._images) - 1:
            self._show_slide(self._current_slide + 1)
            self._upload_current_slide()

    def _prev_slide(self):
        if not self._is_presenting:
            return
        if self._current_slide > 0:
            self._show_slide(self._current_slide - 1)
            # Don't re-upload — prev is for navigation, not a new slide event

    # ------------------------------------------------------------------
    # Voice recording
    # ------------------------------------------------------------------

    def _start_voice(self, cloud_session_id: str):
        """Start local voice recording + cloud voice session."""
        storage_dir = Path.home() / ".local" / "share" / "seenslide" / "voice"
        mic_device = self._mic_combo.currentData()

        self._voice_recorder = VoiceRecorder(
            event_bus=self._event_bus,
            output_dir=str(storage_dir),
            session_id=cloud_session_id,
            device=mic_device,
        )
        if not self._voice_recorder.start():
            logger.warning("Voice recording failed to start")
            self._voice_recorder = None
            return

        self._voice_indicator.setText("REC")
        self._voice_indicator.setVisible(True)

        # Start cloud voice upload
        if self._cloud and self._cloud.api_url:
            import yaml
            config_path = Path(__file__).parent.parent.parent / "config" / "config.yaml"
            try:
                with open(config_path) as f:
                    token = yaml.safe_load(f).get("cloud", {}).get("session_token", "")
            except Exception:
                token = ""

            self._voice_uploader = VoiceCloudUploader(self._cloud.api_url, token)
            self._voice_uploader.start_cloud_recording(cloud_session_id)

    def _stop_voice(self) -> Optional[str]:
        """Stop voice recording, upload final chunk, return WAV path."""
        path = None
        if self._voice_recorder and self._voice_recorder.is_recording:
            # Final chunk upload
            if self._voice_uploader:
                chunk = self._voice_recorder.flush_chunk()
                if chunk:
                    markers = self._voice_recorder.markers
                    slide_num = markers[-1].slide_number if markers else 0
                    ts = markers[-1].timestamp_seconds if markers else 0.0
                    self._voice_uploader.upload_chunk(chunk, slide_num, ts)

            duration = self._voice_recorder.duration_seconds
            path = self._voice_recorder.stop()

            if self._voice_uploader:
                self._voice_uploader.stop_cloud_recording(duration)
                self._voice_uploader = None

            self._voice_indicator.setVisible(False)
        return path

    # ------------------------------------------------------------------
    # Stop presenting
    # ------------------------------------------------------------------

    def _on_stop(self):
        if not self._is_presenting:
            return

        reply = QMessageBox.question(
            self, "Stop Presenting",
            "Stop the live presentation?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        voice_path = self._stop_voice()
        self._is_presenting = False
        self._stop_btn.setVisible(False)
        self._start_btn.setVisible(True)
        self._start_btn.setEnabled(True)
        self._presenter_frame.setVisible(False)

        viewer_url = f"{self._cloud.api_url}/{self._session_id}" if self._cloud else ""
        voice_msg = f"\n\nAudio saved to:\n{voice_path}" if voice_path else ""

        QMessageBox.information(
            self, "Presentation Ended",
            f"Uploaded {self._slides_uploaded} slides.\n\n"
            f"Viewer URL: {viewer_url}"
            + voice_msg
        )
        self._status_label.setText(f"Session ended. Viewer URL: {viewer_url}")
        logger.info("Sync mode stopped")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _populate_mics(self):
        try:
            devices = VoiceRecorder.list_audio_devices()
            for d in devices:
                self._mic_combo.addItem(f"{d['name']} ({d['channels']}ch)", d["index"])
        except Exception:
            pass

    @staticmethod
    def _btn_style(color: str) -> str:
        return f"""
            QPushButton {{
                background: {color}; color: white; border: none;
                border-radius: 8px; padding: 8px 18px; font-size: 12px;
            }}
            QPushButton:hover {{ background: {color}dd; }}
            QPushButton:disabled {{ background: #94a3b8; }}
        """

    def closeEvent(self, event):
        if self._is_presenting:
            self._stop_voice()
        self.close_requested.emit()
        event.accept()
