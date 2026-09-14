#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."

pyinstaller --noconfirm --clean --windowed --name QQ音乐 \
  --osx-bundle-identifier com.sayuriqvq.QQ音乐 \
  --icon assets/app.icns \
  --add-data "ai_screenshot_assistant/web/static:ai_screenshot_assistant/web/static" \
  --add-data "assets:assets" \
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

python packaging/macos/patch_info_plist.py dist/QQ音乐.app
codesign --force --deep --sign - dist/QQ音乐.app

mkdir -p dist/dmg
rm -rf dist/dmg/QQ音乐.app
cp -R dist/QQ音乐.app dist/dmg/
rm -f dist/QQ音乐-macOS.dmg
hdiutil create -volname QQ音乐 -srcfolder dist/dmg -ov -format UDZO dist/QQ音乐-macOS.dmg
echo "Built: dist/QQ音乐.app and dist/QQ音乐-macOS.dmg"
