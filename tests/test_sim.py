import math
from dataclasses import replace

import pytest

from gravi.chamber import ChamberChain, ChamberParams
from gravi.field import Charge, FieldParams, Node
from gravi.gravity import GravityState
from gravi.sim import World, charge_from_input

PARAMS = FieldParams(k_attract=8.0, k_repel=12.0, force_max=1e9)

# Slice 1's tests were written against a room with no corridor walls. One
# enormous chamber is that room: identical physics, no geometry in the way.
WIDE = ChamberParams(depth=1e6, half_width=1e6)


def chain_with(nodes, params=None):
    """A deterministic one-archetype chain whose first chamber holds exactly
    the nodes a test cares about."""
    chain = ChamberChain(seed=0, params=params or ChamberParams())
    chain.chambers[0] = replace(chain.chambers[0], nodes=tuple(nodes))
    return chain


def make_world(nodes=(), flip_duration=0.3, gravity=500.0, spawn=None,
               chamber_params=None, player_radius=7.0, speed_max=600.0,
               fall_speed_max=600.0):
    w = World(
        chain=chain_with(nodes, chamber_params),
        params=PARAMS,
        gravity=gravity,
        gravity_state=GravityState(flip_duration=flip_duration),
        player_radius=player_radius,
        speed_max=speed_max,
        fall_speed_max=fall_speed_max,
    )
    if spawn is not None:
        w.x, w.y = spawn
    return w


def lab_world(gravity=0.0, spawn=(300.0, 400.0), nodes=None,
              speed_max=1e9, fall_speed_max=1e9):
    """Slice 1's `make_world`, on one wide chamber instead of a room."""
    return make_world(
        nodes=nodes if nodes is not None else [Node(400.0, 400.0, 250.0, 18.0)],
        gravity=gravity, spawn=spawn, chamber_params=WIDE, player_radius=9.0,
        speed_max=speed_max, fall_speed_max=fall_speed_max)


# --- slice 1 regressions, ported onto the chain ---------------------------

def test_gravity_accelerates_the_player_downward():
    # Tall room so the out-of-bounds death check does not halt the fall before
    # a full second has elapsed.
    w = lab_world(gravity=1000.0, nodes=[])
    for _ in range(240):  # one second at 240 Hz
        w.step(Charge.NEUTRAL)
    assert w.vy == pytest.approx(1000.0, rel=1e-6)


def test_active_node_is_the_nearest_containing_node():
    near = Node(310.0, 400.0, 100.0, 10.0)
    far = Node(360.0, 400.0, 400.0, 10.0)
    w = lab_world(nodes=[far, near])
    assert w.active_node() is near


def test_active_node_is_none_outside_every_radius():
    w = lab_world(nodes=[Node(1000.0, 1000.0, 50.0, 10.0)])
    assert w.active_node() is None


def test_ties_break_on_lowest_index():
    a = Node(300.0, 350.0, 200.0, 10.0)
    b = Node(300.0, 450.0, 200.0, 10.0)  # same distance from spawn (300, 400)
    w = lab_world(nodes=[a, b])
    assert w.active_node() is a


def test_only_the_active_node_applies_force():
    # Two overlapping nodes pulling opposite ways. If both applied force they
    # would partially cancel; only the nearer one may contribute.
    near = Node(400.0, 400.0, 400.0, 10.0)   # 100px right of spawn
    far = Node(100.0, 400.0, 400.0, 10.0)    # 200px left of spawn
    w = lab_world(nodes=[far, near])
    assert w.active_node() is near
    w.step(Charge.ATTRACT)
    expected_ax = 8.0 * 100.0  # k_attract * r toward the near node, i.e. +x
    assert w.vx == pytest.approx(expected_ax * w.dt, rel=1e-9)
    assert w.vx > 0.0


