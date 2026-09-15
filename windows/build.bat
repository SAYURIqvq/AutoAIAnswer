@echo off
setlocal
cd /d %~dp0
python -m pip install -r requirements.txt
set ICON_ARGS=
if exist assets\app.ico set ICON_ARGS=--icon assets\app.ico
python -m PyInstaller --noconfirm --clean --onefile --windowed --name QQMusicOverlay %ICON_ARGS% ^
  --add-data "assets;assets" ^
  --hidden-import win32_capture ^
  --hidden-import overlay ^
  --exclude-module IPython ^
  --exclude-module pytest ^
  --exclude-module tkinter ^
  main.py
echo Built: dist\QQMusicOverlay.exe
endlocal
