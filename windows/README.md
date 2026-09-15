# Windows 悬浮窗独立工程

GitHub 分支：`win`。只包含 Windows 字幕悬浮窗（`WDA_EXCLUDEFROMCAPTURE`），和 macOS / 主工程分开。

需要 **Windows 10 2004** 或更高。

## 直接运行

```powershell
python -m pip install -r requirements.txt
python main.py
```

## 打包成 exe

```bat
build.bat
```

生成 `dist\QQMusicOverlay.exe`。

## 怎么判断成功

控制窗口会出现在屏幕共享里。白色字幕悬浮窗应被排除。

1. 勾选「显示悬浮字幕」，拖到显眼位置。
2. 本机看得见字幕。
3. Win+Shift+S 截图，共享图里应没有字幕。
4. Zoom / 腾讯会议选「共享整个屏幕」。
