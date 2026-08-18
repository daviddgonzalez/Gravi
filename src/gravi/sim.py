"""The simulation core: a point mass under gravity plus one central force.

No physics engine. The entire dynamic state is six floats and the only contact
test is circle-vs-circle, so a hand-written symplectic integrator is simpler,
exactly deterministic, fast enough for the offline validator to run thousands
of headless rollouts, and — unlike pymunk — it runs in the browser.

Semi-implicit (symplectic) Euler is used deliberately: a linear central force
is a harmonic oscillator, and symplectic integrators do not pump energy into
oscillators the way explicit Euler does, so orbits stay stable instead of
spiralling outward.

Slice 2 runs this on a streamed chamber chain rather than one hand-authored
room, and gravity became a rotating vector rather than a downward scalar. The
speed clamp moved with it: "fall" and "carry" are now measured along and
across the CURRENT gravity direction, because leaving the clamp in world axes
would silently undo slice 1's carry fix the moment the player is sideways.

World coordinates never rotate. The camera rotates at draw time instead, so
the offline validator simulates exactly the numbers the game does (spec 8.1).

Never import pygame here (see tests/test_purity.py).
"""

from __future__ import annotations

import math

from .chamber import ChamberChain
from .config import PHYS_DT
from .field import Charge, FieldParams, Node, charge_force
from .gravity import QUARTER, GravityState


