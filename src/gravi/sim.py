"""The simulation core: a point mass under gravity plus one central force.

No physics engine. The entire dynamic state is six floats and the only contact
test is circle-vs-circle, so a hand-written symplectic integrator is simpler,
exactly deterministic, fast enough for the offline validator to run thousands
of headless rollouts, and — unlike pymunk — it runs in the browser.

Semi-implicit (symplectic) Euler is used deliberately: a linear central force
is a harmonic oscillator, and symplectic integrators do not pump energy into
oscillators the way explicit Euler does, so orbits stay stable instead of
spiralling outward.

Never import pygame here (see tests/test_purity.py).
"""

from __future__ import annotations

import math

from .config import PHYS_DT
from .field import Charge, FieldParams, Node, charge_force
from .room import Room


class World:
    """Mutable simulation state for one attempt at a room."""

    def __init__(
        self,
        room: Room,
        params: FieldParams,
        gravity_y: float,
        player_radius: float,
        speed_max: float,
        dt: float = PHYS_DT,
    ) -> None:
        self.room = room
        self.params = params
        self.gravity_y = gravity_y
        self.player_radius = player_radius
        self.speed_max = speed_max
        self.dt = dt

        self.x = 0.0
        self.y = 0.0
        self.vx = 0.0
        self.vy = 0.0
        self.dead = False
        self.elapsed = 0.0
        self.reset()

    def reset(self) -> None:
        self.x, self.y = self.room.spawn
        self.vx = 0.0
        self.vy = 0.0
        self.dead = False
        self.elapsed = 0.0

    def active_node(self) -> Node | None:
        """Nearest node whose influence radius contains the player. Ties break
        on lowest index so the choice is deterministic. Overlapping fields
        producing a net force is a deliberate late-game escalation (spec 3.6),
        not a slice 1 feature."""
        best: Node | None = None
        best_distance = math.inf
        for node in self.room.nodes:
            distance = math.hypot(node.x - self.x, node.y - self.y)
            if distance <= node.radius and distance < best_distance:
                best = node
                best_distance = distance
        return best

    def step(self, charge: Charge) -> None:
        """Advance one fixed timestep. No-op once dead."""
        if self.dead:
            return

        ax = 0.0
        ay = self.gravity_y  # mass is fixed at 1.0, so force == acceleration

        node = self.active_node()
        if node is not None:
            fx, fy = charge_force(self.x, self.y, node, charge, self.params)
            ax += fx
            ay += fy

        self.vx += ax * self.dt
        self.vy += ay * self.dt

        speed = math.hypot(self.vx, self.vy)
        if speed > self.speed_max and speed > 0.0:
            scale = self.speed_max / speed
            self.vx *= scale
            self.vy *= scale

        self.x += self.vx * self.dt
        self.y += self.vy * self.dt
        self.elapsed += self.dt

        self._check_death()

    def _check_death(self) -> None:
        for node in self.room.nodes:
            lethal = node.core_radius + self.player_radius
            if math.hypot(node.x - self.x, node.y - self.y) <= lethal:
                self.dead = True
                return

        margin = 200.0  # let the player leave the frame briefly and recover
        if not (-margin <= self.x <= self.room.width + margin):
            self.dead = True
        elif not (-margin <= self.y <= self.room.height + margin):
            self.dead = True


def charge_from_input(attract_held: bool, repel_held: bool) -> Charge:
    """Map the two inputs to a charge. Holding both is neutral — pressing
    everything must never be the strongest option."""
    if attract_held and not repel_held:
        return Charge.ATTRACT
    if repel_held and not attract_held:
        return Charge.REPEL
    return Charge.NEUTRAL
