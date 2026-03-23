#!/bin/bash
# =============================================================================
# SeenSlide Desktop - macOS Build Script
# Creates a .app bundle and optional .dmg installer
#
# Usage:
#   ./build_macos.sh                   # Build .app only
#   ./build_macos.sh --dmg             # Build .app + .dmg
#   ./build_macos.sh --version 1.0.3   # Override version
# =============================================================================

set -e

APP_NAME="SeenSlide"
APP_VERSION="${VERSION:-1.0.3}"
BUNDLE_ID="com.seenslide.desktop"
APP_CATEGORY="public.app-category.productivity"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="$SCRIPT_DIR/dist/macos"
ICON_SRC="$PROJECT_DIR/gui/resources/icons/logo.png"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# =============================================================================
# Parse arguments
# =============================================================================
CREATE_DMG=false
while [[ $# -gt 0 ]]; do
    case $1 in
        --dmg)      CREATE_DMG=true; shift ;;
        --version)  APP_VERSION="$2"; shift 2 ;;
        *)          log_error "Unknown option: $1"; exit 1 ;;
    esac
done

echo "========================================"
echo "  $APP_NAME macOS Build v$APP_VERSION"
echo "========================================"
echo ""

# =============================================================================
# Platform check
# =============================================================================
if [[ "$(uname)" != "Darwin" ]]; then
    log_error "This script must be run on macOS."
    exit 1
fi

# =============================================================================
# Dependencies
# =============================================================================
log_info "Checking dependencies..."

if ! command -v python3 &> /dev/null; then
    log_error "Python 3 not found. Install via: brew install python@3.12"
    exit 1
fi

# Activate project venv if present
if [ -f "$PROJECT_DIR/venv/bin/activate" ]; then
    source "$PROJECT_DIR/venv/bin/activate"
elif [ -f "$PROJECT_DIR/.venv/bin/activate" ]; then
    source "$PROJECT_DIR/.venv/bin/activate"
else
    log_warn "No project venv found — using system Python"
fi

# Ensure PyInstaller
if ! python3 -c "import PyInstaller" 2>/dev/null; then
    log_info "Installing PyInstaller..."
    python3 -m pip install pyinstaller
fi

# Ensure project deps
log_info "Installing project dependencies..."
python3 -m pip install -r "$PROJECT_DIR/requirements.txt" -q

# =============================================================================
# Create .icns icon from logo.png
# =============================================================================
create_icns() {
    local ICONSET_DIR="$BUILD_DIR/SeenSlide.iconset"
    local ICNS_PATH="$BUILD_DIR/SeenSlide.icns"

    if [ ! -f "$ICON_SRC" ]; then
        log_warn "No logo.png found — skipping icon"
        echo ""
        return
    fi

    log_info "Creating .icns from logo.png..."
    mkdir -p "$ICONSET_DIR"

    # Generate all required sizes
    for sz in 16 32 64 128 256 512; do
        sips -z $sz $sz "$ICON_SRC" --out "$ICONSET_DIR/icon_${sz}x${sz}.png" &>/dev/null
        # @2x retina variants (half the name, double the pixels)
        local half=$((sz / 2))
        if [ $half -ge 16 ]; then
            cp "$ICONSET_DIR/icon_${sz}x${sz}.png" "$ICONSET_DIR/icon_${half}x${half}@2x.png"
        fi
    done

    iconutil -c icns "$ICONSET_DIR" -o "$ICNS_PATH" 2>/dev/null || true
    rm -rf "$ICONSET_DIR"

    if [ -f "$ICNS_PATH" ]; then
        log_info "Icon created: $ICNS_PATH"
        echo "$ICNS_PATH"
    else
        log_warn "iconutil failed — building without custom icon"
        echo ""
    fi
}

# =============================================================================
# Clean & prep
# =============================================================================
log_info "Cleaning previous build..."
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

ICNS_PATH=$(create_icns)

# =============================================================================
# PyInstaller build
# =============================================================================
log_info "Building with PyInstaller..."
cd "$PROJECT_DIR"

ICON_FLAG=""
if [ -n "$ICNS_PATH" ] && [ -f "$ICNS_PATH" ]; then
    ICON_FLAG="--icon=$ICNS_PATH"
fi

python3 -m PyInstaller --noconfirm --clean \
    --name "$APP_NAME" \
    --windowed \
    --osx-bundle-identifier "$BUNDLE_ID" \
    $ICON_FLAG \
    --add-data "config:config" \
    --add-data "gui:gui" \
    --add-data "core:core" \
    --add-data "modules:modules" \
    --add-data "seenslide:seenslide" \
    --hidden-import PyQt5 \
    --hidden-import PyQt5.QtCore \
    --hidden-import PyQt5.QtGui \
    --hidden-import PyQt5.QtWidgets \
    --hidden-import PIL \
    --hidden-import PIL.Image \
    --hidden-import imagehash \
    --hidden-import mss \
    --hidden-import mss.darwin \
    --hidden-import fastapi \
    --hidden-import uvicorn \
    --hidden-import pydantic \
    --hidden-import requests \
    --hidden-import yaml \
    --hidden-import bcrypt \
    --hidden-import jwt \
    --hidden-import keyring \
    --hidden-import sounddevice \
    --hidden-import soundfile \
    --hidden-import fitz \
    --hidden-import cv2 \
    --distpath "$BUILD_DIR" \
    gui/main.py

