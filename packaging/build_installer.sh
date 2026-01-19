#!/bin/bash
# =============================================================================
# SeenSlide Desktop Installer Builder
# Creates .deb, .rpm, and AppImage packages for Linux
# =============================================================================

set -e  # Exit on error

# Configuration
APP_NAME="seenslide"
APP_DISPLAY_NAME="SeenSlide"
APP_VERSION="${VERSION:-1.0.0}"
APP_DESCRIPTION="Slide capture and cloud sync tool for presentations"
APP_MAINTAINER="SeenSlide Team <support@seenslide.com>"
APP_URL="https://seenslide.com"
APP_CATEGORY="Utility"

# Directories
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="$SCRIPT_DIR/dist"
PACKAGE_DIR="$SCRIPT_DIR/package"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# =============================================================================
# Check Dependencies
# =============================================================================
check_dependencies() {
    log_info "Checking build dependencies..."

    local missing=()

    # Python 3.10+
    if ! command -v python3 &> /dev/null; then
        missing+=("python3")
    fi

    # pip
    if ! command -v pip3 &> /dev/null; then
        missing+=("python3-pip")
    fi

    # PyInstaller (will install if missing)
    if ! python3 -c "import PyInstaller" 2>/dev/null; then
        log_info "Installing PyInstaller..."
        pip3 install pyinstaller
    fi

    # fpm for .deb/.rpm creation
    if ! command -v fpm &> /dev/null; then
        missing+=("fpm (gem install fpm)")
    fi

    if [ ${#missing[@]} -ne 0 ]; then
        log_error "Missing dependencies: ${missing[*]}"
        echo ""
        echo "Install missing dependencies:"
        echo "  sudo apt install python3 python3-pip ruby ruby-dev build-essential"
        echo "  sudo gem install fpm"
        exit 1
    fi

    log_info "All dependencies satisfied"
}

# =============================================================================
# Clean Previous Build
# =============================================================================
clean_build() {
    log_info "Cleaning previous build..."
    rm -rf "$BUILD_DIR"
    rm -rf "$PACKAGE_DIR"
    rm -rf "$SCRIPT_DIR/build"
    rm -rf "$SCRIPT_DIR/*.spec"
    mkdir -p "$BUILD_DIR"
    mkdir -p "$PACKAGE_DIR"
}

# =============================================================================
# Build with PyInstaller
# =============================================================================
build_pyinstaller() {
    log_info "Building application with PyInstaller..."

    cd "$PROJECT_DIR"

    # Create spec file for more control
    cat > "$SCRIPT_DIR/seenslide.spec" << 'SPEC'
# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

block_cipher = None
project_dir = Path(SPECPATH).parent

# Collect all data files
datas = [
    (str(project_dir / 'config'), 'config'),
    (str(project_dir / 'gui'), 'gui'),
    (str(project_dir / 'core'), 'core'),
    (str(project_dir / 'modules'), 'modules'),
]

# Hidden imports that PyInstaller might miss
hiddenimports = [
    'customtkinter',
    'PyQt5',
    'PyQt5.QtCore',
    'PyQt5.QtGui',
    'PyQt5.QtWidgets',
    'PIL',
    'PIL.Image',
    'imagehash',
    'mss',
    'mss.linux',
    'fastapi',
    'uvicorn',
    'pydantic',
    'requests',
    'qrcode',
    'yaml',
    'dotenv',
]

a = Analysis(
    [str(project_dir / 'gui' / 'main.py')],
    pathex=[str(project_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='seenslide',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # No console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='seenslide',
)
SPEC

    # Run PyInstaller
    pyinstaller --clean --noconfirm "$SCRIPT_DIR/seenslide.spec"

    # Move output to build dir
    mv "$PROJECT_DIR/dist/seenslide" "$BUILD_DIR/seenslide"
    rm -rf "$PROJECT_DIR/dist" "$PROJECT_DIR/build"

    log_info "PyInstaller build complete"
}

# =============================================================================
# Create Desktop Entry
# =============================================================================
create_desktop_entry() {
    log_info "Creating desktop entry..."

    mkdir -p "$PACKAGE_DIR/usr/share/applications"
    cat > "$PACKAGE_DIR/usr/share/applications/seenslide.desktop" << EOF
[Desktop Entry]
Name=$APP_DISPLAY_NAME
Comment=$APP_DESCRIPTION
Exec=/opt/seenslide/seenslide
Icon=seenslide
Terminal=false
Type=Application
Categories=Utility;Office;
Keywords=presentation;slides;capture;screen;
StartupNotify=true
EOF
}

# =============================================================================
# Create Icon
# =============================================================================
create_icon() {
    log_info "Creating application icon..."

    # Create icon directories
    for size in 16 32 48 64 128 256; do
        mkdir -p "$PACKAGE_DIR/usr/share/icons/hicolor/${size}x${size}/apps"
    done

    # Check if icon exists in project
    if [ -f "$PROJECT_DIR/gui/assets/icon.png" ]; then
        # Resize icon for different sizes
        for size in 16 32 48 64 128 256; do
            if command -v convert &> /dev/null; then
                convert "$PROJECT_DIR/gui/assets/icon.png" -resize ${size}x${size} \
                    "$PACKAGE_DIR/usr/share/icons/hicolor/${size}x${size}/apps/seenslide.png"
            else
                cp "$PROJECT_DIR/gui/assets/icon.png" \
                    "$PACKAGE_DIR/usr/share/icons/hicolor/${size}x${size}/apps/seenslide.png"
            fi
        done
    else
        log_warn "No icon found at gui/assets/icon.png - using placeholder"
        # Create a simple placeholder icon (requires ImageMagick)
        if command -v convert &> /dev/null; then
            convert -size 256x256 xc:'#10b981' -gravity center \
                -fill white -font DejaVu-Sans-Bold -pointsize 120 \
                -annotate 0 'S' \
                "$PACKAGE_DIR/usr/share/icons/hicolor/256x256/apps/seenslide.png"
        fi
    fi
}

# =============================================================================
# Build .deb Package
# =============================================================================
build_deb() {
    log_info "Building .deb package..."

    # Prepare package directory structure
    mkdir -p "$PACKAGE_DIR/opt/seenslide"
    mkdir -p "$PACKAGE_DIR/usr/bin"

    # Copy application files
    cp -r "$BUILD_DIR/seenslide/"* "$PACKAGE_DIR/opt/seenslide/"

    # Create symlink in /usr/bin
    ln -sf /opt/seenslide/seenslide "$PACKAGE_DIR/usr/bin/seenslide"

    # Create desktop entry and icons
    create_desktop_entry
    create_icon

    # Create post-install script
    mkdir -p "$PACKAGE_DIR/DEBIAN"
    cat > "$SCRIPT_DIR/postinst" << 'EOF'
#!/bin/bash
# Update icon cache
if command -v gtk-update-icon-cache &> /dev/null; then
    gtk-update-icon-cache -f /usr/share/icons/hicolor 2>/dev/null || true
fi
# Update desktop database
if command -v update-desktop-database &> /dev/null; then
    update-desktop-database /usr/share/applications 2>/dev/null || true
fi
EOF
    chmod +x "$SCRIPT_DIR/postinst"

    # Build .deb with fpm
    cd "$SCRIPT_DIR"
    fpm -s dir -t deb \
        -n "$APP_NAME" \
        -v "$APP_VERSION" \
        --description "$APP_DESCRIPTION" \
        --maintainer "$APP_MAINTAINER" \
        --url "$APP_URL" \
        --category "$APP_CATEGORY" \
        --license "MIT" \
        --after-install "$SCRIPT_DIR/postinst" \
        --depends "libxcb-xinerama0" \
        --depends "libxcb-cursor0" \
        --depends "libgl1" \
        -C "$PACKAGE_DIR" \
        -p "$BUILD_DIR/${APP_NAME}_${APP_VERSION}_amd64.deb" \
        .

    log_info "Created: $BUILD_DIR/${APP_NAME}_${APP_VERSION}_amd64.deb"
}

# =============================================================================
# Build .rpm Package
# =============================================================================
build_rpm() {
    log_info "Building .rpm package..."

    cd "$SCRIPT_DIR"
    fpm -s dir -t rpm \
        -n "$APP_NAME" \
        -v "$APP_VERSION" \
        --description "$APP_DESCRIPTION" \
        --maintainer "$APP_MAINTAINER" \
        --url "$APP_URL" \
        --category "$APP_CATEGORY" \
        --license "MIT" \
        --after-install "$SCRIPT_DIR/postinst" \
        -C "$PACKAGE_DIR" \
        -p "$BUILD_DIR/${APP_NAME}-${APP_VERSION}.x86_64.rpm" \
        .

    log_info "Created: $BUILD_DIR/${APP_NAME}-${APP_VERSION}.x86_64.rpm"
}

# =============================================================================
# Build AppImage
# =============================================================================
build_appimage() {
    log_info "Building AppImage..."

    APPDIR="$SCRIPT_DIR/SeenSlide.AppDir"
    rm -rf "$APPDIR"
    mkdir -p "$APPDIR/usr/bin"
    mkdir -p "$APPDIR/usr/share/applications"
    mkdir -p "$APPDIR/usr/share/icons/hicolor/256x256/apps"

    # Copy application
    cp -r "$BUILD_DIR/seenslide/"* "$APPDIR/usr/bin/"

    # Create desktop file
    cat > "$APPDIR/seenslide.desktop" << EOF
[Desktop Entry]
Name=$APP_DISPLAY_NAME
Comment=$APP_DESCRIPTION
Exec=seenslide
Icon=seenslide
Terminal=false
Type=Application
Categories=Utility;Office;
EOF
    cp "$APPDIR/seenslide.desktop" "$APPDIR/usr/share/applications/"

    # Copy icon
    if [ -f "$PACKAGE_DIR/usr/share/icons/hicolor/256x256/apps/seenslide.png" ]; then
        cp "$PACKAGE_DIR/usr/share/icons/hicolor/256x256/apps/seenslide.png" "$APPDIR/"
        cp "$PACKAGE_DIR/usr/share/icons/hicolor/256x256/apps/seenslide.png" \
            "$APPDIR/usr/share/icons/hicolor/256x256/apps/"
    fi

    # Create AppRun
    cat > "$APPDIR/AppRun" << 'EOF'
#!/bin/bash
SELF=$(readlink -f "$0")
HERE=${SELF%/*}
export PATH="${HERE}/usr/bin:${PATH}"
export LD_LIBRARY_PATH="${HERE}/usr/lib:${LD_LIBRARY_PATH}"
exec "${HERE}/usr/bin/seenslide" "$@"
EOF
    chmod +x "$APPDIR/AppRun"

    # Download appimagetool if needed
    if [ ! -f "$SCRIPT_DIR/appimagetool" ]; then
        log_info "Downloading appimagetool..."
        wget -q "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage" \
            -O "$SCRIPT_DIR/appimagetool"
        chmod +x "$SCRIPT_DIR/appimagetool"
    fi

    # Build AppImage
    cd "$SCRIPT_DIR"
    ARCH=x86_64 ./appimagetool "$APPDIR" "$BUILD_DIR/${APP_DISPLAY_NAME}-${APP_VERSION}-x86_64.AppImage"

    rm -rf "$APPDIR"
    log_info "Created: $BUILD_DIR/${APP_DISPLAY_NAME}-${APP_VERSION}-x86_64.AppImage"
}

# =============================================================================
# Main
# =============================================================================
main() {
    echo "========================================"
    echo "  SeenSlide Installer Builder v$APP_VERSION"
    echo "========================================"
    echo ""

    # Parse arguments
    BUILD_DEB=true
    BUILD_RPM=false
    BUILD_APPIMAGE=false

    while [[ $# -gt 0 ]]; do
        case $1 in
            --deb)
                BUILD_DEB=true
                shift
                ;;
            --rpm)
                BUILD_RPM=true
                shift
                ;;
            --appimage)
                BUILD_APPIMAGE=true
                shift
                ;;
            --all)
                BUILD_DEB=true
                BUILD_RPM=true
                BUILD_APPIMAGE=true
                shift
                ;;
            --version)
                APP_VERSION="$2"
                shift 2
                ;;
            --help)
                echo "Usage: $0 [OPTIONS]"
                echo ""
                echo "Options:"
                echo "  --deb         Build .deb package (default)"
                echo "  --rpm         Build .rpm package"
                echo "  --appimage    Build AppImage"
                echo "  --all         Build all formats"
                echo "  --version X   Set version number"
                echo "  --help        Show this help"
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done

    check_dependencies
    clean_build
    build_pyinstaller

    if $BUILD_DEB; then
        build_deb
    fi

    if $BUILD_RPM; then
        build_rpm
    fi

    if $BUILD_APPIMAGE; then
        build_appimage
    fi

    echo ""
    log_info "Build complete! Output files:"
    ls -la "$BUILD_DIR/"*.{deb,rpm,AppImage} 2>/dev/null || true
    echo ""
    echo "To install .deb: sudo dpkg -i $BUILD_DIR/${APP_NAME}_${APP_VERSION}_amd64.deb"
    echo "To install .rpm: sudo rpm -i $BUILD_DIR/${APP_NAME}-${APP_VERSION}.x86_64.rpm"
    echo "To run AppImage: chmod +x *.AppImage && ./*.AppImage"
}

main "$@"
