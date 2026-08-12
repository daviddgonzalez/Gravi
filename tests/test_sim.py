import math

import pytest

from gravi.field import Charge, FieldParams, Node
from gravi.room import Room
from gravi.sim import World, charge_from_input

PARAMS = FieldParams(k_attract=8.0, k_repel=12.0, force_max=1e9)


def make_world(gravity_y=0.0, spawn=(300.0, 400.0), nodes=None,
               width=1280.0, height=720.0, speed_max=1e9):
    room = Room(
        spawn=spawn,
        nodes=nodes if nodes is not None else [Node(400.0, 400.0, 250.0, 18.0)],
        width=width,
        height=height,
    )
    return World(room=room, params=PARAMS, gravity_y=gravity_y,
                 player_radius=9.0, speed_max=speed_max)


def test_gravity_accelerates_the_player_downward():
    # Tall room so the out-of-bounds death check does not halt the fall before
    # a full second has elapsed.
    w = make_world(gravity_y=1000.0, nodes=[], height=1e6)
    for _ in range(240):  # one second at 240 Hz
        w.step(Charge.NEUTRAL)
    assert w.vy == pytest.approx(1000.0, rel=1e-6)


def test_active_node_is_the_nearest_containing_node():
    near = Node(310.0, 400.0, 100.0, 10.0)
    far = Node(360.0, 400.0, 400.0, 10.0)
    w = make_world(nodes=[far, near])
    assert w.active_node() is near


def test_active_node_is_none_outside_every_radius():
    w = make_world(nodes=[Node(1000.0, 1000.0, 50.0, 10.0)])
    assert w.active_node() is None


def test_ties_break_on_lowest_index():
    a = Node(300.0, 350.0, 200.0, 10.0)
    b = Node(300.0, 450.0, 200.0, 10.0)  # same distance from spawn (300, 400)
    w = make_world(nodes=[a, b])
    assert w.active_node() is a


def test_only_the_active_node_applies_force():
    # Two overlapping nodes pulling opposite ways. If both applied force they
    # would partially cancel; only the nearer one may contribute.
    near = Node(400.0, 400.0, 400.0, 10.0)   # 100px right of spawn
    far = Node(100.0, 400.0, 400.0, 10.0)    # 200px left of spawn
    w = make_world(nodes=[far, near])
    assert w.active_node() is near
    w.step(Charge.ATTRACT)
    expected_ax = 8.0 * 100.0  # k_attract * r toward the near node, i.e. +x
    assert w.vx == pytest.approx(expected_ax * w.dt, rel=1e-9)
    assert w.vx > 0.0


def test_player_dies_on_core_contact():
    w = make_world(spawn=(400.0, 400.0 - 30.0),
                   nodes=[Node(400.0, 400.0, 250.0, 18.0)])
    assert not w.dead
    for _ in range(240 * 3):
        w.step(Charge.ATTRACT)
        if w.dead:
            break
    assert w.dead


def test_player_dies_leaving_room_bounds():
    w = make_world(gravity_y=2000.0, nodes=[])
    for _ in range(240 * 5):
        w.step(Charge.NEUTRAL)
        if w.dead:
            break
    assert w.dead


def test_reset_restores_spawn_state():
    w = make_world(gravity_y=1000.0, nodes=[])
    for _ in range(100):
        w.step(Charge.NEUTRAL)
    w.reset()
    assert (w.x, w.y) == w.room.spawn
    assert (w.vx, w.vy) == (0.0, 0.0)
    assert not w.dead


def test_simulation_is_deterministic():
    """Also stands in for the spec's replay-fidelity requirement in slice 1:
    the same input sequence replays to the same outcome. A full input recorder
    arrives with ghosts and the path map in later slices."""
    charges = [Charge.ATTRACT] * 300 + [Charge.NEUTRAL] * 120 + [Charge.REPEL] * 180

    def trace():
        w = make_world(gravity_y=900.0, height=1e6)
        out = []
        for c in charges:
            w.step(c)
            out.append((w.x, w.y, w.vx, w.vy))
        return out

    assert trace() == trace()  # exact equality, not approx


