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
    px: float, py: float, node: Node, charge: Charge, params: FieldParams
) -> Vec:
    """Force on a unit-mass player at (px, py) from `node` under `charge`.

    Returns (0.0, 0.0) when neutral, outside the influence radius, or exactly
    at the node centre.
    """
    if charge is Charge.NEUTRAL:
        return (0.0, 0.0)

    dx = node.x - px
    dy = node.y - py
    r = math.hypot(dx, dy)

    if r > node.radius or r < _EPSILON:
        return (0.0, 0.0)

    if charge is Charge.ATTRACT:
        magnitude = params.k_attract * r
        sign = 1.0
    else:
        magnitude = params.k_repel * (node.radius - r)
        sign = -1.0

    magnitude = min(magnitude, params.force_max)
    ux = dx / r
    uy = dy / r
    return (sign * magnitude * ux, sign * magnitude * uy)
