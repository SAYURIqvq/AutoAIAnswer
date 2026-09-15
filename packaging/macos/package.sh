#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."

pyinstaller --noconfirm --clean --windowed --name QQMusic \
  --osx-bundle-identifier com.sayuriqvq.QQMusic \
  --icon assets/app.icns \
  --add-data "ai_screenshot_assistant/web/static:ai_screenshot_assistant/web/static" \
  --add-data "assets:assets" \
  --hidden-import ai_screenshot_assistant.ui.macos_capture \
  --hidden-import ai_screenshot_assistant.ui.native_capture \
  --hidden-import ai_screenshot_assistant.ui.streaming_overlay \
  --exclude-module IPython \
  --exclude-module pytest \
  --exclude-module matplotlib \
  --exclude-module pandas \
  --exclude-module pyarrow \
  --exclude-module scipy \
  --exclude-module sklearn \
  --exclude-module torch \
  --exclude-module torchvision \
  --exclude-module torchaudio \
  --exclude-module transformers \
  --exclude-module datasets \
  --exclude-module gradio \
  --exclude-module cv2 \
  --exclude-module tkinter \
  main.py

python packaging/macos/patch_info_plist.py dist/QQMusic.app
codesign --force --deep --sign - dist/QQMusic.app

mkdir -p dist/dmg
rm -rf dist/dmg/QQMusic.app
cp -R dist/QQMusic.app dist/dmg/
rm -f dist/QQMusic-macOS.dmg
hdiutil create -volname QQMusic -srcfolder dist/dmg -ov -format UDZO dist/QQMusic-macOS.dmg
echo "Built: dist/QQMusic.app and dist/QQMusic-macOS.dmg"
