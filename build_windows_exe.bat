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
  --add-data ".env;." ^
  main.py
echo Built: dist\AI_Assistant.exe
