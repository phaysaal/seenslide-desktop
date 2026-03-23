#!/bin/bash
# =============================================================================
# SeenSlide Release Script
#
# Usage:
#   ./release.sh            # Auto-increment patch: v1.0.3 → v1.0.4
#   ./release.sh 1.2.0      # Explicit version: v1.2.0
#   ./release.sh --dry-run   # Show what would happen without doing it
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${GREEN}[release]${NC} $1"; }
warn() { echo -e "${YELLOW}[release]${NC} $1"; }
fail() { echo -e "${RED}[release]${NC} $1"; exit 1; }

DRY_RUN=false
VERSION=""

# Parse args
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
        --help|-h)
            echo "Usage: $0 [VERSION] [--dry-run]"
            echo ""
            echo "  VERSION    Explicit version (e.g., 1.2.0). Omit to auto-increment patch."
            echo "  --dry-run  Show what would happen without making changes."
            echo ""
            echo "Examples:"
            echo "  $0            # v1.0.3 → v1.0.4"
            echo "  $0 2.0.0      # → v2.0.0"
            echo "  $0 --dry-run  # preview only"
            exit 0
            ;;
        *) VERSION="$arg" ;;
    esac
done

# ── Determine version ──────────────────────────────────────────────

# Get latest tag
LATEST_TAG=$(git tag --sort=-v:refname | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | head -1)
LATEST_VERSION="${LATEST_TAG#v}"

if [ -z "$LATEST_VERSION" ]; then
    # No tags yet — read from __init__.py
    LATEST_VERSION=$(grep -oP '__version__\s*=\s*"\K[^"]+' seenslide/__init__.py)
    LATEST_VERSION="${LATEST_VERSION:-0.0.0}"
fi

if [ -z "$VERSION" ]; then
    # Auto-increment patch
    IFS='.' read -r MAJOR MINOR PATCH <<< "$LATEST_VERSION"
    PATCH=$((PATCH + 1))
    VERSION="${MAJOR}.${MINOR}.${PATCH}"
    log "Auto-incremented: ${LATEST_VERSION} → ${VERSION}"
else
    # Strip leading 'v' if user passed it
    VERSION="${VERSION#v}"
    log "Explicit version: ${VERSION}"
fi

TAG="v${VERSION}"

# Validate format
if ! echo "$VERSION" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+$'; then
    fail "Invalid version format: ${VERSION} (expected X.Y.Z)"
fi

# Check tag doesn't already exist
if git rev-parse "$TAG" >/dev/null 2>&1; then
    fail "Tag ${TAG} already exists. Choose a different version."
fi

log "Current: v${LATEST_VERSION}"
log "New:     ${TAG}"

# ── Dry run stop ───────────────────────────────────────────────────

if $DRY_RUN; then
    echo ""
    warn "Dry run — the following would happen:"
    echo "  1. Update seenslide/__init__.py → __version__ = \"${VERSION}\""
    echo "  2. git add + commit \"Release ${TAG}\""
    echo "  3. git tag ${TAG}"
    echo "  4. git push origin main --tags"
    echo "  5. GitHub Actions builds all platform installers and creates a Release:"
    echo "       Linux:   .deb (Debian/Ubuntu) + .rpm (Fedora/RHEL) + .AppImage (universal)"
    echo "       macOS:   .dmg"
    echo "       Windows: .exe installer"
    echo ""
    echo "  After the release, update Railway env vars:"
    echo "    SEENSLIDE_DESKTOP_VERSION=${VERSION}"
    echo "    SEENSLIDE_DESKTOP_URL_LINUX=https://github.com/phaysaal/seenslide-desktop/releases/download/${TAG}/seenslide_${VERSION}_amd64.deb"
    echo "    SEENSLIDE_DESKTOP_URL_DARWIN=https://github.com/phaysaal/seenslide-desktop/releases/download/${TAG}/SeenSlide-${VERSION}-macOS.dmg"
    echo "    SEENSLIDE_DESKTOP_URL_WINDOWS=https://github.com/phaysaal/seenslide-desktop/releases/download/${TAG}/SeenSlide-${VERSION}-Setup.exe"
    echo ""
    echo "  Optional (auto-generated from version, only set to override):"
    echo "    SEENSLIDE_DL_APPIMAGE=SeenSlide-${VERSION}-x86_64.AppImage"
    echo "    SEENSLIDE_DL_RPM=seenslide-${VERSION}.x86_64.rpm"
    exit 0
fi

# ── Update version in source ──────────────────────────────────────

log "Updating seenslide/__init__.py..."
sed -i "s/^__version__ = \".*\"/__version__ = \"${VERSION}\"/" seenslide/__init__.py

# Verify it worked
NEW_VER=$(grep -oP '__version__\s*=\s*"\K[^"]+' seenslide/__init__.py)
if [ "$NEW_VER" != "$VERSION" ]; then
    fail "Failed to update __init__.py (got: ${NEW_VER})"
fi

# ── Commit, tag, push ─────────────────────────────────────────────

log "Committing..."
git add seenslide/__init__.py
git commit -m "Release ${TAG}"

log "Tagging ${TAG}..."
git tag -a "$TAG" -m "Release ${TAG}"

log "Pushing to origin..."
git push origin main --tags

# ── Done ──────────────────────────────────────────────────────────

echo ""
log "Release ${TAG} pushed!"
echo ""
echo "  GitHub Actions will now build installers for all platforms:"
echo ""
echo "    Linux:   .deb (Debian/Ubuntu)  .rpm (Fedora/RHEL)  .AppImage (universal)"
echo "    macOS:   .dmg"
echo "    Windows: .exe installer (Inno Setup) or .zip"
echo ""
echo "  Track progress: https://github.com/phaysaal/seenslide-desktop/actions"
echo "  Release page:   https://github.com/phaysaal/seenslide-desktop/releases/tag/${TAG}"
echo ""
echo "  Once built, update Railway env vars:"
echo "    SEENSLIDE_DESKTOP_VERSION=${VERSION}"
echo "    SEENSLIDE_DESKTOP_URL_LINUX=https://github.com/phaysaal/seenslide-desktop/releases/download/${TAG}/seenslide_${VERSION}_amd64.deb"
echo "    SEENSLIDE_DESKTOP_URL_DARWIN=https://github.com/phaysaal/seenslide-desktop/releases/download/${TAG}/SeenSlide-${VERSION}-macOS.dmg"
echo "    SEENSLIDE_DESKTOP_URL_WINDOWS=https://github.com/phaysaal/seenslide-desktop/releases/download/${TAG}/SeenSlide-${VERSION}-Setup.exe"
echo ""
echo "  Optional (auto-generated from version, only set to override):"
echo "    SEENSLIDE_DL_APPIMAGE=SeenSlide-${VERSION}-x86_64.AppImage"
echo "    SEENSLIDE_DL_RPM=seenslide-${VERSION}.x86_64.rpm"
