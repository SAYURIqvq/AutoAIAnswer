from pathlib import Path

from PySide6.QtCore import QSettings, Qt

from ai_screenshot_assistant.desktop_command_client import WEBSOCKET_MAX_BYTES
from ai_screenshot_assistant.ui.streaming_overlay import MAX_OVERLAY_CHARS, StreamingOverlay


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "ai_screenshot_assistant" / "web" / "static"


def test_overlay_caps_stream_buffer(qapp, monkeypatch) -> None:
    monkeypatch.setattr(StreamingOverlay, "_apply_native_flags", lambda self: None)
    overlay = StreamingOverlay(QSettings())
    overlay.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    overlay.start_stream()
    overlay.append_delta("A" * (MAX_OVERLAY_CHARS + 250))

    assert len(overlay._buffer) == MAX_OVERLAY_CHARS
    overlay.clear()
    assert overlay._buffer == ""
    assert overlay.label.text() == ""
    overlay.close()
    overlay.deleteLater()


def test_overlay_complete_stream_is_capped(qapp, monkeypatch) -> None:
    monkeypatch.setattr(StreamingOverlay, "_apply_native_flags", lambda self: None)
    overlay = StreamingOverlay(QSettings())
    overlay.complete_stream("B" * (MAX_OVERLAY_CHARS + 80))

    assert len(overlay._buffer) == MAX_OVERLAY_CHARS
    overlay.close()
    overlay.deleteLater()


def test_mobile_page_exposes_explicit_model_routes_and_clear_chat() -> None:
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    css = (STATIC / "style.css").read_text(encoding="utf-8")

    assert 'id="model-route"' in html
    assert "OpenRouter · qwen/qwen3-vl-235b-a22b-thinking（最准 / 较慢 / 会思考）" in html
    assert "豆包 Turbo · doubao-seed-2-1-turbo-260628（快 / 准确较好）" in html
    assert "豆包 Mini · doubao-seed-2-0-mini-260428（最快 / 准确一般）" in html
    assert "豆包 Lite · doubao-seed-2-0-lite-260428（较快 / 准确中等）" in html
    assert "豆包 Pro · doubao-seed-2-1-pro-260915（最准 / 较慢）" in html
    assert "OpenRouter · qwen/qwen3-vl-32b-instruct（较快 / 准确较好）" in html
    assert "OpenRouter · qwen/qwen3-vl-8b-instruct（最快 / 准确一般）" in html
    assert "OpenRouter DeepSeek · deepseek/deepseek-v4.1-flash（快 / 准确较好）" in html
    assert "DeepSeek 官方 · deepseek-flash（快 / 准确一般）" in html
    assert 'data-tier="good"' not in html
    assert ">好<" not in html
    assert ">中等<" not in html
    assert ">简单<" not in html
    assert "清空聊天" in html
    assert "保存到相册" in html
    assert "全选" in html
    assert "添加到照片" in html
    assert "command.clear_conversation" in js
    assert "command.set_model_tier" in js
    assert "sendModelTier(currentTier)" not in js
    assert "分析失败：" in js
    fullscreen_chunk = js.split("fullscreenButton.addEventListener", 1)[1].split("chatCaptureButton.addEventListener", 1)[0]
    assert "command.fullscreen" in fullscreen_chunk
    assert "client_request_id: activeDirectRequestId" in fullscreen_chunk
    assert "chat: true" not in fullscreen_chunk
    assert "conversation: true" not in fullscreen_chunk
    assert "请根据当前屏幕作答" not in fullscreen_chunk
    assert "activeChatRequestId = requestId" not in fullscreen_chunk
    fail_chunk = js.split("function failAssistantMessage", 1)[1].split("function isOutdatedAnswerEvent", 1)[0]
    assert "if (!activeChatRequestId)" in fail_chunk
    assert "nextRequestId(\"chat\")" not in fail_chunk
    assert "function isChatAnswer" in js
    assert "聊天请求分析中" not in js
    assert 'startsWith("chat-")' in js
    assert "normalizeRoute" in js
    assert "saveImagesToAlbum" in js
    assert "selectedAlbumItems" in js
    assert "preview-check" in js
    assert "存储图像" in js
    assert "isAppleMobile" in js
    assert "downloadBlob" not in js
    captured_chunk = js.split('event.type === "screenshot.captured"', 1)[1].split('event.type === "answer.error"', 1)[0]
    assert "payload.add_to_buffer === true" in captured_chunk
    assert "addAlbumItem(payload.image, payload.size || 0, true)" in captured_chunk
    assert "addAlbumItem(payload.image, payload.size || 0, forChat)" not in captured_chunk
    assert "截图已到达手机" not in js
    reset_chunk = js.split("function resetChatUi", 1)[1].split("function setActiveTier", 1)[0]
    assert "setOutput(" not in reset_chunk
    assert "activeDirectRequestId = null" not in reset_chunk
    assert "const maxChatMessages = 40" in js
    assert "const maxAlbumItems = 12" in js
    assert "const maxRenderChars = 40000" in js
    assert "add_to_buffer" in js
    assert "conversation.cleared" in js
    assert "model.changed" in js
    assert "function removeSentChatScreenshots" in js
    assert ".model-routes" in css
    assert ".tier-button" not in css
    assert ".clear-chat" in css
    assert ".save-album" in css
    assert ".preview-check" in css
    assert ".album-sheet" in css
    assert "__PAIR_TOKEN__" in html
    assert "lookupSession" in js
    assert "等待电脑端启动，可直接刷新" in js
    assert "pairToken:${hostKey}" in js
    assert "lastEventId:${sessionId" in js
    assert "function storageGet" in js
    assert "visibilitychange" in js


