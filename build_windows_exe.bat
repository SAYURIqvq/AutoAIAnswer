@echo off
setlocal
cd /d %~dp0
if not exist .venv (
  py -3.11 -m venv .venv
)
call .venv\Scripts\activate
python -m pip install -r requirements.txt
pyinstaller --noconfirm --clean --onefile --windowed --name AI_Assistant ^
  --add-data "ai_screenshot_assistant\web\static;ai_screenshot_assistant\web\static" ^
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
echo Built: dist\AI_Assistant.exe