def test_orbit_stays_bounded_for_ten_seconds():
    node = Node(400.0, 400.0, 400.0, 5.0)
    w = make_world(nodes=[node])
    # Circular orbit for F = k*r needs v = r*sqrt(k); r = 100 here.
    w.vy = 100.0 * math.sqrt(8.0)
    distances = []
    for _ in range(240 * 10):
        w.step(Charge.ATTRACT)
        assert not w.dead
        distances.append(math.hypot(w.x - node.x, w.y - node.y))
    assert min(distances) > 90.0
    assert max(distances) < 110.0


def test_speed_is_clamped_to_speed_max():
    w = make_world(gravity_y=10000.0, nodes=[], height=1e6, speed_max=50.0)
    for _ in range(240):
        w.step(Charge.NEUTRAL)
    assert math.hypot(w.vx, w.vy) <= 50.0 + 1e-9


def test_latch_survives_leaving_the_influence_radius():
    """The rope does not snap at the rim — it holds until the player lets go."""
    node = Node(400.0, 400.0, 150.0, 5.0)
    w = make_world(nodes=[node], height=1e6)
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
    w = make_world(nodes=[node], height=1e6)
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
    w = make_world(spawn=(300.0, 350.0), nodes=[first, second])
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
    w = make_world(spawn=(400.0, 100.0), nodes=[node], height=1e6)
    assert w.active_node() is None
    w.step(Charge.ATTRACT)
    assert w.latched_node() is None, "nothing in reach yet"
    w.vy = 300.0
    for _ in range(240):
        w.step(Charge.ATTRACT)
        if w.latched_node() is not None:
            break
    assert w.latched_node() is node


def test_latched_repel_never_inverts_into_a_pull():
    """k_repel*(R - r) goes negative past the rim; that must floor at zero,
    not turn a push into a pull."""
    node = Node(400.0, 400.0, 100.0, 5.0)
    # Spawn inside the ring, or no rope can form in the first place.
    w = make_world(spawn=(400.0, 350.0), nodes=[node], height=1e6)
    w.vy = -600.0  # heading away, straight out through the top of the ring
    for _ in range(120):
        w.step(Charge.REPEL)
    assert w.latched_node() is node
    assert math.hypot(w.x - node.x, w.y - node.y) > node.radius
    assert w.vy <= -600.0, "a latched repel must never drag the player back in"


def test_reset_clears_the_latch():
    node = Node(400.0, 400.0, 250.0, 18.0)
    w = make_world(nodes=[node])
    w.step(Charge.ATTRACT)
    assert w.latched_node() is node
    w.reset()
    assert w.latched_node() is None


def test_latch_survives_the_node_being_dragged_by_the_editor():
    """The editor replaces a Node in place while the player may be latched to
    it; the rope must follow the node, not a stale copy."""
    w = make_world(nodes=[Node(400.0, 400.0, 250.0, 18.0)])
    w.step(Charge.ATTRACT)
    assert w.latched_node() is w.room.nodes[0]
    w.room.nodes[0] = Node(500.0, 300.0, 250.0, 18.0)
    w.step(Charge.ATTRACT)
    assert w.latched_node() is w.room.nodes[0]
    assert (w.latched_node().x, w.latched_node().y) == (500.0, 300.0)


def test_latch_clears_when_the_node_is_deleted():
    w = make_world(nodes=[Node(400.0, 400.0, 250.0, 18.0)])
    w.step(Charge.ATTRACT)
    assert w.latched_node() is not None
    w.room.nodes.clear()
    w.step(Charge.ATTRACT)
    assert w.latched_node() is None


def test_charge_from_input_maps_all_four_combinations():
    assert charge_from_input(True, False) is Charge.ATTRACT
    assert charge_from_input(False, True) is Charge.REPEL
    assert charge_from_input(False, False) is Charge.NEUTRAL
    assert charge_from_input(True, True) is Charge.NEUTRAL
