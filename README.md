# SeenSlide Desktop

**Real-time presentation sharing made simple and transparent.**

SeenSlide Desktop captures your presentations and shares them with remote audiences in real-time. Attendees follow along in their browser at `seenslide.com/{session-id}` — no install needed on their end.

---

## Features

### Presentation Modes

| Mode | Description |
|------|-------------|
| **Just One Talk** | Quick setup for a single presentation. Screen capture starts after a countdown, slides are uploaded as they change. Window closes when done. |
| **Multiple Talks (Conference)** | Long-running mode for events with multiple speakers. Admin dashboard runs in the browser. Talks are started/stopped individually. |
| **Upload Slides** | Import a PDF or PowerPoint file directly — no screen capture needed. Two sub-modes: **Upload All** (bulk) or **Sync with Talk** (manual advance with live session). |

### Smart Screen Capture
- **Automatic deduplication** — only uploads when the slide actually changes
- **Multiple strategies** — hash, perceptual, hybrid, or adaptive deduplication
- **Multi-monitor support** — capture from any connected display
- **Wayland & X11** — works on all major Linux desktop environments
- **Adjustable sensitivity** — slider from strict (catches small changes) to lenient

### Voice Recording
- **Optional microphone recording** during any talk
- **Automatic slide markers** — timestamps sync audio with each slide transition
- **Semi-live cloud upload** — audio chunks uploaded after each slide change + every 60 seconds
- **Local WAV backup** — full recording saved locally at `~/.local/share/seenslide/voice/`
- **Device selection** — pick which microphone to use

### Slide File Upload
- **PDF support** — renders each page as a slide image (via PyMuPDF)
- **PowerPoint support** — converts PPTX/PPT/ODP via LibreOffice headless
- **Upload All** — bulk upload all slides at once with progress bar
- **Sync with Talk** — presenter view with keyboard navigation (arrow keys / space bar), uploads one slide at a time as you advance

### Conference Mode
- **Admin dashboard** — web-based control panel at `http://localhost:8081`
- **Talk agenda** — paste a plain-text list of talks (`Title | Speaker | Description`), then select from a dropdown to auto-fill the form when starting each talk
- **QR code** — displayed in the admin panel for easy audience access
- **Background operation** — minimizes to system tray, admin panel stays in browser
- **Session persistence** — cloud session survives server restarts

### Auto-Update
- **Background version check** on startup against the cloud server
- **Broadcast messages** — server can push announcements to all desktop clients
- **In-app download** with SHA-256 verification and progress bar
- **Dismissed messages persist** across sessions

