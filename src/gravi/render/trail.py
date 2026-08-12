"""The player's recent path. Pure state so it can be unit-tested without a
display, and so the slice 6 path map can reuse it unchanged."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable


class Trail:
    def __init__(self, max_points: int) -> None:
        self._points: deque[tuple[float, float]] = deque(maxlen=max_points)

    def add(self, x: float, y: float) -> None:
        self._points.append((x, y))

    def points(self) -> Iterable[tuple[float, float]]:
        return tuple(self._points)

    def clear(self) -> None:
        self._points.clear()

    def __len__(self) -> int:
        return len(self._points)
