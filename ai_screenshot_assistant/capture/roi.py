from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RoiState(str, Enum):
    IDLE = "IDLE"
    WAIT_SECOND_LEFT = "WAIT_SECOND_LEFT"
    WAIT_RIGHT = "WAIT_RIGHT"
    READY = "READY"


@dataclass(frozen=True)
class Point:
    x: int
    y: int


@dataclass(frozen=True)
class Roi:
    left: int
    top: int
    width: int
    height: int

    @classmethod
    def from_points(cls, p1: Point, p2: Point) -> "Roi":
        left = min(p1.x, p2.x)
        top = min(p1.y, p2.y)
        width = abs(p2.x - p1.x)
        height = abs(p2.y - p1.y)
        if width <= 0 or height <= 0:
            raise ValueError("ROI width and height must be greater than zero")
        return cls(left=left, top=top, width=width, height=height)

    def to_mss_monitor(self) -> dict[str, int]:
        return {"left": self.left, "top": self.top, "width": self.width, "height": self.height}


class RoiStateMachine:
    def __init__(self) -> None:
        self.state = RoiState.IDLE
        self.p1: Point | None = None
        self.p2: Point | None = None

    def start(self) -> None:
        self.p1 = None
        self.p2 = None
        self.state = RoiState.IDLE

    def left_up(self, x: int, y: int) -> None:
        self.p1 = Point(x, y)
        self.p2 = None
        self.state = RoiState.WAIT_RIGHT

    def right_up(self, x: int, y: int) -> Roi | None:
        if self.state != RoiState.WAIT_RIGHT or self.p1 is None:
            return None
        self.p2 = Point(x, y)
        roi = Roi.from_points(self.p1, self.p2)
        self.state = RoiState.READY
        return roi

    def reset(self) -> None:
        self.p1 = None
        self.p2 = None
        self.state = RoiState.IDLE
