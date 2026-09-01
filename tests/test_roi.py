import pytest

from ai_screenshot_assistant.capture.roi import Point, Roi, RoiState, RoiStateMachine


def test_roi_normalizes_points() -> None:
    roi = Roi.from_points(Point(300, 200), Point(100, 450))

    assert roi.left == 100
    assert roi.top == 200
    assert roi.width == 200
    assert roi.height == 250
    assert roi.to_mss_monitor() == {"left": 100, "top": 200, "width": 200, "height": 250}


def test_roi_rejects_zero_size() -> None:
    with pytest.raises(ValueError):
        Roi.from_points(Point(100, 100), Point(100, 120))


def test_roi_state_machine_long_left_then_right_flow() -> None:
    machine = RoiStateMachine()

    machine.start()
    machine.left_up(1, 2)
    roi = machine.right_up(110, 70)

    assert machine.state == RoiState.READY
    assert roi == Roi(left=1, top=2, width=109, height=68)


def test_roi_state_machine_ignores_right_before_long_left() -> None:
    machine = RoiStateMachine()

    machine.start()
    roi = machine.right_up(110, 70)

    assert roi is None
    assert machine.state == RoiState.IDLE
