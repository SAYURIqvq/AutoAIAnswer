#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."

pyinstaller --noconfirm --clean --windowed --name AutoAIAnswer \
  --osx-bundle-identifier com.sayuriqvq.AutoAIAnswer \
  --add-data "ai_screenshot_assistant/web/static:ai_screenshot_assistant/web/static" \
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

python packaging/macos/patch_info_plist.py dist/AutoAIAnswer.app
codesign --force --deep --sign - dist/AutoAIAnswer.app

mkdir -p dist/dmg
rm -rf dist/dmg/AutoAIAnswer.app
cp -R dist/AutoAIAnswer.app dist/dmg/
rm -f dist/AutoAIAnswer-macOS.dmg
hdiutil create -volname AutoAIAnswer -srcfolder dist/dmg -ov -format UDZO dist/AutoAIAnswer-macOS.dmg
echo "Built: dist/AutoAIAnswer.app and dist/AutoAIAnswer-macOS.dmg"
