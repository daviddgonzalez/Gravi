"""Gravity direction as one eased scalar.

Gravity direction and camera rotation are the SAME number (slice 2 spec
section 3.1). Because the camera rotation is exactly the rotation that carries
the gravity vector onto screen-down, gravity is straight down on screen at
every instant, including mid-turn — not merely at the endpoints. Snapping
gravity at the crossing and easing only the camera was rejected: it leaves
0.2 s in which the force felt and the screen read disagree, at precisely the
moment the player is most disoriented.

The flip TARGET is an integer count of quarter turns; only the eased CURRENT
angle is a float. Hundreds of flips accumulating `+= pi/2` would drift.

phi = 0 is world-down. Increasing phi sweeps gravity from 6 o'clock toward
3 o'clock, which is counter-clockwise on screen — so the spec's clockwise
convention for 180 degree flips means DECREASING phi.

Never import pygame here (see tests/test_purity.py).
"""

from __future__ import annotations

import math

QUARTER = math.pi / 2

Vec = tuple[float, float]


def ease_in_out(t: float) -> float:
    """Raised cosine on [0, 1], clamped outside it. Zero slope at both ends,
    which is what stops a flip from starting and stopping with a jerk."""
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    return 0.5 - 0.5 * math.cos(math.pi * t)


class GravityState:
    """Eased quarter-turn gravity. `angle` is the only float that moves."""

    def __init__(self, quarter_turns: int = 0, flip_duration: float = 0.3) -> None:
        self.target_turns = int(quarter_turns)
        self.flip_duration = flip_duration
        self.angle = self.target_angle
        self._from_angle = self.angle
        self._t = 1.0

    @property
    def target_angle(self) -> float:
        return self.target_turns * QUARTER

    @property
    def settled(self) -> bool:
        return self._t >= 1.0

    def flip_by(self, quarter_turns: int) -> None:
        """Turn by a signed number of quarter turns, from wherever the ease
        currently is — so a flip that interrupts another flip is continuous."""
        if int(quarter_turns) == 0:
            # A straight chamber crosses its seam with turn 0. Starting an ease
            # to the angle we are already at would report the state as mid-flip
            # for flip_duration seconds while nothing moved.
            return
        self._from_angle = self.angle
        self.target_turns += int(quarter_turns)
        if self.flip_duration <= 0.0:
            self._t = 1.0
            self.angle = self.target_angle
        else:
            self._t = 0.0

    def flip_to(self, quarter_turns: int) -> None:
        """Turn to an absolute quarter-turn index by the shortest path. A
        180 degree turn is ambiguous, so it goes clockwise (phi decreasing)."""
        delta = (int(quarter_turns) - self.target_turns) % 4
        if delta == 3:
            delta = -1
        elif delta == 2:
            delta = -2      # clockwise by convention
        self.flip_by(delta)

    def settle(self, quarter_turns: int) -> None:
        """Jump straight to an orientation with no ease. Spawning uses this:
        a run must never open mid-flip."""
        self.target_turns = int(quarter_turns)
        self.angle = self.target_angle
        self._from_angle = self.angle
        self._t = 1.0

    def advance(self, dt: float) -> None:
        if self._t >= 1.0:
            return
        self._t = min(1.0, self._t + dt / self.flip_duration)
        span = self.target_angle - self._from_angle
        self.angle = self._from_angle + span * ease_in_out(self._t)
        if self._t >= 1.0:
            self.angle = self.target_angle

    def direction(self) -> Vec:
        return (math.sin(self.angle), math.cos(self.angle))

    def vector(self, magnitude: float) -> Vec:
        dx, dy = self.direction()
        return (dx * magnitude, dy * magnitude)