def test_player_dies_on_core_contact():
    w = lab_world(spawn=(400.0, 400.0 - 30.0),
                   nodes=[Node(400.0, 400.0, 250.0, 18.0)])
    assert not w.dead
    for _ in range(240 * 3):
        w.step(Charge.ATTRACT)
        if w.dead:
            break
    assert w.dead


def test_reset_restores_spawn_state():
    w = lab_world(gravity=1000.0, nodes=[])
    for _ in range(100):
        w.step(Charge.NEUTRAL)
    w.reset()
    assert (w.x, w.y) == w.chain.current.world(60.0, 0.0)
    assert (w.vx, w.vy) == (0.0, 0.0)
    assert not w.dead


def test_simulation_is_deterministic():
    """Also stands in for the spec's replay-fidelity requirement in slice 1:
    the same input sequence replays to the same outcome. A full input recorder
    arrives with ghosts and the path map in later slices."""
    charges = [Charge.ATTRACT] * 300 + [Charge.NEUTRAL] * 120 + [Charge.REPEL] * 180

    def trace():
        w = lab_world(gravity=900.0)
        out = []
        for c in charges:
            w.step(c)
            out.append((w.x, w.y, w.vx, w.vy))
        return out

    assert trace() == trace()  # exact equality, not approx


def test_orbit_stays_bounded_for_ten_seconds():
    node = Node(400.0, 400.0, 400.0, 5.0)
    w = lab_world(nodes=[node])
    # Circular orbit for F = k*r needs v = r*sqrt(k); r = 100 here.
    w.vy = 100.0 * math.sqrt(8.0)
    distances = []
    for _ in range(240 * 10):
        w.step(Charge.ATTRACT)
        assert not w.dead
        distances.append(math.hypot(w.x - node.x, w.y - node.y))
    assert min(distances) > 90.0
    assert max(distances) < 110.0


def test_fall_speed_is_clamped():
    w = lab_world(gravity=10000.0, nodes=[], fall_speed_max=50.0)
    for _ in range(240):
        w.step(Charge.NEUTRAL)
    assert w.vy <= 50.0 + 1e-9


def test_horizontal_speed_is_clamped_independently():
    w = lab_world(gravity=0.0, nodes=[], speed_max=50.0)
    w.vx = 5000.0
    w.step(Charge.NEUTRAL)
    assert abs(w.vx) <= 50.0 + 1e-9
    w.vx = -5000.0
    w.step(Charge.NEUTRAL)
    assert w.vx >= -50.0 - 1e-9


def test_gravity_never_taxes_horizontal_carry():
    """The gripe this split exists to fix. Under a single isotropic |v| clamp,
    gravity buys its downward velocity with the player's horizontal velocity:
    launched flat at the cap, vx bled from 600 to 439 in one second while |v|
    sat pinned at 600. Horizontal carry must now be untouchable by gravity."""
    w = lab_world(gravity=500.0, nodes=[],
                   speed_max=600.0, fall_speed_max=600.0)
    w.vx = 600.0
    for _ in range(240):  # one second of falling
        w.step(Charge.NEUTRAL)
    assert w.vx == pytest.approx(600.0), "gravity stole horizontal speed"
    assert w.vy > 0.0, "test is meaningless unless the player is actually falling"


def test_upward_speed_is_not_capped_by_the_fall_limit():
    """A slingshot must be allowed to fling the player upward faster than
    terminal fall speed, or the launch the whole game is built on gets blunted."""
    w = lab_world(gravity=0.0, nodes=[], fall_speed_max=50.0)
    w.vy = -900.0
    w.step(Charge.NEUTRAL)
    assert w.vy == pytest.approx(-900.0)


