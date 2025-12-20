# SeenSlide Desktop - Open Source Screen Capture

**Real-time presentation sharing made simple and transparent.**

SeenSlide Desktop is an open-source screen capture application that intelligently captures your presentations and shares them with remote audiences in real-time. Perfect for lectures, webinars, sales demos, and remote teaching.

---

## 🔓 Why Open Source?

**Transparency = Trust**

When you install software that captures your screen, you deserve to know exactly what it does with your data. That's why SeenSlide Desktop is **100% open source**:

- ✅ **Auditable Security**: Every line of code is public - security researchers can verify there's no data theft or malicious behavior
- ✅ **Privacy First**: Your screen captures are processed locally - you control what gets shared
- ✅ **Community Driven**: Contributions, bug reports, and feature requests welcome
- ✅ **No Hidden Agenda**: What you see is what you get

---

## ✨ Features

### Core Capture
- **Smart Deduplication**: Only shares slides when content actually changes
- **Multi-Monitor Support**: Capture from any connected display
- **Wayland & X11**: Works on all major Linux desktop environments
- **Efficient Compression**: Minimal bandwidth usage

### Local Management
- **Private Sessions**: Run completely offline if desired
- **Local Admin Dashboard**: Manage your presentations from a web interface
- **Export Options**: Save slides as images or PDFs
- **Session History**: Review past presentations

### Cloud Integration (Optional)
- **Real-Time Sharing**: Connect to SeenSlide Cloud for remote viewing
- **Viewer Analytics**: See who's watching your presentation
- **Q&A Features**: Interact with your audience (requires cloud subscription)

---

## 🚀 Quick Start

### Installation

**Prerequisites:**
- Python 3.10 or higher
- pip package manager

**Install:**

```bash
# Clone the repository
git clone https://github.com/yourusername/seenslide-desktop.git
cd seenslide-desktop

# Install dependencies
pip install -r requirements.txt

# Run setup
python setup.py install

# Start SeenSlide
python seenslide.py
```

### First Launch

1. **Configure Capture Source**:
   ```bash
   python seenslide.py --configure
   ```

2. **Start a Local Session**:
   ```bash
   python seenslide.py --local
   ```

3. **Connect to Cloud** (optional):
   ```bash
   python seenslide.py --cloud --api-key YOUR_API_KEY
   ```

---

## 📖 Usage

### Basic Screen Capture

```bash
# Start capturing your primary monitor
python seenslide.py

# Capture from specific monitor
python seenslide.py --monitor 2

# Save locally without cloud sync
python seenslide.py --local --output ./my-presentation
```

### Local Admin Dashboard

```bash
# Start local admin server
python seenslide_admin.py

# Access at: http://localhost:5050
```

### Cloud Integration

To share your presentations with remote viewers:

