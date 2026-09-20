import sys
from pathlib import Path

from ai_screenshot_assistant.backend.embedded import EmbeddedBackend
from ai_screenshot_assistant.backend.session_manager import valid_pair_token
from main import _restore_hint

ROOT = Path(__file__).resolve().parents[1]


def test_embedded_backend_keeps_preferred_port(monkeypatch) -> None:
    monkeypatch.setattr("ai_screenshot_assistant.backend.embedded.get_lan_ip", lambda: "192.168.1.8")
    backend = EmbeddedBackend(8000)
    assert backend.port == 8000
    assert backend.local_url == "http://127.0.0.1:8000"
    assert backend.url == "http://192.168.1.8:8000"


def test_main_uses_loopback_for_desktop_and_lan_for_qr() -> None:
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "backend.local_url" in source
    assert "public_url=backend.url" in source
    assert "Local\\\\com.sayuriqvq.QQMusic.single" in source
    assert "setStaleLockTime(0)" in source
    assert "removeStaleLockFile" not in source


def test_macos_packaging_includes_pynput() -> None:
    source = (ROOT / "packaging" / "macos" / "package.sh").read_text(encoding="utf-8")
    assert "pynput.mouse._darwin" in source
    assert "--collect-submodules pynput" in source


def test_pair_token_helper_rejects_short_values() -> None:
    assert valid_pair_token("too-short") is None
    assert valid_pair_token("stable_pair_token_1234567890") == "stable_pair_token_1234567890"


def test_restore_hint_matches_platform() -> None:
    hint = _restore_hint()
    if sys.platform == "win32":
        assert "托盘" in hint
        assert "菜单栏" not in hint
    elif sys.platform == "darwin":
        assert "菜单栏" in hint
    else:
        assert "托盘" in hint
