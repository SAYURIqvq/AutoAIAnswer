from ai_screenshot_assistant.input.mouse_listener import MouseRoiListener


def test_long_press_threshold_is_two_seconds(monkeypatch) -> None:
    long_clicks = []
    short_clicks = []
    listener = MouseRoiListener(lambda x, y: long_clicks.append((x, y)), lambda x, y: short_clicks.append((x, y)))
    listener._left_down_at = 10.0
    listener._left_down_position = (3, 4)
    monkeypatch.setattr("ai_screenshot_assistant.input.mouse_listener.time.monotonic", lambda: 12.0)

    listener._handle_left_up()

    assert listener.long_press_seconds == 2.0
    assert long_clicks == [(3, 4)]
    assert short_clicks == []


def test_disabled_listener_ignores_and_clears_pending_click() -> None:
    clicks = []
    listener = MouseRoiListener(lambda x, y: clicks.append((x, y)), lambda x, y: clicks.append((x, y)))
    listener._left_down_at = 10.0
    listener._left_down_position = (3, 4)

    listener.set_enabled(False)
    listener._handle_left_up()

    assert listener.enabled is False
    assert listener._left_down_at is None
    assert listener._left_down_position is None
    assert clicks == []


def test_explicit_position_supports_macos_callback(monkeypatch) -> None:
    clicks = []
    listener = MouseRoiListener(lambda x, y: clicks.append((x, y)), lambda x, y: clicks.append((x, y)))
    times = iter((10.0, 12.1))
    monkeypatch.setattr("ai_screenshot_assistant.input.mouse_listener.time.monotonic", lambda: next(times))

    listener._handle_left_down((120, 240))
    listener._handle_left_up()

    assert clicks == [(120, 240)]