def test_latch_survives_leaving_the_influence_radius():
    """The rope does not snap at the rim — it holds until the player lets go."""
    node = Node(400.0, 400.0, 150.0, 5.0)
    w = lab_world(nodes=[node])
    # Orbits under F = k*r are bound, with far semi-axis v/sqrt(k). At k=8
    # that needs v > 150*sqrt(8) = 424 px/s to reach past a 150px ring at all.
    w.vy = -800.0
    went_outside = False
    for _ in range(240):
        w.step(Charge.ATTRACT)
        assert not w.dead
        assert w.latched_node() is node, "the rope must never snap on its own"
        if math.hypot(w.x - node.x, w.y - node.y) > node.radius:
            went_outside = True
            assert w.active_node() is None, "outside every ring by the old rule"
    assert went_outside, "test is meaningless unless the player left the ring"


def test_releasing_drops_the_latch():
    node = Node(400.0, 400.0, 150.0, 5.0)
    w = lab_world(nodes=[node])
    w.vy = -800.0
    for _ in range(240):
        w.step(Charge.ATTRACT)
    assert w.latched_node() is node
    w.step(Charge.NEUTRAL)
    assert w.latched_node() is None


def test_latch_does_not_hand_off_to_a_nearer_node_while_held():
    """Flying into another node's ring must not steal the rope."""
    first = Node(300.0, 400.0, 120.0, 5.0)
    second = Node(900.0, 400.0, 400.0, 5.0)
    w = lab_world(spawn=(300.0, 350.0), nodes=[first, second])
    # Fast enough that the bound orbit around `first` reaches x=618, well
    # inside the second ring, which starts at x=500.
    w.vx = 900.0
    entered_second_ring = False
    for _ in range(240):
        w.step(Charge.ATTRACT)
        if w.dead:
            break
        if math.hypot(w.x - second.x, w.y - second.y) <= second.radius:
            entered_second_ring = True
            assert w.latched_node() is first
    assert entered_second_ring, "test is meaningless unless the second ring was entered"


def test_latch_forms_on_entry_when_the_charge_is_already_held():
    """Holding attract before reaching a node still grabs the first one met."""
    node = Node(400.0, 400.0, 100.0, 5.0)
    w = lab_world(spawn=(400.0, 100.0), nodes=[node])
    assert w.active_node() is None
    w.step(Charge.ATTRACT)
    assert w.latched_node() is None, "nothing in reach yet"
    w.vy = 300.0
    for _ in range(240):
        w.step(Charge.ATTRACT)
        if w.latched_node() is not None:
            break
    assert w.latched_node() is node


def test_a_push_breaks_at_the_rim_where_a_pull_holds():
    """The two ropes differ deliberately: attract holds past the rim, repel
    does not. Same room, same launch, same held button — only the charge
    changes, so this is the whole difference in one test."""
    node = Node(400.0, 400.0, 100.0, 5.0)

    def fly(charge):
        # Spawn inside the ring, or no rope can form in the first place.
        w = lab_world(spawn=(400.0, 350.0), nodes=[node])
        w.vy = -600.0  # heading away, straight out through the top of the ring
        for _ in range(120):
            w.step(charge)
        assert math.hypot(w.x - node.x, w.y - node.y) > node.radius, (
            "test is meaningless unless the player left the ring")
        return w

    assert fly(Charge.REPEL).latched_node() is None, "a push must break at the rim"
    assert fly(Charge.ATTRACT).latched_node() is node, "a pull must hold past it"


def test_a_broken_push_never_drags_the_player_back_in():
    """Belt and braces on the direction of the force. Once the rope is gone
    there is nothing to invert, but k_repel*(R - r) going negative past the rim
    was a real bug, so the outcome it produced stays asserted."""
    node = Node(400.0, 400.0, 100.0, 5.0)
    w = lab_world(spawn=(400.0, 350.0), nodes=[node])
    w.vy = -600.0
    for _ in range(120):
        w.step(Charge.REPEL)
    assert w.vy <= -600.0, "a push must never turn into a pull"