1. Sign up at [seenslide.com](https://seenslide.com)
2. Get your API key from the dashboard
3. Configure desktop app:
   ```bash
   export SEENSLIDE_API_KEY="your-api-key-here"
   python seenslide.py --cloud
   ```

---

## 🏗️ Architecture

```
seenslide-desktop/
├── core/                  # Core framework
│   ├── auth/             # Authentication (cloud API)
│   ├── bus/              # Event system
│   ├── config/           # Configuration management
│   ├── interfaces/       # Plugin interfaces
│   ├── models/           # Data models
│   └── registry/         # Plugin registry
│
├── modules/
│   ├── capture/          # Screen capture providers
│   │   └── providers/   # Wayland portal, X11, etc.
│   ├── dedup/            # Deduplication strategies
│   ├── storage/          # Local & cloud storage
│   ├── admin/            # Admin web interface
│   ├── server/           # Local HTTP server
│   └── web/              # Web API
│
├── seenslide/           # Main application logic
│   ├── orchestrator.py  # Coordinates all components
│   ├── cli.py           # Command-line interface
│   └── app_starter.py   # Application startup
│
└── seenslide.py         # Entry point
```

---

## 🔒 Security & Privacy

### What Data is Collected?

**When running locally (`--local`):**
- ❌ NO data sent anywhere
- ✅ Everything stays on your machine
- ✅ You control all captured slides

**When connected to cloud (`--cloud`):**
- ✅ Slide images (deduplicated screenshots)
- ✅ Session metadata (title, timestamp)
- ✅ User authentication tokens
- ❌ NO keystroke logging
- ❌ NO audio recording (unless you explicitly enable voice features)
- ❌ NO access to other applications
- ❌ NO access to files outside presentation

### How is Data Transmitted?

- 🔐 **TLS 1.3 Encryption**: All cloud communication encrypted
- 🔐 **Secure WebSockets**: Real-time updates over WSS protocol
- 🔐 **API Key Authentication**: Your credentials never stored in plaintext
- 🔐 **No Third-Party Tracking**: No analytics, no telemetry

### Can I Audit the Code?

**Absolutely!** That's why it's open source:

```bash
# Search for network calls
grep -r "requests\|urllib\|http" modules/ core/

# Search for file system access
grep -r "open\|write\|delete" modules/ core/

# Search for subprocess execution
grep -r "subprocess\|popen\|system" modules/ core/
```

---

## 🛠️ Configuration

### Config File Location

```
~/.config/seenslide/config.yaml
```

### Example Configuration

```yaml
capture:
  monitor: 0  # Primary monitor
  fps: 1      # Capture once per second
  quality: 85 # JPEG quality (0-100)

deduplication:
  strategy: "hash"  # or "visual"
  threshold: 0.95   # Similarity threshold

cloud:
  enabled: false
  api_url: "https://api.seenslide.com"
  auto_sync: true

storage:
  local_path: "~/.local/share/seenslide/slides"
  max_sessions: 50
  max_storage_mb: 1000
```

---

## 🤝 Contributing

We welcome contributions from the community!

### How to Contribute

1. **Fork the repository**
2. **Create a feature branch**: `git checkout -b feature/my-feature`
3. **Make your changes**
4. **Add tests** (if applicable)
5. **Commit**: `git commit -m "Add my feature"`
6. **Push**: `git push origin feature/my-feature`
7. **Open a Pull Request**

### Development Setup

```bash
# Clone your fork
git clone https://github.com/YOUR-USERNAME/seenslide-desktop.git
cd seenslide-desktop

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dev dependencies
pip install -r requirements.txt
pip install pytest black flake8

# Run tests
pytest tests/

# Format code
black .

# Lint
flake8 modules/ core/ seenslide/
```

### Code of Conduct

- Be respectful and inclusive
- Provide constructive feedback
- Focus on the code, not the person
- Help newcomers feel welcome

---

## 📋 Roadmap

### Current Features (v1.0)
- ✅ Screen capture (Wayland, X11)
- ✅ Smart deduplication
- ✅ Local sessions
- ✅ Cloud synchronization
- ✅ Admin dashboard

### Planned Features
- [ ] Windows support (native screen capture)
- [ ] macOS support (Screen Capture Kit)
- [ ] Hardware acceleration (GPU encoding)
- [ ] Mobile app companion
- [ ] Plugin system for custom providers
- [ ] CLI-only mode (headless servers)
- [ ] Docker container support

---

## 🐛 Troubleshooting

### Screen Capture Not Working

**Linux (Wayland):**
```bash
# Install xdg-desktop-portal
sudo apt install xdg-desktop-portal xdg-desktop-portal-gtk

# Verify portal is running
systemctl --user status xdg-desktop-portal
```

**Linux (X11):**
```bash
# Install scrot or ImageMagick
sudo apt install scrot
```

### "Permission Denied" Errors

```bash
# Grant executable permissions
chmod +x seenslide.py seenslide_admin.py

# Check Python version
python --version  # Should be 3.10+
```

### Cloud Connection Issues

```bash
# Test API connectivity
curl https://api.seenslide.com/health

# Verify API key
python seenslide.py --test-auth
```

---

## 📜 License

**MIT License**

```
Copyright (c) 2024 SeenSlide Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## 🔗 Links

- **Cloud Service**: [seenslide.com](https://seenslide.com)
- **Documentation**: [docs.seenslide.com](https://docs.seenslide.com)
- **Bug Reports**: [GitHub Issues](https://github.com/yourusername/seenslide-desktop/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/seenslide-desktop/discussions)
- **Twitter**: [@SeenSlide](https://twitter.com/SeenSlide)

---

## 💬 Support

- **Community Support**: [GitHub Discussions](https://github.com/yourusername/seenslide-desktop/discussions)
- **Bug Reports**: [GitHub Issues](https://github.com/yourusername/seenslide-desktop/issues)
- **Email**: opensource@seenslide.com

---

## 🙏 Acknowledgments

SeenSlide Desktop is built with amazing open-source technologies:

- **FastAPI** - Modern web framework
- **CustomTkinter** - Beautiful GUI components
- **MSS** - Fast screen capture
- **ImageHash** - Perceptual hashing
- **Pillow** - Image processing
- **Python** - The language that powers it all

Thank you to all our contributors and the open-source community!

---

**Made with ❤️ by the SeenSlide community**

*Star ⭐ this repo if you find it useful!*
