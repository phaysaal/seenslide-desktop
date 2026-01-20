#!/bin/bash
# =============================================================================
# SeenSlide Desktop .deb Builder (Simple version using dpkg-deb)
# =============================================================================

set -e

# Configuration
APP_NAME="seenslide"
APP_VERSION="${VERSION:-1.0.0}"
APP_DESCRIPTION="Slide capture and cloud sync tool for presentations"
APP_MAINTAINER="SeenSlide Team <support@seenslide.com>"
ARCH="amd64"

# Directories
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="$SCRIPT_DIR/build"
DIST_DIR="$SCRIPT_DIR/dist"
DEB_ROOT="$BUILD_DIR/deb-root"

echo "========================================"
echo "  SeenSlide .deb Builder v$APP_VERSION"
echo "========================================"

# Clean previous build
echo "[INFO] Cleaning previous build..."
rm -rf "$BUILD_DIR" "$DIST_DIR"
mkdir -p "$BUILD_DIR" "$DIST_DIR" "$DEB_ROOT"

# Activate virtual environment
echo "[INFO] Activating virtual environment..."
cd "$PROJECT_DIR"
source venv/bin/activate

# Check PyInstaller
if ! command -v pyinstaller &> /dev/null; then
    echo "[INFO] Installing PyInstaller..."
    pip install pyinstaller
fi

# Build with PyInstaller
echo "[INFO] Building with PyInstaller..."
cd "$PROJECT_DIR"
pyinstaller --clean --noconfirm \
    --name seenslide \
    --onedir \
    --noconsole \
    --add-data "$PROJECT_DIR/config:config" \
    --add-data "$PROJECT_DIR/gui:gui" \
    --hidden-import customtkinter \
    --hidden-import PIL \
    --hidden-import PIL.Image \
    --hidden-import imagehash \
    --hidden-import mss \
    --hidden-import mss.linux \
    --hidden-import requests \
    --hidden-import qrcode \
    --hidden-import yaml \
    --hidden-import dotenv \
    --hidden-import bcrypt \
    --distpath "$BUILD_DIR/pyinstaller" \
    --workpath "$BUILD_DIR/work" \
    --specpath "$BUILD_DIR" \
    "$PROJECT_DIR/gui/main.py"

echo "[INFO] PyInstaller build complete"

# Create .deb directory structure
echo "[INFO] Creating .deb structure..."
mkdir -p "$DEB_ROOT/opt/seenslide"
mkdir -p "$DEB_ROOT/usr/bin"
mkdir -p "$DEB_ROOT/usr/share/applications"
mkdir -p "$DEB_ROOT/usr/share/icons/hicolor/256x256/apps"
mkdir -p "$DEB_ROOT/DEBIAN"

# Copy application files
cp -r "$BUILD_DIR/pyinstaller/seenslide/"* "$DEB_ROOT/opt/seenslide/"

# Create symlink
ln -sf /opt/seenslide/seenslide "$DEB_ROOT/usr/bin/seenslide"

# Create desktop entry
cat > "$DEB_ROOT/usr/share/applications/seenslide.desktop" << EOF
[Desktop Entry]
Name=SeenSlide
Comment=$APP_DESCRIPTION
Exec=/opt/seenslide/seenslide
Icon=seenslide
Terminal=false
Type=Application
Categories=Utility;Office;
Keywords=presentation;slides;capture;screen;
StartupNotify=true
EOF

# Create simple icon (green square with S)
if command -v convert &> /dev/null; then
    convert -size 256x256 xc:'#10b981' -gravity center \
        -fill white -font DejaVu-Sans-Bold -pointsize 120 \
        -annotate 0 'S' \
        "$DEB_ROOT/usr/share/icons/hicolor/256x256/apps/seenslide.png" 2>/dev/null || true
fi

# Create control file
cat > "$DEB_ROOT/DEBIAN/control" << EOF
Package: $APP_NAME
Version: $APP_VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Depends: libxcb-xinerama0, libxcb-cursor0, libgl1
Maintainer: $APP_MAINTAINER
Description: $APP_DESCRIPTION
 SeenSlide captures presentation slides in real-time and syncs
 them to the cloud for collaborative viewing and annotation.
EOF

# Create postinst script
cat > "$DEB_ROOT/DEBIAN/postinst" << 'EOF'
#!/bin/bash
# Update icon cache
gtk-update-icon-cache -f /usr/share/icons/hicolor 2>/dev/null || true
# Update desktop database
update-desktop-database /usr/share/applications 2>/dev/null || true
EOF
chmod 755 "$DEB_ROOT/DEBIAN/postinst"

# Set permissions
chmod -R 755 "$DEB_ROOT/opt"
chmod 644 "$DEB_ROOT/usr/share/applications/seenslide.desktop"

# Build .deb
echo "[INFO] Building .deb package..."
dpkg-deb --build "$DEB_ROOT" "$DIST_DIR/${APP_NAME}_${APP_VERSION}_${ARCH}.deb"

echo ""
echo "========================================"
echo "[SUCCESS] Build complete!"
echo "========================================"
echo ""
echo "Output: $DIST_DIR/${APP_NAME}_${APP_VERSION}_${ARCH}.deb"
echo ""
echo "To install: sudo dpkg -i $DIST_DIR/${APP_NAME}_${APP_VERSION}_${ARCH}.deb"
echo "To fix dependencies: sudo apt-get install -f"
echo ""
ls -lh "$DIST_DIR/"*.deb
