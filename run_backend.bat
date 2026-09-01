@echo off
setlocal
cd /d %~dp0
if not exist .venv (
  py -3.11 -m venv .venv
)
call .venv\Scripts\activate
python -m pip install -r requirements.txt
uvicorn ai_screenshot_assistant.backend.app:app --host 0.0.0.0 --port 8000

