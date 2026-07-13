#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

APP_NAME="OmniLit"
ENTRY_FILE="omnilit_qt_app.py"
RELEASE_HELPER="sync_release_metadata.py"
DEFAULT_KEY_FILE="Workspace/Translate/APIKey.enc"
LEGACY_KEY_FILE="Translate/APIKey.enc"
PACKAGED_KEY_FILE=""
KEY_ENCRYPT_HELPER="encrypt_default_key.py"
ICON_SOURCE="assets/omnilit_logo.png"
ICON_ICNS="assets/omnilit_logo.icns"
RELEASE_DIR="release/macos"

MODE="${1:-}"
SKIP_KEY=""
REFRESH_KEY=""

case "$MODE" in
  --skip-key|--no-key|--build-only) SKIP_KEY="1" ;;
  --refresh-key) REFRESH_KEY="1" ;;
  --help|-h)
    cat <<USAGE
Usage:
  ./build_omnilit_macos.sh                 Build OmniLit.app for macOS.
  ./build_omnilit_macos.sh --refresh-key   Recreate encrypted default key, then build.
  ./build_omnilit_macos.sh --encrypt-default-key   Only create encrypted default key.
  ./build_omnilit_macos.sh --skip-key      Build without packaging Workspace/Translate/APIKey.enc.

Optional:
  OMNILIT_MAC_ARCH=universal2 ./build_omnilit_macos.sh
USAGE
    exit 0
    ;;
esac

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "ERROR: macOS builds must be run on macOS. PyInstaller cannot cross-build a .app from Windows."
  exit 1
fi

dependency_error() {
  echo "ERROR: The OmniLit Conda environment is missing a required dependency."
  echo "Run: conda env update -n OmniLit -f environment.yml --prune"
  exit 1
}

echo "[1/8] Checking OmniLit Conda environment..."
if [[ "${CONDA_DEFAULT_ENV:-}" != "OmniLit" || -z "${CONDA_PREFIX:-}" ]]; then
  echo "ERROR: Activate the OmniLit Conda environment before building."
  echo "Run: conda activate OmniLit"
  exit 1
fi
PYTHON_CMD="$CONDA_PREFIX/bin/python"
if [[ ! -x "$PYTHON_CMD" ]]; then
  echo "ERROR: Conda environment Python was not found: $PYTHON_CMD"
  exit 1
fi
"$PYTHON_CMD" -c "import sys; print('Python', sys.version.split()[0])"

echo "[2/8] Checking pip and PyInstaller..."
"$PYTHON_CMD" -m pip --version >/dev/null 2>&1 || dependency_error
"$PYTHON_CMD" -m PyInstaller --version >/dev/null 2>&1 || dependency_error

echo "[3/8] Checking runtime dependencies..."
"$PYTHON_CMD" -c "import PySide6, requests, fitz, openai, reportlab, rapidocr, onnxruntime, tqdm; import PySide6.QtWebChannel, PySide6.QtWebEngineCore, PySide6.QtWebEngineQuick; from cryptography.fernet import Fernet" >/dev/null 2>&1 || dependency_error

echo "[4/8] Syncing version metadata..."
APP_VERSION="$("$PYTHON_CMD" "$RELEASE_HELPER" prebuild)"
echo "Release version: $APP_VERSION"

command -v npm >/dev/null 2>&1 || { echo "ERROR: npm was not found on PATH."; exit 1; }
npm run web:build

echo "[5/8] Preparing encrypted default DeepSeek API Key..."
if [[ "$MODE" == "--encrypt-default-key" ]]; then
  "$PYTHON_CMD" "$KEY_ENCRYPT_HELPER" --output "$DEFAULT_KEY_FILE"
  echo "Encrypted key saved to: $DEFAULT_KEY_FILE"
  exit 0
fi