### Cloud Integration
- **Real-time sync** to [seenslide.com](https://seenslide.com) — viewers see slides appear live
- **Collections** — group talks into collections with optional password protection
- **Aliases** — human-readable URLs for collections
- **Cross-device access** — verify ownership via admin credentials

---

## Quick Start

### Install from .deb (Ubuntu/Debian)

```bash
sudo apt install ./seenslide_1.0.3_amd64.deb
seenslide
```

### Run from Source

```bash
git clone https://github.com/phaysaal/seenslide-desktop.git
cd seenslide-desktop

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

python -m gui.main
```

### First Launch

A window with three options appears:
1. **Start Presenting** — captures your screen, uploads slides live
2. **Set up conference...** — opens the admin dashboard for multi-talk events
3. **Or upload a PDF / PowerPoint file...** — import slides from a file

Keyboard shortcuts: `Enter` = Start, `C` = Conference, `U` = Upload, `M` = Manage Talks, `Esc` = Quit

---

## Configuration

Config file: `config/config.yaml`

```yaml
capture:
  provider: "portal"        # "portal" (Wayland) or "mss" (X11)
  interval_seconds: 2.0

deduplication:
  strategy: "hash"           # hash, perceptual, hybrid, adaptive
  perceptual_threshold: 0.95

storage:
  base_dir: "./data"

voice:
  enabled: true
  quality: "medium"          # low (16kHz), medium (44.1kHz), high (48kHz)
  channels: 1

cloud:
  enabled: true
  api_url: "https://seenslide.com"
  session_token: "your-token"
```

---

## Architecture

```
seenslide-desktop/
├── gui/                     # PyQt5 GUI
│   ├── main.py              # Application entry point
│   ├── windows/
│   │   ├── mode_selector.py       # Main launcher
│   │   ├── direct_talk_window.py  # Single talk mode
│   │   ├── conference_launcher.py # Conference mode
│   │   ├── slide_deck_window.py   # File upload mode
│   │   └── talk_manager_window.py # Manage past talks
│   └── widgets/
│       ├── update_banner.py       # Auto-update notifications
│       ├── region_selector.py     # Capture region picker
│       └── countdown_widget.py    # Pre-capture countdown
│
├── core/
│   ├── bus/event_bus.py     # Pub/sub event system
│   ├── config/              # YAML config loader
│   ├── interfaces/events.py # Event types (slide, voice, session)
│   ├── models/              # Session, Slide, CaptureMode
│   ├── registry/            # Plugin registry
│   └── updater/             # Auto-update checker + downloader
│
├── modules/
│   ├── capture/             # Screen capture (Wayland portal, MSS)
│   ├── dedup/               # Deduplication strategies
│   ├── storage/             # Local (SQLite) + cloud storage providers
│   ├── voice/               # Voice recording + cloud chunk upload
│   ├── slides/              # PDF/PPTX → image converter
│   ├── admin/               # Conference admin server + web UI
│   └── web/                 # Local viewer web server
│
├── seenslide/
│   └── orchestrator.py      # Coordinates capture → dedup → storage → voice
│
├── config/config.yaml       # App configuration
├── packaging/               # Build scripts (Linux .deb, macOS .dmg, Windows .exe)
└── .github/workflows/       # CI/CD (builds all platforms on tag push)
```

### Event Flow

```
Screen Capture → SLIDE_CAPTURED
       ↓
Deduplication  → SLIDE_UNIQUE (new) or SLIDE_DUPLICATE (skip)
       ↓
Storage        → SLIDE_STORED (local + cloud upload)
       ↓
Voice Recorder → VOICE_MARKER_ADDED (auto-timestamps audio)
       ↓
Cloud Uploader → Audio chunk uploaded (semi-live)
```

---

## Building Installers

### Linux (.deb)

```bash
bash packaging/build_installer.sh --deb --version 1.0.3
# Output: packaging/dist/seenslide_1.0.3_amd64.deb
```

### macOS (.dmg)

```bash
bash packaging/build_macos.sh --dmg --version 1.0.3
# Output: packaging/dist/macos/SeenSlide-1.0.3-macOS.dmg
```

### Windows (.exe)

```bat
packaging\build_windows.bat
```

### CI/CD

Push a git tag to build all platforms and create a GitHub Release:

```bash
git tag v1.0.3
git push --tags
```

---

## Security & Privacy

**When running locally:**
- No data sent anywhere — everything stays on your machine

**When connected to cloud:**
- Slide images (deduplicated screenshots) uploaded to seenslide.com
- Audio recording uploaded in chunks (only if voice recording is enabled)
- All communication over HTTPS
- No keystroke logging, no access to other applications, no telemetry

**Voice recording** is opt-in — unchecked by default. The microphone is only accessed when the user explicitly enables it before starting a talk.

---

## Conference Mode — Talk Agenda

For events with many talks, the admin can pre-load a talk list:

1. Open the admin dashboard in the browser
2. Click **Load List** in the Agenda section
3. Paste talks in plain text, one per line:
   ```
   Introduction to AI | Dr. Smith | Opening keynote
   Data Structures | Jane Doe | Trees and graphs
   Machine Learning | Bob Wilson
   Panel Discussion | Multiple | Q&A session
   ```
4. Click **Load** — a dropdown appears with all talks
5. Select a talk → form auto-fills with title, speaker, description
6. Click **Start Talk** — the talk starts and is marked as done in the list

Format: `Title | Speaker | Description` (speaker and description are optional)

---

## Dependencies

| Package | Purpose |
|---------|---------|
| PyQt5 | GUI framework |
| FastAPI + Uvicorn | Local web servers (admin + viewer) |
| Pillow | Image processing |
| imagehash | Perceptual deduplication |
| mss | X11 screen capture |
| sounddevice | Microphone recording |
| PyMuPDF | PDF → slide images |
| requests | Cloud API communication |
| PyYAML | Configuration |
| bcrypt + PyJWT | Authentication |
| qrcode | QR code generation |

---

## License

MIT License - see [LICENSE](LICENSE) for details.

---

## Links

- **Cloud Service**: [seenslide.com](https://seenslide.com)
- **Bug Reports**: [GitHub Issues](https://github.com/phaysaal/seenslide-desktop/issues)

---

**Made with care by the SeenSlide team**
