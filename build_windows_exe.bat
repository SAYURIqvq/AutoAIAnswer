@echo off
setlocal
cd /d %~dp0
python -m pip install -r requirements.txt
set ICON_ARGS=
if exist assets\app.ico set ICON_ARGS=--icon assets\app.ico
python -m PyInstaller --noconfirm --clean --onefile --windowed --name QQMusic %ICON_ARGS% ^
  --add-data "ai_screenshot_assistant\web\static;ai_screenshot_assistant\web\static" ^
  --add-data "assets;assets" ^
  --exclude-module IPython ^
  --exclude-module pytest ^
  --exclude-module matplotlib ^
  --exclude-module pandas ^
  --exclude-module pyarrow ^
  --exclude-module scipy ^
  --exclude-module sklearn ^
  --exclude-module torch ^
  --exclude-module torchvision ^
  --exclude-module torchaudio ^
  --exclude-module transformers ^
  --exclude-module datasets ^
  --exclude-module gradio ^
  --exclude-module cv2 ^
  --exclude-module tkinter ^
  main.py
echo Built: dist\QQMusic.exe
endlocal