def test_a_broken_push_regrabs_on_re_entry_without_being_released():
    """Breaking at the rim must not require letting go to use the node again —
    holding push through an arc that falls back into the ring re-connects."""
    node = Node(400.0, 400.0, 100.0, 5.0)
    w = lab_world(spawn=(400.0, 350.0), nodes=[node], gravity=2000.0)
    w.vy = -600.0
    broke = False
    for _ in range(240):
        w.step(Charge.REPEL)
        if w.dead:
            break
        if w.latched_node() is None:
            broke = True
        elif broke:
            return  # re-latched while still holding
    assert broke, "test is meaningless unless the push broke first"
    raise AssertionError("the push never re-grabbed on re-entry")


def test_a_push_does_not_break_while_still_inside_the_ring():
    """Only leaving the ring breaks it — a push that fizzles out near the rim
    while still inside keeps its rope."""
    node = Node(400.0, 400.0, 250.0, 5.0)
    w = lab_world(spawn=(400.0, 300.0), nodes=[node])
    for _ in range(60):
        w.step(Charge.REPEL)
        assert math.hypot(w.x - node.x, w.y - node.y) <= node.radius
        assert w.latched_node() is node


def test_reset_clears_the_latch():
    node = Node(400.0, 400.0, 250.0, 18.0)
    w = lab_world(nodes=[node])
    w.step(Charge.ATTRACT)
    assert w.latched_node() is node
    w.reset()
    assert w.latched_node() is None


def test_latch_survives_the_node_being_moved_by_the_editor():
    """The editor replaces a Node in place while the player may be latched to
    it; the rope must follow the node, not a stale copy."""
    w = lab_world(nodes=[Node(400.0, 400.0, 250.0, 18.0)])
    w.step(Charge.ATTRACT)
    assert w.latched_node() is w.chain.current.nodes[0]
    w.chain.chambers[0] = replace(w.chain.chambers[0],
                                  nodes=(Node(500.0, 300.0, 250.0, 18.0),))
    w.step(Charge.ATTRACT)
    assert w.latched_node() is w.chain.current.nodes[0]
    assert (w.latched_node().x, w.latched_node().y) == (500.0, 300.0)


def test_latch_clears_when_the_node_is_deleted():
    w = lab_world(nodes=[Node(400.0, 400.0, 250.0, 18.0)])
    w.step(Charge.ATTRACT)
    assert w.latched_node() is not None
    w.chain.chambers[0] = replace(w.chain.chambers[0], nodes=())
    w.step(Charge.ATTRACT)
    assert w.latched_node() is None


def test_charge_from_input_maps_all_four_combinations():
    assert charge_from_input(True, False) is Charge.ATTRACT
    assert charge_from_input(False, True) is Charge.REPEL
    assert charge_from_input(False, False) is Charge.NEUTRAL
    assert charge_from_input(True, True) is Charge.NEUTRAL


# --- slice 2: gravity-relative clamps and the chamber chain ---------------

def test_clamp_reduces_to_slice_one_at_phi_zero():
    """Spec section 6: the gravity-relative clamp is a strict generalisation
    of slice 1's per-axis split, so at phi = 0 it must do exactly that."""
    w = make_world()
    w.vx, w.vy = 5000.0, 5000.0
    w.step(Charge.NEUTRAL)
    assert w.vx == pytest.approx(600.0)
    assert w.vy == pytest.approx(600.0)


def test_upward_speed_is_never_capped():
    w = make_world()
    w.vy = -5000.0
    w.step(Charge.NEUTRAL)
    assert w.vy < -4000.0


@pytest.mark.parametrize("turns", [0, 1, 2, 3])
def test_gravity_never_taxes_carry_at_any_orientation(turns):
    """The slice 1 finding, re-run rotated. An isotropic clamp bled carry from
    600 to 439 in one second while |v| sat pinned at the cap; the split clamp
    must leave carry untouched no matter which way gravity points."""
    w = make_world(flip_duration=0.0, chamber_params=WIDE)
    w.gravity_state.flip_by(turns)
    gx, gy = w.gravity_state.direction()
    px, py = gy, -gx
    w.vx, w.vy = px * 600.0, py * 600.0
    for _ in range(240):
        w.step(Charge.NEUTRAL)
        if w.dead:
            break
    carry = w.vx * px + w.vy * py
    assert carry == pytest.approx(600.0, abs=1.0)