if [[ -z "$SKIP_KEY" ]]; then
  if [[ -n "$REFRESH_KEY" ]]; then
    "$PYTHON_CMD" "$KEY_ENCRYPT_HELPER" --output "$DEFAULT_KEY_FILE"
    PACKAGED_KEY_FILE="$DEFAULT_KEY_FILE"
  elif [[ -f "$DEFAULT_KEY_FILE" ]]; then
    PACKAGED_KEY_FILE="$DEFAULT_KEY_FILE"
    echo "Found encrypted default key: $DEFAULT_KEY_FILE"
  elif [[ -f "$LEGACY_KEY_FILE" ]]; then
    PACKAGED_KEY_FILE="$LEGACY_KEY_FILE"
    echo "Found legacy encrypted default key: $LEGACY_KEY_FILE"
    echo "New deployment keys should be saved to $DEFAULT_KEY_FILE."
  else
    "$PYTHON_CMD" "$KEY_ENCRYPT_HELPER" --output "$DEFAULT_KEY_FILE"
    PACKAGED_KEY_FILE="$DEFAULT_KEY_FILE"
  fi
fi

echo "[6/8] Cleaning old build artifacts..."
rm -rf build dist "$APP_NAME.spec" "$RELEASE_DIR"
mkdir -p "$RELEASE_DIR"

if [[ ! -f "$ICON_ICNS" && -f "$ICON_SOURCE" ]] && command -v sips >/dev/null 2>&1 && command -v iconutil >/dev/null 2>&1; then
  ICONSET="build/${APP_NAME}.iconset"
  mkdir -p "$ICONSET"
  for size in 16 32 128 256 512; do
    sips -z "$size" "$size" "$ICON_SOURCE" --out "$ICONSET/icon_${size}x${size}.png" >/dev/null
    double_size=$((size * 2))
    sips -z "$double_size" "$double_size" "$ICON_SOURCE" --out "$ICONSET/icon_${size}x${size}@2x.png" >/dev/null
  done
  iconutil -c icns "$ICONSET" -o "$ICON_ICNS"
fi

echo "[7/8] Building macOS app bundle..."
PYINSTALLER_ARGS=(
  --noconfirm
  --clean
  --windowed
  --name "$APP_NAME"
  --hidden-import requests
  --hidden-import urllib3
  --hidden-import fitz
  --collect-all rapidocr
  --collect-all onnxruntime
  --hidden-import openai
  --hidden-import reportlab
  --hidden-import reportlab.pdfgen
  --hidden-import reportlab.pdfgen.canvas
  --hidden-import reportlab.pdfbase
  --hidden-import reportlab.pdfbase.pdfmetrics
  --hidden-import reportlab.pdfbase.cidfonts
  --hidden-import reportlab.pdfbase.ttfonts
  --hidden-import reportlab.lib.utils
  --collect-submodules reportlab
  --collect-data reportlab
  --hidden-import tqdm
  --hidden-import cryptography
  --hidden-import cryptography.fernet
  --hidden-import cryptography.hazmat
  --hidden-import cryptography.hazmat.primitives
  --hidden-import cryptography.hazmat.primitives.hashes
  --hidden-import cryptography.hazmat.primitives.kdf.pbkdf2
  --hidden-import cryptography.hazmat.bindings._rust
  --collect-submodules cryptography
  --collect-data cryptography
  --collect-binaries cryptography
  --hidden-import PySide6.QtCore
  --hidden-import PySide6.QtGui
  --hidden-import PySide6.QtQml
  --hidden-import PySide6.QtQuick
  --hidden-import PySide6.QtWidgets
  --hidden-import PySide6.QtWebChannel
  --hidden-import PySide6.QtWebEngineCore
  --hidden-import PySide6.QtWebEngineQuick
  --hidden-import Download.literature_download_core
  --hidden-import Translate.literature_translate_core
  --hidden-import Update.update_core
  --add-data "assets/omnilit_logo.png:assets"
  --add-data "assets/omnilit_logo_164.png:assets"
  --add-data "assets/omnilit_logo.ico:assets"
  --add-data "ui/qml:ui/qml"
  --add-data "apps/web/dist:apps/web/dist"
  --add-data "update_manifest.json:."
  --add-data "Download/__init__.py:Download"
  --add-data "Download/literature_download_core.py:Download"
  --add-data "Download/journal_metrics.py:Download"
  --add-data "Update/__init__.py:Update"
  --add-data "Update/update_core.py:Update"
  --add-data "Translate/__init__.py:Translate"
  --add-data "Translate/literature_translate_core.py:Translate"
  --add-data "Translate/glossary:Translate/glossary"
)

