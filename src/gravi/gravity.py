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
from enum import Enum

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


class GravityMode(Enum):
    """What the gravity vector DOES to the player. Not what it is — the eased
    quarter-turn in `GravityState` is untouched by all of these, so the camera,
    the flip cadence and the camera lead keep working unchanged.

    Experiments for the slice 2 playtest (see the 2026-08-20 design doc).
    ALONG is the shipped behaviour and the default everywhere.
    """

    ALONG = "along"
    PERP_CORRIDOR = "perp-corridor"
    PERP_VELOCITY = "perp-velocity"

    def next(self) -> "GravityMode":
        order = list(GravityMode)
        return order[(order.index(self) + 1) % len(order)]


# The most the heading may turn in one physics step. Beyond this the mode
# stops being steering and becomes a spin dictated by the exact float value
# of a tiny speed: at magnitude 500 and dt 1/240, a speed of 0.1 px/s turns
# the heading 132 degrees in a single step. Below the speed where that would
# happen, gravity behaves as ALONG instead — which is also the only thing
# that gets a stopped player moving again.
MAX_TURN_PER_STEP = 0.25        # radians, ~14 degrees


def apply_gravity(mode: GravityMode, direction: Vec, vx: float, vy: float,
                  magnitude: float, dt: float) -> Vec:
    """The velocity after one step of gravity.

    Returns a VELOCITY rather than an acceleration on purpose: two of these
    modes are a force and the third is a rotation, and only by handing back the
    finished velocity can one function cover both without the caller knowing
    which it got.
    """
    # GravityMode used to mix in `str`, which advertises that a plain string
    # is interchangeable with a member — but dispatch below uses `is`, so a
    # string (exactly what json.loads(json.dumps(mode)) returns, and this
    # project saves/loads JSON presets) would silently compare unequal to
    # every branch and fall through to PERP_VELOCITY instead of raising.
    # Resolving by value here makes a string behave correctly, and makes an
    # unrecognised value raise ValueError instead of failing silently.
    mode = GravityMode(mode)
    gx, gy = direction
    if mode is GravityMode.ALONG or mode is GravityMode.PERP_CORRIDOR:
        # Both of these are plain forces — gravity_force already has the
        # direction-scaling formula for each, differing from here only by the
        # dt factor, so compute the acceleration there and integrate it here
        # rather than keeping two copies of the same arithmetic in sync. The
        # multiplication order below is unchanged (fx = gx * magnitude, then
        # fx * dt), so this is byte-identical to the pre-refactor code.
        fx, fy = gravity_force(mode, direction, vx, vy, magnitude)
        return (vx + fx * dt, vy + fy * dt)

    speed = math.hypot(vx, vy)
    theta = 0.0 if speed == 0.0 else (magnitude / speed) * dt
    if speed == 0.0 or abs(theta) > MAX_TURN_PER_STEP:
        # Perpendicular to nothing is undefined, and near-zero speed makes
        # theta blow up into a spin rather than steering. Either way, ALONG
        # is what gets the player moving again.
        return (vx + gx * magnitude * dt, vy + gy * magnitude * dt)

    # A ROTATION, not an added force. A perpendicular force does no work in
    # continuous mathematics, but explicit Euler at 240 Hz walks the velocity
    # off the circle it is meant to stay on and the speed creeps upward. A
    # rotation is speed-preserving by construction at any step size.
    c, s = math.cos(theta), math.sin(theta)
    return (vx * c - vy * s, vx * s + vy * c)


def gravity_force(mode: GravityMode, direction: Vec, vx: float, vy: float,
                  magnitude: float) -> Vec:
    """Gravity as an ACCELERATION VECTOR, for callers that must not have their
    whole velocity rotated out from under them.

    `apply_gravity` returns a finished velocity because PERP_VELOCITY is a
    rotation, and a rotation is the only way to keep that mode from pumping
    speed in. But a rotation composes badly with a constraint: rotating the
    velocity about the origin injects a component that is radial relative to a
    rope's anchor, the rope strips it, and two individually speed-preserving
    operations leak energy together — measured at 260 -> 10 px/s over 70
    seconds on a held rope. So a constrained caller takes the force form and
    lets its own constraint absorb whatever part it must.
    """
    mode = GravityMode(mode)
    gx, gy = direction
    if mode is GravityMode.ALONG:
        return (gx * magnitude, gy * magnitude)

    if mode is GravityMode.PERP_CORRIDOR:
        return (-gy * magnitude, gx * magnitude)

    speed = math.hypot(vx, vy)
    if speed == 0.0:
        # Perpendicular to nothing is undefined, and a stopped player has
        # nothing else to get them moving again — same threshold, same
        # reason, as apply_gravity's own PERP_VELOCITY fallback.
        return (gx * magnitude, gy * magnitude)
    return (-vy / speed * magnitude, vx / speed * magnitude)


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
