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
from .field import Charge, FieldParams, Node, charge_force, surface_force
from .gravity import QUARTER, GravityState

# _rotate_on_rope's radius appears in two denominators: the unit radial
# direction (dx / r, dy / r) and the angular rate (speed / r). That makes a
# degenerate radius more dangerous here than field.charge_force's own
# near-zero guard (field._EPSILON, 1e-9) — that guard only protects a force
# that force_max separately caps, but there is no cap on an angular rate, so
# even a radius as "small" as 1e-6 turns one physics step into on the order
# of a million radians, aliasing the position to an effectively arbitrary
# point on the circle rather than merely raising. This needs a threshold
# several orders of magnitude larger than field's, so it is its own constant
# rather than a reuse of field._EPSILON.
_ROPE_RADIUS_EPSILON = 1e-3


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
        rigid_rope: bool = True,
        dt: float = PHYS_DT,
        wall_reach: float = 260.0,
        repel_charges_max: float = 3.0,
        repel_charge_seconds: float = 0.35,
        repel_min_spend: float = 0.5,
        repel_regen: float = 0.4,
        repel_attach_bonus: float = 0.5,
    ) -> None:
        self.chain = chain
        self.params = params
        self.gravity = gravity          # magnitude; direction lives in gravity_state
        self.gravity_state = gravity_state
        self.player_radius = player_radius
        self.speed_max = speed_max
        self.fall_speed_max = fall_speed_max
        # Playtest experiment (2026-08-20 design doc), played the same day:
        # the rigid rope won and is now the shipped behaviour, so a World
        # built without an explicit rigid_rope argument comes out rigid. The
        # spring is the option now, reachable behind `T` (main.py) or by
        # passing rigid_rope=False here.
        self.rigid_rope = rigid_rope
        self.dt = dt
        # Corridor walls are repel-able surfaces (2026-08-22 design doc). A
        # corridor always has one, which is what removes the no-verb moment
        # after a gravity turn.
        self.wall_reach = wall_reach

        # Repel's budget (2026-08-22 design doc 4). Attract has no cost and
        # must not gain one: solid cores already make holding attract fatal,
        # which is what makes the pull self-limiting. Nothing makes holding
        # repel fatal, because it pushes you away from the thing that would
        # punish you, so the push was unlimited by omission rather than design.
        self.repel_charges_max = repel_charges_max
        self.repel_charge_seconds = repel_charge_seconds
        self.repel_min_spend = repel_min_spend
        self.repel_regen = repel_regen
        self.repel_attach_bonus = repel_attach_bonus
        self.repel_charges = repel_charges_max
        self._press_paid: float | None = None   # None when no press is open
        self._press_used = 0.0
        self._bonus_latch: tuple[int, int] | None = None

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
        self.repel_charges = self.repel_charges_max
        self._press_paid = None
        self._press_used = 0.0
        self._bonus_latch = None
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

    def _resolve_latch(self, latch: tuple[int, int] | None) -> Node | None:
        """Resolve a (chamber index, node index) latch tuple back to the Node
        it names, or None if there is no such tuple, its chamber was culled
        behind the player, or the editor deleted the node out from under it.
        Shared by `latched_node` (for `_latch`) and the attach-bonus re-arm
        check (for `_bonus_latch`) — both are the same kind of stale-index
        problem."""
        if latch is None:
            return None
        chamber_index, node_index = latch
        chamber = self.chain.by_index(chamber_index)
        if chamber is None or node_index >= len(chamber.nodes):
            return None
        return chamber.nodes[node_index]

    def latched_node(self) -> Node | None:
        """The node currently roped to, or None. Tracked by (chamber, node)
        index rather than by value because `Node` is frozen and compares by
        value: the editor replaces a node in place when you drag it, and the
        rope must follow the node to its new position instead of pointing at a
        stale copy. The chamber index also lets a rope survive right up to the
        moment its chamber is culled behind the player."""
        node = self._resolve_latch(self._latch)
        if node is None:
            # Either there was no latch, or it was culled behind us, or the
            # editor deleted it out from under us — either way, forget it.
            self._latch = None
        return node

    def _within(self, node: Node) -> bool:
        return math.hypot(node.x - self.x, node.y - self.y) <= node.radius

    def _clear_stale_bonus_latch(self) -> None:
        """The attach bonus re-arms once the player has actually LEFT the
        ring of the node they were last paid for — not when they merely let
        go of the button. `_update_latch` drops `_latch` on every NEUTRAL
        frame regardless of whether the player left the node's ring, so
        keying the re-arm off `_latch`/button state let a stationary mash of
        ATTRACT on/off re-pay the bonus every cycle (a farmable, near-free
        charge tank next to any node). `_bonus_latch` now survives release
        and clears only when the node it names is gone (culled, or deleted
        by the editor) or the player is no longer within its ring — i.e. when
        the player actually did the work of leaving and can be paid again for
        coming back."""
        node = self._resolve_latch(self._bonus_latch)
        if node is None or not self._within(node):
            self._bonus_latch = None

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

        self._clear_stale_bonus_latch()
        if (charge is Charge.ATTRACT and node is not None
                and self._latch != self._bonus_latch):
            # Once per NEW latch, not per frame: grabbing is already how you
            # steer, and now it is also how you rearm. Re-arms only once the
            # player has left the node's ring (see _clear_stale_bonus_latch),
            # not merely released the button.
            self._bonus_latch = self._latch
            self.repel_charges = min(
                self.repel_charges_max,
                self.repel_charges + self.repel_attach_bonus)

        # Mass is fixed at 1.0, so force == acceleration.
        ax = gx * self.gravity
        ay = gy * self.gravity
        fx = fy = 0.0
        if charge is Charge.REPEL:
            # WALLS TAKE PRIORITY over nodes for a push. Reversed on 2026-08-23
            # by the author; the wall was the fallback until then. The rule a
            # player holds in their head is now "a push goes off the wall, and
            # only off a node when no wall is near" — which makes the emergency
            # out the same gesture everywhere, since a corridor always has a
            # wall. Consequence worth knowing: at wall_reach 260 against a
            # half_width of 460, walls win across the outer 260 units on each
            # side, so node-repel survives only in the middle ~400 of the
            # corridor and is now the rarer case.
            #
            # Still exactly one of the two, never both summed: whichever this
            # resolves to is the only push applied this step.
            #
            # This branch and the rigid rope are mutually exclusive by charge
            # value alone: rigid requires Charge.ATTRACT (see `rigid` above),
            # this branch requires Charge.REPEL. A player who releases a rigid
            # rope by switching to repel drops the latch on the same step and
            # can land straight in here with no residual rope state left
            # behind. That is correct, just non-obvious enough to write down.
            #
            # Known discontinuity, deliberately left for the playtest (design
            # doc §10): node repel is k*(radius - r), zero at the ring's rim
            # by construction. Wall repel is a function of an unrelated
            # quantity, distance to the corridor wall, so nothing makes the
            # handoff between the two continuous. Measured with shipped
            # constants (k_repel=15, force_max=4500, wall_reach=260,
            # half_width=460): a node at u=200 with radius=260 hands off from
            # a node force of 0.000 to a wall force of 3900.000 at the exact
            # step its latch breaks. Sampling 200 generated chambers (893
            # nodes) found 100% have a ring edge reaching into the wall_reach
            # band and 21.1% reach or pass the wall outright, so this is not
            # a rare corner case. Do NOT "fix" this by changing either force
            # law without a playtest verdict on whether it reads as the wall
            # taking over or as a snap — see the pinned regression test
            # `test_leaving_a_nodes_ring_near_a_wall_can_snap` in
            # tests/test_sim.py.
            #
            # `self.chain.current` (not the geometrically-nearer chamber) is
            # deliberate here, and it is only correct because both this call
            # and `_check_bounds`'s death check below key off the SAME
            # `chain.current` within one step, and `chain.advance()` cannot
            # run until after this force computation finishes. At a turn,
            # adjacent chamber boxes genuinely overlap in world space: a point
            # can be simultaneously (t=1500, u=-455) in the old chamber and
            # (t=455, u=-100) in the next. `chain.current` (the old chamber)
            # reports distance=5.0 here -- correctly dangerous, since |u|=455
            # is only 95 short of the death threshold of half_width +
            # side_grace = 550. The "geometrically real" next chamber would
            # report 360 -- falsely safe, suppressing the push exactly when
            # it is needed. A future refactor toward proper chamber-box
            # containment must not break this coupling without checking it.
            distance, normal = self.chain.current.nearest_wall(self.x, self.y)
            fx, fy = surface_force(distance, normal, self.params,
                                   self.wall_reach)
            if fx == 0.0 and fy == 0.0 and node is not None:
                # Out of the wall's reach, so the node is what is left. The
                # latch bookkeeping in _update_latch is unchanged either way:
                # a repel latch still forms and still breaks at the rim, it
                # simply may not be the thing pushing while a wall is nearer.
                fx, fy = charge_force(self.x, self.y, node, charge,
                                      self.params, ignore_radius=False)
        elif node is not None and not rigid:
            # Attract. It is allowed to act past the rim, because its rope
            # holds after the player stretches outside the ring.
            fx, fy = charge_force(self.x, self.y, node, charge, self.params,
                                  ignore_radius=True)

        pushing = False
        if charge is Charge.REPEL and (fx != 0.0 or fy != 0.0):
            # Only a push that would actually do something costs anything.
            pushing = self._open_or_continue_press()
            if not pushing:
                fx = fy = 0.0
                # A failed payment must close the press (design doc 4.1): if
                # the press stayed open here, `_press_used` would keep
                # growing every frame the button stays held while
                # `_press_paid` sits frozen at whatever the empty tank could
                # afford, so `overrun` grows without bound and every future
                # regen tick is immediately re-consumed trying to pay down a
                # press that is producing nothing. That stranded the player
                # until they physically released the button — exactly the
                # "emergency out unavailable at a flip" state 4.1 forbids.
                self._end_press()
        else:
            # A press cost is "settled when the press ends" (design doc 4):
            # the frame that closes it is still part of what the press paid
            # for, not idle time, so it must not also earn a regen tick — that
            # would refund a sliver of the floor it just finished paying. Only
            # a frame that finds no press already open is truly idle.
            settling = self._press_paid is not None
            self._end_press()
            pushing = settling

        ax += fx
        ay += fy

        if not pushing:
            # Regen and drain never fight over the same frame.
            #
            # This clamp is also what bites if `repel_charges_max` is swept
            # DOWN mid-run: banked charge above the new max is clipped on the
            # very next tick rather than eased off. Only reachable through
            # the live-tuning overlay, never through play, so it is a note
            # rather than a bug.
            self.repel_charges = min(
                self.repel_charges_max,
                self.repel_charges + self.repel_regen * self.dt)
        # A rigid rope supplies exactly the tension its constraint needs, so
        # the spring is NOT applied on top: two mechanisms pulling on one
        # radius would just fight. Gravity is still applied as a force
        # increment here even while rigid — _rotate_on_rope strips whatever
        # component of the resulting velocity turns out to be radial.

        self.vx += ax * self.dt
        self.vy += ay * self.dt

        self._clamp_speed(gx, gy)

        if rigid:
            nx, ny = self._rotate_on_rope(node)
        else:
            nx = self.x + self.vx * self.dt
            ny = self.y + self.vy * self.dt
        # Chord length, not arc length, even on a rigid rope: the relative
        # error is theta**2/24, negligible at the theta ~0.01 rad/step this
        # sim runs at — the same class of approximation this file already
        # makes everywhere else (see e.g. semi-implicit Euler's own error).
        self.distance += math.hypot(nx - self.x, ny - self.y)
        self.x, self.y = nx, ny
        self.elapsed += self.dt

        self._check_bounds()
        if not self.dead:
            self._check_cores()

    def _clamp_speed(self, gx: float, gy: float) -> None:
        """Bound fall and carry speed separately, never as one isotropic |v|
        clamp: an isotropic clamp rescales the whole vector, so the velocity
        gravity keeps adding gets paid for out of the player's carry — every
        swing bleeds it while total speed sits pinned at the cap. Fall is
        measured along the current gravity direction and carry perpendicular
        to it, so the split rotates with gravity instead of assuming a fixed
        world axis. Speed against gravity is left uncapped so a slingshot can
        still fling.
        """
        px, py = gy, -gx
        fall = self.vx * gx + self.vy * gy
        carry = self.vx * px + self.vy * py
        if fall > self.fall_speed_max:
            fall = self.fall_speed_max
        if abs(carry) > self.speed_max:
            carry = math.copysign(self.speed_max, carry)
        self.vx = fall * gx + carry * px
        self.vy = fall * gy + carry * py

    def _update_rope(self, node: Node | None, rigid: bool) -> None:
        """Record the radius at the moment of the grab, and forget it the
        moment the rope is gone. Keyed on the latch, so re-grabbing a different
        node measures a new radius rather than inheriting the old one.

        Editor-only gap: if the editor deletes a node and a different node
        reuses its (chamber, node) index, this stays keyed on that index and
        the rope keeps rotating around the new node at the old, now-stale
        radius until release. Unlike the spring path, which recovers the true
        distance every frame, the rigid path has no such self-correction. Not
        worth machinery for — it can only happen while editing, never during
        a run.
        """
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
        cos(theta) every step. At the corridor's own scale (theta ~0.01
        rad/step) that decayed a held swing's speed by ~12% over the ten
        seconds `test_a_rigid_rope_is_uniform_circular_motion` specifies to
        hold to 1e-6 — confirmed by running the literal algorithm before
        switching to this one. Rotating position and velocity together by the
        same angle is speed- and radius-preserving by construction, at any
        step size. The radial component removed here is the one true to the
        design intent: it still zeroes out on the first grabbed step (see
        `test_a_rigid_rope_strips_the_radial_velocity`) and does no work.
        """
        r = self._rope_radius
        if r < _ROPE_RADIUS_EPSILON:
            # Grabbed exactly at (or minutely off) the node's centre. The
            # radius is meaningless at this scale, so treat the rope as
            # inert this step rather than dividing by it: leave position and
            # velocity exactly as they arrived, no rotation, no strip. A
            # grab this close is inside every node's lethal core anyway, so
            # the death check on the very next step is how this actually
            # resolves — it just must not do it via an exception.
            return self.x, self.y
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

    def _open_or_continue_press(self) -> bool:
        """Pay for a repel that is about to produce force. False means it may
        not fire.

        The floor is deducted the instant the first force is produced, not on
        release, so a press can never drain past what it reserved. A press that
        produces NO force never reaches here and therefore costs nothing.
        """
        if self._press_paid is None:
            if self.repel_charges < self.repel_min_spend:
                return False
            self.repel_charges -= self.repel_min_spend
            self._press_paid = self.repel_min_spend
            self._press_used = 0.0

        self._press_used += self.dt / max(self.repel_charge_seconds, 1e-9)
        overrun = self._press_used - self._press_paid
        if overrun > 0.0:
            spend = min(overrun, self.repel_charges)
            self.repel_charges -= spend
            self._press_paid += spend
            if spend < overrun:
                return False            # tank ran dry mid-push
        return True

    def _end_press(self) -> None:
        self._press_paid = None
        self._press_used = 0.0

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