if [[ -f "$ICON_ICNS" ]]; then
  PYINSTALLER_ARGS+=(--icon "$ICON_ICNS")
fi
if [[ -n "${OMNILIT_MAC_ARCH:-}" ]]; then
  PYINSTALLER_ARGS+=(--target-architecture "$OMNILIT_MAC_ARCH")
fi
if [[ -z "$SKIP_KEY" && -n "$PACKAGED_KEY_FILE" ]]; then
  PYINSTALLER_ARGS+=(--add-data "$PACKAGED_KEY_FILE:Translate")
fi

"$PYTHON_CMD" -m PyInstaller "${PYINSTALLER_ARGS[@]}" "$ENTRY_FILE"

APP_BUNDLE="dist/${APP_NAME}.app"
if [[ ! -d "$APP_BUNDLE" ]]; then
  echo "ERROR: expected app bundle was not created: $APP_BUNDLE"
  exit 1
fi

if [[ -n "${OMNILIT_MAC_SIGNING_IDENTITY:-}" ]]; then
  codesign --force --deep --options runtime --timestamp --sign "$OMNILIT_MAC_SIGNING_IDENTITY" "$APP_BUNDLE"
  codesign --verify --deep --strict --verbose=2 "$APP_BUNDLE"
  spctl --assess --type execute --verbose=2 "$APP_BUNDLE"
else
  if [[ "${OMNILIT_FORMAL_RELEASE:-0}" == "1" ]]; then
    echo "ERROR: Formal releases require OMNILIT_MAC_SIGNING_IDENTITY."
    exit 1
  fi
  echo "WARNING: Built an unsigned macOS development artifact."
fi

if [[ -n "${OMNILIT_MAC_NOTARY_PROFILE:-}" ]]; then
  if [[ -z "${OMNILIT_MAC_SIGNING_IDENTITY:-}" ]]; then
    echo "ERROR: Notarization requires a signed app bundle."
    exit 1
  fi
  NOTARY_ZIP="${RELEASE_DIR}/${APP_NAME}-notary-submission.zip"
  mkdir -p "$RELEASE_DIR"
  ditto -c -k --keepParent "$APP_BUNDLE" "$NOTARY_ZIP"
  xcrun notarytool submit "$NOTARY_ZIP" --keychain-profile "$OMNILIT_MAC_NOTARY_PROFILE" --wait
  rm -f "$NOTARY_ZIP"
  xcrun stapler staple "$APP_BUNDLE"
  xcrun stapler validate "$APP_BUNDLE"
elif [[ "${OMNILIT_FORMAL_RELEASE:-0}" == "1" ]]; then
  echo "ERROR: Formal releases require OMNILIT_MAC_NOTARY_PROFILE."
  exit 1
fi

echo "[8/8] Packaging zip release..."
ZIP_PATH="${RELEASE_DIR}/${APP_NAME}-macOS-${APP_VERSION}.zip"
ditto -c -k --keepParent "$APP_BUNDLE" "$ZIP_PATH"
shasum -a 256 "$ZIP_PATH" | tee "${ZIP_PATH}.sha256"

echo "Done: $APP_BUNDLE"
echo "Release archive: $ZIP_PATH"
if [[ "${OMNILIT_FORMAL_RELEASE:-0}" != "1" ]]; then
  echo "Note: this development artifact is not a signed and notarized formal release."
fi