class World:
    """Mutable simulation state for one run through a chamber chain."""

    def __init__(
        self,
        chain: ChamberChain,
        params: FieldParams,
        gravity: float,
        gravity_state: GravityState,
        player_radius: float,
        speed_max: float,
        fall_speed_max: float = math.inf,
        dt: float = PHYS_DT,
    ) -> None:
        self.chain = chain
        self.params = params
        self.gravity = gravity          # magnitude; direction lives in gravity_state
        self.gravity_state = gravity_state
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
        self.distance = 0.0
        self.cleared = 0
        self._latch: tuple[int, int] | None = None
        self.reset()

    def reset(self) -> None:
        """Spawn just inside the current chamber's entrance, with gravity
        already settled onto that chamber's direction — a run must never open
        mid-flip."""
        ch = self.chain.current
        self.x, self.y = ch.spawn()
        self.vx = 0.0
        self.vy = 0.0
        self.dead = False
        self.elapsed = 0.0
        self.distance = 0.0
        self.cleared = 0
        self._latch = None
        self.gravity_state.settle(
            round(math.atan2(ch.direction[0], ch.direction[1]) / QUARTER))

    def _nearest(self) -> tuple[tuple[int, int], Node] | None:
        """Nearest node whose influence radius contains the player, addressed
        by (chamber index, node index). Ties break on the lowest index so the
        choice is deterministic. Overlapping fields producing a net force is a
        deliberate late-game escalation (spec 3.6), not a slice 1 feature."""
        best: tuple[tuple[int, int], Node] | None = None
        best_distance = math.inf
        for chamber_index, node_index, node in self.chain.nodes_near():
            distance = math.hypot(node.x - self.x, node.y - self.y)
            if distance <= node.radius and distance < best_distance:
                best = ((chamber_index, node_index), node)
                best_distance = distance
        return best

    def active_node(self) -> Node | None:
        found = self._nearest()
        return None if found is None else found[1]

    def latched_node(self) -> Node | None:
        """The node currently roped to, or None. Tracked by (chamber, node)
        index rather than by value because `Node` is frozen and compares by
        value: the editor replaces a node in place when you drag it, and the
        rope must follow the node to its new position instead of pointing at a
        stale copy. The chamber index also lets a rope survive right up to the
        moment its chamber is culled behind the player."""
        if self._latch is None:
            return None
        chamber_index, node_index = self._latch
        chamber = self.chain.by_index(chamber_index)
        if chamber is None or node_index >= len(chamber.nodes):
            # Culled behind us, or the editor deleted it out from under us.
            self._latch = None
            return None
        return chamber.nodes[node_index]

    def _within(self, node: Node) -> bool:
        return math.hypot(node.x - self.x, node.y - self.y) <= node.radius

    def _update_latch(self, charge: Charge) -> Node | None:
        """Releasing always drops the rope. What holding does depends on which
        rope it is, because the two charges are different tools:

        ATTRACT is a long-range whip, and its rope holds until the player lets
        go, even once they have stretched well outside the influence radius.
        The ring says where you can *grab*, not how long you can hold. F = k*r
        keeps tightening out there, so the hold stays meaningful.

        REPEL is a close-range kick, and its rope breaks the moment the player
        leaves the ring. Its profile is k*(R - r), which is already zero at the
        rim: a push that survived past it would be a rope that pushes with no
        force, holding the player's one input hostage for nothing. Breaking on
        exit is also what makes the kick self-terminating — it ends exactly
        when it stops doing anything.

        A held charge with no rope yet grabs the first node that comes into
        reach, so flying into a field with the button already down still
        connects — and so a broken push re-grabs on re-entry without needing
        to be released first.
        """
        if charge is Charge.NEUTRAL:
            self._latch = None
            return None

        current = self.latched_node()
        if current is not None:
            if charge is not Charge.REPEL or self._within(current):
                return current
            # Pushed itself out of range: drop it and fall through, so an
            # overlapping ring can pick the push up on the same step.
            self._latch = None

        found = self._nearest()
        if found is None:
            return None
        self._latch, node = found
        return node

    def step(self, charge: Charge) -> None:
        """Advance one fixed timestep. Gravity keeps easing once dead, so the
        death screen settles upright instead of freezing mid-turn."""
        self.gravity_state.advance(self.dt)
        if self.dead:
            return

        gx, gy = self.gravity_state.direction()
        # Mass is fixed at 1.0, so force == acceleration.
        ax = gx * self.gravity
        ay = gy * self.gravity

        node = self._update_latch(charge)
        if node is not None:
            # Only attract is allowed to act past the rim; a latched repel is
            # inside its ring by construction, so the cutoff is a no-op there
            # and left in place as a guard rather than an exception.
            fx, fy = charge_force(self.x, self.y, node, charge, self.params,
                                  ignore_radius=charge is Charge.ATTRACT)
            ax += fx
            ay += fy

        self.vx += ax * self.dt
        self.vy += ay * self.dt

        # Fall and carry speed are bounded separately, never as one |v| clamp,
        # and in GRAVITY-RELATIVE axes. An isotropic clamp rescales the whole
        # vector, so the velocity gravity keeps adding gets paid for out of the
        # player's carry — every swing bleeds it while total speed sits pinned
        # at the cap. Speed against gravity is left uncapped so a slingshot can
        # still fling.
        px, py = gy, -gx
        fall = self.vx * gx + self.vy * gy
        carry = self.vx * px + self.vy * py
        if fall > self.fall_speed_max:
            fall = self.fall_speed_max
        if abs(carry) > self.speed_max:
            carry = math.copysign(self.speed_max, carry)
        self.vx = fall * gx + carry * px
        self.vy = fall * gy + carry * py

        nx = self.x + self.vx * self.dt
        ny = self.y + self.vy * self.dt
        self.distance += math.hypot(nx - self.x, ny - self.y)
        self.x, self.y = nx, ny
        self.elapsed += self.dt

        self._check_bounds()
        if not self.dead:
            self._check_cores()

    def _check_bounds(self) -> None:
        ch = self.chain.current
        t, u = ch.local(self.x, self.y)
        if t >= ch.params.depth:
            # Land exactly on the arrow plane rather than wherever the step
            # happened to overshoot to. Velocity is constant across a step, so
            # backing up along it is the exact crossing point, and it is what
            # makes spec 4.3 hold to the letter: the offset you crossed at
            # becomes your entry depth next door, and your entry offset there
            # is zero rather than a leftover fraction of a step.
            into = self.vx * ch.direction[0] + self.vy * ch.direction[1]
            if into > 0.0:
                back = (t - ch.params.depth) / into
                self.x -= self.vx * back
                self.y -= self.vy * back
                self.distance -= math.hypot(self.vx * back, self.vy * back)
                t, u = ch.local(self.x, self.y)
            if abs(u) > ch.params.half_width:
                self.dead = True            # left past the side, not through the arrow
                return
            # rot() carries a direction at angle phi to phi - a, so gravity
            # turns by the NEGATIVE of the corridor's geometric turn. Getting
            # this backwards spins the world the wrong way on every flip, which
            # looks almost right — which is how it survived a playtest once.
            self.gravity_state.flip_by(-ch.turn)
            self.chain.advance()
            self.cleared += 1
            self._latch = None              # no handoff across the seam

            # Arrive at the next chamber's entry, wherever the chain says that
            # is. In the corridor it is exactly the exit just crossed, so this
            # is a no-op and the seam stays continuous; a chain that loops back
            # on itself (the lab) uses it to put the player at the entrance
            # again without a second physics path.
            nxt = self.chain.current
            self.x += nxt.entry[0] - ch.exit_center[0]
            self.y += nxt.entry[1] - ch.exit_center[1]
        elif abs(u) > ch.params.half_width + ch.params.side_grace:
            self.dead = True
        elif t < -600.0:
            self.dead = True                # thrown back out of the entrance

    def _check_cores(self) -> None:
        for _, _, node in self.chain.nodes_near():
            lethal = node.core_radius + self.player_radius
            if math.hypot(node.x - self.x, node.y - self.y) <= lethal:
                self.dead = True
                return


def charge_from_input(attract_held: bool, repel_held: bool) -> Charge:
    """Map the two inputs to a charge. Holding both is neutral — pressing
    everything must never be the strongest option."""
    if attract_held and not repel_held:
        return Charge.ATTRACT
    if repel_held and not attract_held:
        return Charge.REPEL
    return Charge.NEUTRAL