def test_crossing_the_arrow_advances_and_turns_gravity():
    w = make_world(flip_duration=0.0)
    ch = w.chain.current
    turn = ch.turn
    w.x, w.y = ch.world(ch.params.depth - 1.0, 0.0)
    w.vx, w.vy = ch.direction[0] * 600.0, ch.direction[1] * 600.0
    for _ in range(10):
        w.step(Charge.NEUTRAL)
        if w.chain.at == 1:
            break
    assert w.chain.at == 1
    assert not w.dead
    assert w.gravity_state.target_turns == -turn      # spec 3.3's sign trap
    assert w.gravity_state.direction() == pytest.approx(w.chain.current.direction, abs=1e-9)


def _seek_chamber(w, turning: bool):
    """Walk the chain to the next chamber that does (or does not) turn.

    Which chambers turn is a property of the run's cadence now, so a test that
    wants one of each has to go and find them rather than assume chamber 0.
    """
    for _ in range(80):
        if (w.chain.current.turn != 0) == turning:
            return w.chain.current
        w.chain.advance()
    raise AssertionError(f"no chamber with turning={turning} in 80")


def test_entry_lateral_offset_is_zero_at_a_turn():
    """Spec 4.3: at a turn the old lateral axis becomes the new depth axis, so
    where you crossed becomes how deep you start — and offset is exactly
    zero."""
    for u in (-300.0, -50.0, 0.0, 120.0, 400.0):
        w = make_world(flip_duration=0.0)
        ch = _seek_chamber(w, turning=True)
        start = w.chain.at
        w.x, w.y = ch.world(ch.params.depth - 1.0, u)
        w.vx, w.vy = ch.direction[0] * 600.0, ch.direction[1] * 600.0
        for _ in range(10):
            w.step(Charge.NEUTRAL)
            if w.chain.at > start:
                break
        assert not w.dead, u
        _, offset = w.chain.current.local(w.x, w.y)
        assert offset == pytest.approx(0.0, abs=1e-9), u


def test_a_straight_seam_carries_the_offset_through():
    """A chamber that does not turn is a corridor that keeps going, so crossing
    its seam must not shunt the player back onto the centre line. 4.3's
    zero-offset guarantee is a property of TURNS specifically — which is also
    why the lane-clearance guarantee matters most at a turn, where every player
    arrives on the centre line."""
    for u in (-300.0, 120.0):
        w = make_world(flip_duration=0.0)
        ch = _seek_chamber(w, turning=False)
        start = w.chain.at
        w.x, w.y = ch.world(ch.params.depth - 1.0, u)
        w.vx, w.vy = ch.direction[0] * 600.0, ch.direction[1] * 600.0
        for _ in range(10):
            w.step(Charge.NEUTRAL)
            if w.chain.at > start:
                break
        assert w.chain.at > start, u
        assert not w.dead, u
        _, offset = w.chain.current.local(w.x, w.y)
        assert offset == pytest.approx(u, abs=1e-9), u


def test_crossing_outside_the_span_kills():
    w = make_world(flip_duration=0.0)
    ch = w.chain.current
    w.x, w.y = ch.world(ch.params.depth - 1.0, ch.params.half_width + 5.0)
    w.vx, w.vy = ch.direction[0] * 600.0, ch.direction[1] * 600.0
    for _ in range(10):
        w.step(Charge.NEUTRAL)
    assert w.dead
    assert w.chain.at == 0


def test_leaving_the_chamber_sideways_kills():
    w = make_world(flip_duration=0.0)
    ch = w.chain.current
    w.x, w.y = ch.world(400.0, 0.0)
    px, py = ch.perp
    w.vx, w.vy = px * 600.0, py * 600.0
    for _ in range(600):
        w.step(Charge.NEUTRAL)
        if w.dead:
            break
    assert w.dead


