# SeenSlide Desktop - Build Instructions

## Prerequisites

### Ubuntu/Debian
```bash
# Install build dependencies
sudo apt update
sudo apt install python3 python3-pip python3-venv ruby ruby-dev build-essential wget

# Install fpm for package creation
sudo gem install fpm

# Install PyInstaller
pip3 install pyinstaller

# Optional: ImageMagick for icon generation
sudo apt install imagemagick
```

### Fedora/RHEL
```bash
sudo dnf install python3 python3-pip ruby ruby-devel gcc make wget
sudo gem install fpm
pip3 install pyinstaller
```

## Building Installers

### Quick Build (.deb only)
```bash
cd build
./build_installer.sh
```

### Build All Formats
```bash
./build_installer.sh --all
```

### Build Specific Formats
```bash
./build_installer.sh --deb              # Debian/Ubuntu .deb
./build_installer.sh --rpm              # Fedora/RHEL .rpm
./build_installer.sh --appimage         # Portable AppImage
./build_installer.sh --deb --appimage   # Multiple formats
```

### Set Version Number
```bash
./build_installer.sh --version 1.2.0 --all
# Or use environment variable
VERSION=1.2.0 ./build_installer.sh --all
```

## Output

Built packages will be in `build/dist/`:
- `seenslide_X.X.X_amd64.deb` - Debian/Ubuntu package
- `seenslide-X.X.X.x86_64.rpm` - Fedora/RHEL package
- `SeenSlide-X.X.X-x86_64.AppImage` - Portable AppImage

## Installing

### Debian/Ubuntu
```bash
sudo dpkg -i dist/seenslide_1.0.0_amd64.deb
# If there are dependency errors:
sudo apt -f install
```

### Fedora/RHEL
```bash
sudo rpm -i dist/seenslide-1.0.0.x86_64.rpm
# Or with dnf:
sudo dnf install dist/seenslide-1.0.0.x86_64.rpm
```

### AppImage (No Installation Required)
```bash
chmod +x SeenSlide-1.0.0-x86_64.AppImage
./SeenSlide-1.0.0-x86_64.AppImage
```

## Uninstalling

### Debian/Ubuntu
```bash
sudo apt remove seenslide
```

### Fedora/RHEL
```bash
sudo dnf remove seenslide
```

## Troubleshooting

### "fpm: command not found"
```bash
sudo gem install fpm
```

### PyInstaller import errors
Make sure all dependencies are installed:
```bash
pip3 install -r requirements.txt
```

### Icon not showing
Install ImageMagick and rebuild:
```bash
sudo apt install imagemagick
./build_installer.sh --deb
```

## Cross-Platform Builds

### Windows (Future)
- Use PyInstaller on Windows machine
- Create NSIS or Inno Setup installer

### macOS (Future)
- Use PyInstaller on macOS machine
- Create .dmg with create-dmg tool

## CI/CD Integration

Example GitHub Actions workflow:
```yaml
name: Build Installers

on:
  release:
    types: [created]

jobs:
  build-linux:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Install dependencies
        run: |
          sudo apt install ruby ruby-dev
          sudo gem install fpm
          pip install pyinstaller
          pip install -r requirements.txt

      - name: Build packages
        run: |
          cd build
          VERSION=${{ github.ref_name }} ./build_installer.sh --all

      - name: Upload artifacts
        uses: actions/upload-artifact@v3
        with:
          name: installers
          path: build/dist/*
```
