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
        fall_speed_max: float = math.inf,
        dt: float = PHYS_DT,
    ) -> None:
        self.room = room
        self.params = params
        self.gravity_y = gravity_y
        self.player_radius = player_radius
        self.speed_max = speed_max
        self.fall_speed_max = fall_speed_max
        self.dt = dt

        self.x = 0.0
        self.y = 0.0
        self.vx = 0.0
        self.vy = 0.0
        self.dead = False
        self.elapsed = 0.0
        self._latch_index: int | None = None
        self.reset()

    def reset(self) -> None:
        self.x, self.y = self.room.spawn
        self.vx = 0.0
        self.vy = 0.0
        self.dead = False
        self.elapsed = 0.0
        self._latch_index = None

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

    def latched_node(self) -> Node | None:
        """The node currently roped to, or None. Tracked by index rather than
        by value because `Node` is frozen and compares by value: the editor
        replaces a node in place when you drag it, and the rope must follow
        the node to its new position instead of pointing at a stale copy."""
        if self._latch_index is None:
            return None
        if self._latch_index >= len(self.room.nodes):
            # The editor deleted it out from under us.
            self._latch_index = None
            return None
        return self.room.nodes[self._latch_index]

    def _update_latch(self, charge: Charge) -> Node | None:
        """Releasing drops the rope; holding keeps it, even once the player
        has stretched outside the influence radius. A held charge with no rope
        yet grabs the first node that comes into reach, so flying into a field
        with the button already down still connects."""
        if charge is Charge.NEUTRAL:
            self._latch_index = None
            return None

        current = self.latched_node()
        if current is not None:
            return current

        node = self.active_node()
        if node is None:
            return None
        self._latch_index = self.room.nodes.index(node)
        return node

    def step(self, charge: Charge) -> None:
        """Advance one fixed timestep. No-op once dead."""
        if self.dead:
            return

        ax = 0.0
        ay = self.gravity_y  # mass is fixed at 1.0, so force == acceleration

        node = self._update_latch(charge)
        if node is not None:
            fx, fy = charge_force(self.x, self.y, node, charge, self.params,
                                  ignore_radius=True)
            ax += fx
            ay += fy

        self.vx += ax * self.dt
        self.vy += ay * self.dt

        # Horizontal and downward speed are bounded separately, never as one
        # |v| clamp. An isotropic clamp rescales the whole vector, so the
        # downward velocity gravity keeps adding gets paid for out of the
        # player's horizontal velocity — every swing bleeds its carry while
        # total speed sits pinned at the cap. Upward speed is left uncapped
        # so a slingshot can still fling.
        if abs(self.vx) > self.speed_max:
            self.vx = math.copysign(self.speed_max, self.vx)
        if self.vy > self.fall_speed_max:
            self.vy = self.fall_speed_max

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