def test_mobile_send_removes_chat_attachments_from_preview() -> None:
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    ask_chunk = js.split("askButton.addEventListener", 1)[1]

    assert "conversation: true" in ask_chunk
    assert "chat: true" in ask_chunk
    assert "removeSentChatScreenshots(chatImages)" in ask_chunk
    assert "item.forChat = false" not in ask_chunk
    assert 'questionInput.value = ""' in ask_chunk
    assert "function removeSentChatScreenshots" in js
    assert "return !sentIds[item.id]" in js


def test_desktop_main_window_uses_quiet_zone_qr_and_memory_caps() -> None:
    source = (ROOT / "ai_screenshot_assistant" / "ui" / "main_window.py").read_text(encoding="utf-8")

    assert "pair_qr_png_bytes" in source
    assert "KeepAspectRatio" in source
    assert "QScrollArea" in source
    assert "SetMinimumSize" in source
    assert "FastTransformation" in source
    assert "addWidget(self.logs, 1)" not in source
    assert "setMaximumBlockCount(400)" in source
    assert "command.clear_conversation" in source
    assert "command.set_model_tier" in source
    assert "openrouter_model_input" not in source
    assert 'self._log("左键框选手势已关闭")' not in source
    assert "desktop_command_received" in source
    assert "apply_window_capture_exclusion" in source
    assert "public_url" in source
    assert "valid_pair_token" in source
    assert 'f"{self.public_url}/pair?t={self.session.pair_token}"' in source


def test_websocket_payload_limit_is_finite() -> None:
    assert 1024 * 1024 <= WEBSOCKET_MAX_BYTES <= 16 * 1024 * 1024


def test_overlay_plain_code_and_saved_color(qapp, tmp_path) -> None:
    settings = QSettings(str(tmp_path / "overlay.ini"), QSettings.Format.IniFormat)
    settings.setValue("overlay/text_color", "#000000")
    overlay = StreamingOverlay(settings)
    assert overlay.label.textFormat() == Qt.TextFormat.PlainText
    assert 'Times New Roman' in overlay.label.styleSheet()
    assert 'color: #000000' in overlay.label.styleSheet()
    overlay.set_text_color("#ffffff")
    overlay.set_font_px(20)
    assert 'color: #ffffff' in overlay.label.styleSheet()
    assert 'font-size: 20px' in overlay.label.styleSheet()
    code = '```cpp\nif (a < b) {\n    return a;\n}\n```'
    overlay.complete_stream(code)
    assert overlay.label.text() == code
    overlay.close()
    overlay.deleteLater()
