"""World -> screen. Rotation and view scale happen here and nowhere else.

World coordinates never rotate and never scale. That is not an aesthetic
choice: the offline validator and the trainer must simulate exactly what the
game simulates (core spec 8.1), and a rotating or zooming coordinate system
would be a second source of truth. Both transforms live in this file, are
applied at draw time, and are invisible to `sim.py`.

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

## Field of view

`view_width` is how many world units fit across the window, so a bigger number
shows more world. 1280 against a 1280px window is 1:1 — the framing slice 2
shipped with. Widening it is how you see far enough ahead to plan a grab before
you arrive instead of reacting to whatever enters a 1:1 window.

Two things follow from scale being a draw-time transform:

- **World lengths must be scaled at every draw site** — node radii, core radii,
  the player. The influence ring IS the influence radius (spec section 7), so a
  ring left in pixels would lie about where the force reaches as soon as the
  view widened. Use `scale_length`.
- **Screen furniture must not be** — line widths, the arrow's chevron glyphs.
  Those are legibility, not geometry, and a 2px ring that becomes sub-pixel is
  just a ring you cannot see.

The scale deliberately does NOT give the fixed camera a lead. Widening shows
more in every direction at once and moves nothing, which is the only framing
amendment A1 allows the fixed camera (slice 2 spec section 5.2): a lead has to
point somewhere, the only "somewhere" available is the gravity direction, and
swinging it on every flip is the pan A1 exists to forbid. The `lead` argument
is the rotating camera's, where gravity is already a fixed point on screen.
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
        self.scale = 1.0
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

    def update(self, x: float, y: float, angle: float, rotating: bool,
               view_width: float | None = None,
               lead: float = LEAD_FRACTION) -> None:
        a = angle if rotating else 0.0
        self._cos = math.cos(a)
        self._sin = math.sin(a)
        self._ox, self._oy = x, y
        # None and a zero-or-negative width both mean "leave it 1:1" rather
        # than dividing by zero halfway through a frame.
        self.scale = (self.width / view_width
                      if view_width is not None and view_width > 0.0 else 1.0)
        if rotating:
            # Gravity is a fixed point on screen, so the lead can be too. It is
            # a fraction of the SCREEN, not of the world, which keeps it
            # independent of the view scale.
            self.eye = (self.width / 2.0,
                        self.height / 2.0 - self.height * lead)
        else:
            # Dead centre: equal visibility in every direction, and nothing
            # about the framing moves when gravity turns. `lead` is ignored
            # here on purpose — see the module docstring.
            self.eye = (self.width / 2.0, self.height / 2.0)

    def to_screen(self, x: float, y: float) -> tuple[float, float]:
        dx = (x - self._ox) * self.scale
        dy = (y - self._oy) * self.scale
        return (self.eye[0] + dx * self._cos - dy * self._sin,
                self.eye[1] + dx * self._sin + dy * self._cos)

    def direction_to_screen(self, dx: float, dy: float) -> tuple[float, float]:
        """A direction, not a point: rotation only, no translation, and no
        scale — a unit vector must stay one."""
        return (dx * self._cos - dy * self._sin, dx * self._sin + dy * self._cos)

    def scale_length(self, length: float) -> float:
        """A world length in pixels. Every radius drawn goes through here."""
        return length * self.scale

    def to_world(self, sx: float, sy: float) -> tuple[float, float]:
        dx = (sx - self.eye[0]) / self.scale
        dy = (sy - self.eye[1]) / self.scale
        return (self._ox + dx * self._cos + dy * self._sin,
                self._oy - dx * self._sin + dy * self._cos)


def chambers_in_view(at: int, view_width: float, depth: float,
                     width: int = config.WINDOW_WIDTH,
                     height: int = config.WINDOW_HEIGHT,
                     behind: int = 1) -> range:
    """Which chamber indices are worth drawing at this field of view.

    Derived rather than hard-coded because the two knobs move in opposite
    directions: a wider view and shallower chambers each put more corridor on
    screen. Nodes are drawn over this same span, so a chamber outline can never
    appear without its node field — an empty corridor ahead is worse than no
    corridor ahead, because it reads as a safe one.

    The reach is measured to a screen CORNER, not to an edge: at a mid-ease
    angle the corridor runs diagonally across the window.
    """
    scale = width / view_width if view_width > 0.0 else 1.0
    reach = math.hypot(width, height) / 2.0 / scale
    ahead = max(2, int(reach // max(depth, 1.0)) + 1)
    return range(max(0, at - behind), at + ahead + 1)
