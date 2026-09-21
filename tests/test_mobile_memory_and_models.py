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


def test_mobile_page_exposes_model_routes_and_clear_chat() -> None:
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    css = (STATIC / "style.css").read_text(encoding="utf-8")

    assert 'id="model-route"' in html
    assert 'value="doubao-seed-vision"' in html
    assert 'value="openrouter-qwen-235b"' in html
    assert 'value="openrouter-qwen-32b"' in html
    assert 'value="deepseek-flash"' in html
    assert "清空聊天" in html
    assert "保存到相册" in html
    assert "全选" in html
    assert "添加到照片" in html
    assert "command.clear_conversation" in js
    assert "command.set_model_tier" in js
    assert "saveImagesToAlbum" in js
    assert "selectedAlbumItems" in js
    assert "存储图像" in js
    assert "isAppleMobile" in js
    assert "downloadBlob" not in js
    assert "add_to_buffer" in js
    assert "conversation.cleared" in js
    assert "model.changed" in js
    assert "function removeSentChatScreenshots" in js
    assert "function stopActiveAssistantMessage" in js
    assert "latestChatRequestId" in js
    assert "latestDirectRequestId" in js
    assert "#model-route" in css
    assert ".clear-chat" in css
    assert ".save-album" in css
    assert ".preview-check" in css
    assert ".album-sheet" in css


def test_mobile_send_removes_chat_attachments_from_preview() -> None:
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    ask_chunk = js.split("askButton.addEventListener", 1)[1]

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
    assert "setMaximumBlockCount(80)" in source
    assert "command.clear_conversation" in source
    assert "command.set_model_tier" in source
    assert "openrouter_model_input" not in source


def test_websocket_payload_limit_is_finite() -> None:
    assert 1024 * 1024 <= WEBSOCKET_MAX_BYTES <= 16 * 1024 * 1024