def test_being_thrown_back_out_of_the_entrance_kills():
    w = make_world(flip_duration=0.0, gravity=0.0)
    ch = w.chain.current
    w.vx, w.vy = -ch.direction[0] * 600.0, -ch.direction[1] * 600.0
    for _ in range(600):
        w.step(Charge.NEUTRAL)
        if w.dead:
            break
    assert w.dead


def test_core_contact_kills_in_a_neighbouring_chamber_too():
    """Rings and cores reach across the seam, so the chamber next door is
    lethal while you are still in this one.

    The node is planted just past the seam deliberately. Dropping the player
    onto a generated node of the next chamber instead put them a whole chamber
    depth beyond the arrow, where they died of leaving the corridor — the
    assertion passed without a core ever being touched.
    """
    w = make_world(flip_duration=0.0)
    ch = w.chain.current
    just_past = ch.world(ch.params.depth + 5.0, 0.0)
    w.chain.chambers[1] = replace(
        w.chain.by_index(1),
        nodes=(Node(just_past[0], just_past[1], 200.0, 18.0),))

    w.x, w.y = ch.world(ch.params.depth - 10.0, 0.0)
    w.vx = w.vy = 0.0
    w.step(Charge.NEUTRAL)

    assert w.chain.at == 0, "must still be in this chamber, not through the arrow"
    assert w.dead


def test_distance_accumulates_along_the_actual_path():
    w = make_world()
    start = (w.x, w.y)
    for _ in range(240):
        w.step(Charge.NEUTRAL)
    assert w.distance > math.dist(start, (w.x, w.y)) * 0.99
    assert w.distance > 0.0


def test_clearing_chambers_counts_and_retains_outlines():
    """The run must retain chamber geometry rather than discarding it behind
    the camera — the end-of-run path map draws the whole route."""
    w = make_world(flip_duration=0.0)
    for _ in range(3):
        ch = w.chain.current
        w.x, w.y = ch.world(ch.params.depth - 1.0, 0.0)
        w.vx, w.vy = ch.direction[0] * 600.0, ch.direction[1] * 600.0
        for _ in range(10):
            w.step(Charge.NEUTRAL)
            if w.chain.current is not ch:
                break
    assert not w.dead
    assert w.cleared == 3
    assert len(w.chain.outlines) == 3


def test_reset_settles_gravity_onto_the_chamber_and_never_opens_mid_flip():
    w = make_world()
    w.gravity_state.flip_by(1)
    assert not w.gravity_state.settled
    w.reset()
    assert w.gravity_state.settled
    assert w.gravity_state.direction() == pytest.approx(w.chain.current.direction, abs=1e-9)


def test_crossing_a_looping_chamber_puts_the_player_back_at_its_entrance():
    """Lab mode: the chain hands back a chamber whose entry is not where the
    last one ended, and the player must arrive at that entry. In the corridor
    the two coincide, so this rule is a no-op there."""
    from gravi.field import Node
    from gravi.room import LabChain, Room

    room = Room(spawn=(100.0, 60.0), nodes=[Node(400.0, 300.0, 40.0, 4.0)],
                width=1280.0, height=720.0)
    w = World(
        chain=LabChain(room),
        params=PARAMS,
        gravity=500.0,
        gravity_state=GravityState(flip_duration=0.0),
        player_radius=7.0,
        speed_max=600.0,
        fall_speed_max=600.0,
    )
    w.x, w.y = 640.0, 719.0
    w.vx, w.vy = 0.0, 600.0
    for _ in range(10):
        w.step(Charge.NEUTRAL)
        if w.cleared:
            break
    assert w.cleared == 1
    assert not w.dead
    t, _ = w.chain.current.local(w.x, w.y)
    assert t == pytest.approx(0.0, abs=1e-9)      # back at the entrance line
    assert w.gravity_state.target_turns == 0      # and gravity never turned
