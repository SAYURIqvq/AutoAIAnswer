from types import SimpleNamespace

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QLabel, QTextEdit

from ai_screenshot_assistant.ai.client import _build_user_prompt
from ai_screenshot_assistant.ui.main_window import MainWindow
from ai_screenshot_assistant.ui.streaming_overlay import StreamingOverlay
from ai_screenshot_assistant.backend.app import _mobile_command_payload


def test_mobile_prompt_preserves_long_text_and_whitespace():
    text = "  <rules>\n" + "代码先行\n" * 6000
    assert _mobile_command_payload({"type": "command.save_prompt", "payload": {"text": text}})["text"] == text


def test_long_plain_prompt_survives_save_reload_and_all_providers(qapp, tmp_path):
    store = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    prompt = "<answer>代码优先</answer>\n" * 5000
    editor = QTextEdit()
    editor.setPlainText(prompt)
    target = SimpleNamespace(
        prompt_input=editor, app_settings=store, workflow=None,
        save_status=QLabel(), deepseek_key="", qwen_key="", qwen_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1", doubao_key="",
        model_tier="doubao-seed-2-1-pro",
        signals=SimpleNamespace(provider_changed=SimpleNamespace(emit=lambda _: None)),
    )
    MainWindow.save_prompt_settings(target)
    reloaded = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    assert reloaded.value("prompt/system") == prompt
    client = MainWindow._build_ai_client(target)
    for provider in (client.deepseek, client.qwen, client.doubao):
        assert provider.provider.system_prompt == prompt
    built = _build_user_prompt("请用 Java", [], prompt)
    assert built.startswith(prompt.strip())
    assert "第一行仍必须" not in built
    assert "请用 Java" in built


def test_overlay_font_color_survive_size_change_and_restart(qapp, tmp_path):
    store = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    store.setValue("appearance/font_family", "Times New Roman")
    store.setValue("overlay/text_color", "black")
    overlay = StreamingOverlay(store)
    try:
        assert overlay.label.font().family() == "Times New Roman"
        assert "#000000" in overlay.label.styleSheet()
        overlay.set_font_px(20)
        assert "#000000" in overlay.label.styleSheet()
        overlay.set_text_appearance("Times New Roman", "white")
        assert "#ffffff" in overlay.label.styleSheet()
        for color, expected in (("blue", "#0066ff"), ("red", "#ff0000")):
            overlay.set_text_appearance("Times New Roman", color)
            overlay.set_font_px(18)
            assert expected in overlay.label.styleSheet()
    finally:
        overlay.close()
