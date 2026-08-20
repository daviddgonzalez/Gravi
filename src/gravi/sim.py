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
from .gravity import QUARTER, GravityMode, GravityState, apply_gravity


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
        gravity_mode: GravityMode = GravityMode.ALONG,
        rigid_rope: bool = False,
        dt: float = PHYS_DT,
    ) -> None:
        self.chain = chain
        self.params = params
        self.gravity = gravity          # magnitude; direction lives in gravity_state
        self.gravity_state = gravity_state
        self.player_radius = player_radius
        self.speed_max = speed_max
        self.fall_speed_max = fall_speed_max
        # Playtest experiments (2026-08-20 design doc). Both default to the
        # shipped behaviour, so a World built without them is unchanged.
        self.gravity_mode = gravity_mode
        self.rigid_rope = rigid_rope
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
        self._rope: tuple[int, int] | None = None    # which latch the rope is on
        self._rope_radius: float | None = None
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
        self._rope = None
        self._rope_radius = None
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
        node = self._update_latch(charge)
        rigid = (self.rigid_rope and node is not None
                 and charge is Charge.ATTRACT)
        self._update_rope(node, rigid)

        # Mass is fixed at 1.0, so force == acceleration. The node force is
        # integrated first and gravity second, because PERP_VELOCITY rotates
        # the finished velocity and has to see the one the node force produced.
        if node is not None and not rigid:
            # Only attract is allowed to act past the rim; a latched repel is
            # inside its ring by construction, so the cutoff is a no-op there
            # and left in place as a guard rather than an exception.
            fx, fy = charge_force(self.x, self.y, node, charge, self.params,
                                  ignore_radius=charge is Charge.ATTRACT)
            self.vx += fx * self.dt
            self.vy += fy * self.dt
        # A rigid rope supplies exactly the tension its constraint needs, so
        # the spring is NOT applied on top: two mechanisms pulling on one
        # radius would just fight.

        self.vx, self.vy = apply_gravity(self.gravity_mode, (gx, gy),
                                         self.vx, self.vy, self.gravity, self.dt)

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

        if rigid:
            nx, ny = self._rotate_on_rope(node)
        else:
            nx = self.x + self.vx * self.dt
            ny = self.y + self.vy * self.dt
        self.distance += math.hypot(nx - self.x, ny - self.y)
        self.x, self.y = nx, ny
        self.elapsed += self.dt

        self._check_bounds()
        if not self.dead:
            self._check_cores()

    def _update_rope(self, node: Node | None, rigid: bool) -> None:
        """Record the radius at the moment of the grab, and forget it the
        moment the rope is gone. Keyed on the latch, so re-grabbing a different
        node measures a new radius rather than inheriting the old one."""
        if not rigid:
            self._rope = None
            self._rope_radius = None
            return
        if self._rope != self._latch:
            self._rope = self._latch
            self._rope_radius = math.hypot(node.x - self.x, node.y - self.y)

    def _rotate_on_rope(self, node: Node) -> tuple[float, float]:
        """Advance along the held circle by an exact rotation about the node,
        rather than an Euler step reprojected onto the circle afterward.

        Deviation from the design doc's literal "project position, subtract
        radial velocity" wording: doing that with the current position (i.e.
        stripping the velocity's component along the radial direction found
        *after* the straight-line step) shrinks the tangential speed by
        cos(theta) every step, the same drift `apply_gravity`'s docstring
        already diagnoses for PERP_VELOCITY. At the corridor's own scale
        (theta ~0.01 rad/step) that decayed a held swing's speed by ~12% over
        the ten seconds `test_a_rigid_rope_is_uniform_circular_motion`
        specifies to hold to 1e-6 — confirmed by running the literal
        algorithm before switching to this one. Rotating position and
        velocity together by the same angle is speed- and radius-preserving
        by construction, at any step size, which is exactly why
        PERP_VELOCITY is implemented as a rotation rather than a perpendicular
        force. The radial component removed here is the one true to the
        design intent: it still zeroes out on the first grabbed step (see
        `test_a_rigid_rope_strips_the_radial_velocity`) and does no work.
        """
        r = self._rope_radius
        dx = self.x - node.x
        dy = self.y - node.y
        ux, uy = dx / r, dy / r
        radial = self.vx * ux + self.vy * uy
        self.vx -= radial * ux
        self.vy -= radial * uy
        speed = math.hypot(self.vx, self.vy)
        if speed < 1e-9:
            return self.x, self.y       # no tangential motion to rotate by
        theta = (speed / r) * self.dt
        if dx * self.vy - dy * self.vx < 0.0:
            theta = -theta               # match the current sense of travel
        c, s = math.cos(theta), math.sin(theta)
        nx = node.x + dx * c - dy * s
        ny = node.y + dx * s + dy * c
        self.vx, self.vy = self.vx * c - self.vy * s, self.vx * s + self.vy * c
        return nx, ny

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
