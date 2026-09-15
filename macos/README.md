# macOS 悬浮窗独立工程

GitHub 分支：`mac`。只包含 macOS 字幕悬浮窗（`NSWindow.sharingType = .none`），和 Windows / 主工程分开。拷到 Mac 上打包即可。

系统建议 **macOS 14.2.1**（Sonoma）。15 及以上 ScreenCaptureKit 可能仍能抓到这个窗。

## 直接运行

```bash
chmod +x run.sh build.sh
./run.sh
```

## 打包成 .app / .dmg

```bash
chmod +x build.sh
./build.sh
```

生成：

- `dist/QQMusicOverlay.app`
- `dist/QQMusicOverlay-macOS.dmg`

未签名时，请在 Finder 里右键应用 → 打开。

## 怎么判断成功

控制窗口**会出现**在共享画面里。白色字幕悬浮窗在 14.2.1 上应被排除。

1. 勾选「显示悬浮字幕」，拖到显眼位置。
2. 本机看得见字幕。
3. `Cmd + Shift + 4` 截图，共享图里应没有字幕。
4. Zoom / 腾讯会议选「共享整个屏幕」。Zoom 抓屏模式选带「窗口过滤」的那档。
