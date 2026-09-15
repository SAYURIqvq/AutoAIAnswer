#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! "$PYTHON_BIN" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"; then
  echo "Need Python 3.11 or newer. Set PYTHON_BIN to a suitable interpreter." >&2
  exit 1
fi

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This package must be built on a Mac." >&2
  exit 1
fi

if [[ ! -d .venv ]]; then
  "$PYTHON_BIN" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install -r requirements.txt

ICON_ARGS=()
if [[ -f assets/app.icns ]]; then
  ICON_ARGS=(--icon assets/app.icns)
fi

pyinstaller --noconfirm --clean --windowed --name QQMusicOverlay \
  --osx-bundle-identifier com.sayuriqvq.QQMusicOverlay \
  "${ICON_ARGS[@]}" \
  --add-data "assets:assets" \
  --hidden-import macos_capture \
  --hidden-import overlay \
  --exclude-module IPython \
  --exclude-module pytest \
  --exclude-module tkinter \
  main.py

python patch_info_plist.py dist/QQMusicOverlay.app
codesign --force --deep --sign - dist/QQMusicOverlay.app

mkdir -p dist/dmg
rm -rf dist/dmg/QQMusicOverlay.app
cp -R dist/QQMusicOverlay.app dist/dmg/
ln -sf /Applications dist/dmg/Applications
rm -f dist/QQMusicOverlay-macOS.dmg
hdiutil create -volname QQMusicOverlay -srcfolder dist/dmg -ov -format UDZO dist/QQMusicOverlay-macOS.dmg
echo "Built: dist/QQMusicOverlay.app and dist/QQMusicOverlay-macOS.dmg"
