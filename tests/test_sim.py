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


def test_charge_from_input_maps_all_four_combinations():
    assert charge_from_input(True, False) is Charge.ATTRACT
    assert charge_from_input(False, True) is Charge.REPEL
    assert charge_from_input(False, False) is Charge.NEUTRAL
    assert charge_from_input(True, True) is Charge.NEUTRAL