# Clean up build artifacts from project root
rm -rf "$PROJECT_DIR/build" "$PROJECT_DIR/$APP_NAME.spec"

if [ ! -d "$BUILD_DIR/$APP_NAME.app" ]; then
    log_error "Build failed — .app bundle not created."
    exit 1
fi

# =============================================================================
# Patch Info.plist with version and metadata
# =============================================================================
PLIST="$BUILD_DIR/$APP_NAME.app/Contents/Info.plist"
if [ -f "$PLIST" ]; then
    log_info "Patching Info.plist..."
    /usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $APP_VERSION" "$PLIST" 2>/dev/null || \
        /usr/libexec/PlistBuddy -c "Add :CFBundleShortVersionString string $APP_VERSION" "$PLIST"
    /usr/libexec/PlistBuddy -c "Set :CFBundleVersion $APP_VERSION" "$PLIST" 2>/dev/null || \
        /usr/libexec/PlistBuddy -c "Add :CFBundleVersion string $APP_VERSION" "$PLIST"
    /usr/libexec/PlistBuddy -c "Set :LSApplicationCategoryType $APP_CATEGORY" "$PLIST" 2>/dev/null || \
        /usr/libexec/PlistBuddy -c "Add :LSApplicationCategoryType string $APP_CATEGORY" "$PLIST"
    /usr/libexec/PlistBuddy -c "Set :NSHighResolutionCapable true" "$PLIST" 2>/dev/null || \
        /usr/libexec/PlistBuddy -c "Add :NSHighResolutionCapable bool true" "$PLIST"
    # Screen recording permission prompt (needed for mss capture)
    /usr/libexec/PlistBuddy -c "Set :NSScreenCaptureDescription 'SeenSlide needs screen access to capture presentation slides.'" "$PLIST" 2>/dev/null || \
        /usr/libexec/PlistBuddy -c "Add :NSScreenCaptureDescription string 'SeenSlide needs screen access to capture presentation slides.'" "$PLIST"
fi

log_info ".app bundle ready: $BUILD_DIR/$APP_NAME.app"

# =============================================================================
# Optional: code signing
# =============================================================================
if [ -n "$CODESIGN_IDENTITY" ]; then
    log_info "Signing with identity: $CODESIGN_IDENTITY"
    codesign --force --deep --sign "$CODESIGN_IDENTITY" \
        --options runtime \
        --entitlements "$SCRIPT_DIR/entitlements.plist" \
        "$BUILD_DIR/$APP_NAME.app" 2>/dev/null || log_warn "Code signing failed — continuing unsigned"
else
    log_warn "No CODESIGN_IDENTITY set — skipping code signing"
    log_warn "  To sign: CODESIGN_IDENTITY='Developer ID Application: ...' $0"
fi

# =============================================================================
# Optional: create .dmg
# =============================================================================
if $CREATE_DMG; then
    log_info "Creating .dmg installer..."

    DMG_NAME="${APP_NAME}-${APP_VERSION}-macOS.dmg"
    DMG_PATH="$BUILD_DIR/$DMG_NAME"

    if command -v create-dmg &> /dev/null; then
        create-dmg \
            --volname "$APP_NAME $APP_VERSION" \
            --volicon "$ICNS_PATH" \
            --window-pos 200 120 \
            --window-size 600 400 \
            --icon-size 100 \
            --icon "$APP_NAME.app" 150 190 \
            --app-drop-link 450 190 \
            --hide-extension "$APP_NAME.app" \
            "$DMG_PATH" \
            "$BUILD_DIR/$APP_NAME.app" || true
    else
        log_warn "create-dmg not found — using hdiutil (brew install create-dmg for prettier DMG)"
        hdiutil create -volname "$APP_NAME" \
            -srcfolder "$BUILD_DIR/$APP_NAME.app" \
            -ov -format UDZO "$DMG_PATH"
    fi

    if [ -f "$DMG_PATH" ]; then
        log_info "DMG created: $DMG_PATH ($(du -h "$DMG_PATH" | cut -f1))"
    else
        log_warn "DMG creation failed"
    fi
fi

# =============================================================================
# Summary
# =============================================================================
echo ""
log_info "macOS build complete!"
echo "  .app bundle : $BUILD_DIR/$APP_NAME.app"
if [ -f "$BUILD_DIR/${APP_NAME}-${APP_VERSION}-macOS.dmg" ]; then
    echo "  .dmg installer: $BUILD_DIR/${APP_NAME}-${APP_VERSION}-macOS.dmg"
fi
echo ""
echo "To run:          open $BUILD_DIR/$APP_NAME.app"
echo "To create DMG:   $0 --dmg"
echo "To code sign:    CODESIGN_IDENTITY='Your ID' $0"
