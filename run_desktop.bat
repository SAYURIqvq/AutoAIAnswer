@echo off
setlocal
cd /d %~dp0
if not exist .venv (
  py -3.11 -m venv .venv
)
call .venv\Scripts\activate
python -m pip install -r requirements.txt
python main.py

