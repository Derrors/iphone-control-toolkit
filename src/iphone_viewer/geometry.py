"""Mapping between the viewer window and the phone screen, and turning mouse input into touch gestures.

Phone coordinates are in points (what WebDriverAgent expects), window coordinates in pixels.
"""
from dataclasses import dataclass

# a press that moves less than this (in points) is a tap, not a swipe
TAP_SLOP = 6
LONG_PRESS_SECONDS = 0.5
SWIPE_MS = (100, 800)


@dataclass(frozen=True)
class Viewport:
    """Where the phone screen is drawn inside the canvas: scaled to fit, aspect ratio kept, centered."""

    screen_w: float
    screen_h: float
    scale: float  # canvas pixels per phone point
    x: int
    y: int
    width: int
    height: int

    @classmethod
    def fit(cls, screen_w: float, screen_h: float, canvas_w: int, canvas_h: int) -> "Viewport":
        scale = max(min(canvas_w / screen_w, canvas_h / screen_h), 1e-6)
        width, height = max(1, round(screen_w * scale)), max(1, round(screen_h * scale))
        return cls(screen_w, screen_h, scale, (canvas_w - width) // 2, (canvas_h - height) // 2, width, height)

    def to_points(self, px: float, py: float) -> tuple[float, float]:
        """Canvas pixel to phone point, clamped to the screen so presses on the margin hit the nearest edge."""
        x = (px - self.x) / self.scale
        y = (py - self.y) / self.scale
        return min(max(x, 0.0), self.screen_w), min(max(y, 0.0), self.screen_h)


@dataclass(frozen=True)
class Tap:
    x: float
    y: float


@dataclass(frozen=True)
class LongPress:
    x: float
    y: float
    seconds: float


@dataclass(frozen=True)
class Swipe:
    x0: float
    y0: float
    x1: float
    y1: float
    ms: int


def classify(start: tuple[float, float], end: tuple[float, float], seconds: float) -> Tap | LongPress | Swipe:
    """Turn a mouse press (start and end in points, how long it was held) into a touch gesture."""
    (x0, y0), (x1, y1) = start, end
    if abs(x1 - x0) < TAP_SLOP and abs(y1 - y0) < TAP_SLOP:
        return LongPress(x0, y0, seconds) if seconds >= LONG_PRESS_SECONDS else Tap(x0, y0)
    lo, hi = SWIPE_MS
    return Swipe(x0, y0, x1, y1, min(max(round(seconds * 1000), lo), hi))
