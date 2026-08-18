"""World -> screen. Rotation happens here and nowhere else.

World coordinates never rotate. That is not an aesthetic choice: the offline
validator and the trainer must simulate exactly what the game simulates (core
spec 8.1), and a rotating coordinate system would be a second source of truth.

Rotating at draw time is cheap here for a reason specific to Gravi: circles are
rotation-invariant. Nodes, cores, glows and the player are circles, so only
their centre points transform. Only the trail polyline, the beam, the arrow
bars and the chamber outlines need per-point work, and sin/cos are computed
once per frame.

Rejected: rotating the finished frame with pygame.transform.rotate. At
mid-ease angles the output bounding box grows by up to sqrt(2), so it is ~1M
pixels resampled plus an allocation every frame against a frame that costs
1.10 ms — and it resamples rasterised neon, which blurs and crawls the glow,
the exact shimmer that choosing neon was supposed to delete.
"""

from __future__ import annotations

import math

from .. import config

LEAD_FRACTION = 0.12


class Camera:
    def __init__(self, width: int = config.WINDOW_WIDTH,
                 height: int = config.WINDOW_HEIGHT) -> None:
        self.width = width
        self.height = height
        self.eye = (width / 2.0, height / 2.0)
        self._cos = 1.0
        self._sin = 0.0
        self._ox = 0.0
        self._oy = 0.0

    @classmethod
    def identity(cls) -> "Camera":
        """A camera that maps world coordinates straight through. For tests
        and for any draw path that wants raw coordinates."""
        cam = cls()
        cam.eye = (0.0, 0.0)
        return cam

    def update(self, x: float, y: float, angle: float, rotating: bool) -> None:
        a = angle if rotating else 0.0
        self._cos = math.cos(a)
        self._sin = math.sin(a)
        self._ox, self._oy = x, y
        if rotating:
            # Gravity is a fixed point on screen, so the lead can be too.
            self.eye = (self.width / 2.0, self.height / 2.0 - self.height * LEAD_FRACTION)
        else:
            # Dead centre: equal visibility in every direction, and nothing
            # about the framing moves when gravity turns.
            self.eye = (self.width / 2.0, self.height / 2.0)

    def to_screen(self, x: float, y: float) -> tuple[float, float]:
        dx = x - self._ox
        dy = y - self._oy
        return (self.eye[0] + dx * self._cos - dy * self._sin,
                self.eye[1] + dx * self._sin + dy * self._cos)

    def direction_to_screen(self, dx: float, dy: float) -> tuple[float, float]:
        """A direction, not a point: rotation only, no translation."""
        return (dx * self._cos - dy * self._sin, dx * self._sin + dy * self._cos)

    def to_world(self, sx: float, sy: float) -> tuple[float, float]:
        dx = sx - self.eye[0]
        dy = sy - self.eye[1]
        return (self._ox + dx * self._cos + dy * self._sin,
                self._oy - dx * self._sin + dy * self._cos)
