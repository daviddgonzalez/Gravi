"""The force law. THE single source of truth for Gravi's physics.

This module is imported by the game, by the offline chamber validator, and by
the trainer. It must never import pygame, the scene layer, or the renderer —
if the validator ever simulates physics that differ from the game, every
difficulty measurement it produces is fiction (see spec section 8.1).

Attract is a LINEAR central force, F = k*r toward the centre, not inverse
square. Three reasons, in priority order:
  1. No singularity at r = 0, so close passes are well behaved.
  2. Bounded orbits close on themselves, so a grab produces a repeating
     ellipse rather than a spiral to fight. Orbital period is 2*pi/sqrt(k)
     and does not depend on orbit size.
  3. Force grows with distance, which reads exactly like the stretched beam
     the player is looking at.

Repel is the mirror in range profile: strongest at contact, fading to zero at
the rim. Attract is a long-range whip; repel is a close-range kick.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import IntEnum

Vec = tuple[float, float]

_EPSILON = 1e-9


class Charge(IntEnum):
    """The player's three states. There is no fourth input in Gravi."""

    REPEL = -1
    NEUTRAL = 0
    ATTRACT = 1


@dataclass(frozen=True)
class FieldParams:
    """Live-tunable force constants. k units are 1/s^2 (force per unit mass)."""

    k_attract: float
    k_repel: float
    force_max: float


@dataclass(frozen=True)
class Node:
    """A charged anchor. `radius` is the influence radius the glow ring draws;
    `core_radius` is the solid, lethal centre."""

    x: float
    y: float
    radius: float
    core_radius: float


def charge_force(
    px: float, py: float, node: Node, charge: Charge, params: FieldParams,
    ignore_radius: bool = False,
) -> Vec:
    """Force on a unit-mass player at (px, py) from `node` under `charge`.

    Returns (0.0, 0.0) when neutral, outside the influence radius, or exactly
    at the node centre.

    `ignore_radius=True` drops the influence-radius cutoff, for a player who
    latched onto this node while inside it and has since stretched past the
    rim (see World.step). The law is unchanged out there — attract is still
    F = k*r, so the rope keeps tightening with distance until force_max caps
    it.

    In the game only attract is ever called this way, because a repel rope
    breaks at the rim. The `max(0.0, ...)` floor below still guards the repel
    case for any other caller — the validator and the trainer share this
    function — since k*(R - r) goes negative past the rim and would otherwise
    silently invert a push into a pull.
    """
    if charge is Charge.NEUTRAL:
        return (0.0, 0.0)

    dx = node.x - px
    dy = node.y - py
    r = math.hypot(dx, dy)

    if r < _EPSILON or (r > node.radius and not ignore_radius):
        return (0.0, 0.0)

    if charge is Charge.ATTRACT:
        magnitude = params.k_attract * r
        sign = 1.0
    else:
        magnitude = params.k_repel * (node.radius - r)
        sign = -1.0

    magnitude = min(max(0.0, magnitude), params.force_max)
    ux = dx / r
    uy = dy / r
    return (sign * magnitude * ux, sign * magnitude * uy)


def surface_force(distance: float, normal: Vec, params: FieldParams,
                  reach: float) -> Vec:
    """Repel force from a flat charged surface, pushing along `normal`.

    `normal` must be a unit vector pointing AWAY from the surface, and
    `distance` is how far the player is from it.

    A surface obeys the node's repel law, which core spec 2.3 requires
    ("charged surfaces obey the same law"): strongest at contact, fading
    linearly to nothing at the rim. A wall has no attract case — deferred
    deliberately, see the 2026-08-22 design doc section 7.

    A negative distance means the player is already past the surface. It is
    treated as contact rather than extrapolated, because k*(reach - distance)
    keeps growing out there and, worse, nothing stops the caller from having
    handed us an inward normal — the pair would then pull them further
    through. They die on the next bounds check regardless.
    """
    if reach <= 0.0 or distance >= reach:
        return (0.0, 0.0)
    magnitude = params.k_repel * (reach - max(0.0, distance))
    magnitude = min(max(0.0, magnitude), params.force_max)
    return (normal[0] * magnitude, normal[1] * magnitude)
