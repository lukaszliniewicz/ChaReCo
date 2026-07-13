#!/usr/bin/env bash
# Build a portable x86_64 AppImage from a Linux checkout.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${1:-python3}"
ARCH="$(uname -m)"

if [[ "$ARCH" != "x86_64" ]]; then
  echo "Only x86_64 AppImages are currently supported (found: $ARCH)." >&2
  exit 1
fi

VERSION="$($PYTHON -c "import sys; sys.path.insert(0, '$ROOT_DIR'); from chareco import __version__; print(__version__)")"
BUILD_DIR="$ROOT_DIR/build/appimage"
DIST_DIR="$ROOT_DIR/dist"
APPDIR="$BUILD_DIR/ChaReCo.AppDir"
PYINSTALLER_WORK="$BUILD_DIR/pyinstaller"
APPIMAGETOOL="${APPIMAGETOOL:-$BUILD_DIR/appimagetool-x86_64.AppImage}"
OUTPUT="$DIST_DIR/ChaReCo-${VERSION}-x86_64.AppImage"

rm -rf "$APPDIR" "$PYINSTALLER_WORK"
mkdir -p "$APPDIR/usr/lib" "$APPDIR/usr/share/icons/hicolor/scalable/apps" "$DIST_DIR"

"$PYTHON" -m PyInstaller \
  --noconfirm --clean --onedir --windowed --name ChaReCo \
  --hidden-import jupytext --collect-data tiktoken \
  --distpath "$BUILD_DIR/dist" --workpath "$PYINSTALLER_WORK" \
  --specpath "$BUILD_DIR/spec" "$ROOT_DIR/run.py"

cp -a "$BUILD_DIR/dist/ChaReCo" "$APPDIR/usr/lib/ChaReCo"
cp "$ROOT_DIR/packaging/chareco.svg" "$APPDIR/chareco.svg"
cp "$ROOT_DIR/packaging/chareco.svg" "$APPDIR/usr/share/icons/hicolor/scalable/apps/chareco.svg"

cat > "$APPDIR/ChaReCo.desktop" <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=ChaReCo
Comment=Create repository context for LLM chats
Exec=ChaReCo
Icon=chareco
Categories=Development;Utility;
Terminal=false
DESKTOP

cat > "$APPDIR/AppRun" <<'APPRUN'
#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$HERE/usr/lib/ChaReCo/ChaReCo" "$@"
APPRUN
chmod +x "$APPDIR/AppRun"

if [[ ! -x "$APPIMAGETOOL" ]]; then
  curl --fail --location --retry 3 \
    --output "$APPIMAGETOOL" \
    "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
  chmod +x "$APPIMAGETOOL"
fi

ARCH=x86_64 "$APPIMAGETOOL" --appimage-extract-and-run "$APPDIR" "$OUTPUT"
echo "Created $OUTPUT"
