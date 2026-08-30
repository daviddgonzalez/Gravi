import math

import pytest

from gravi.field import Charge, FieldParams, Node, charge_force, surface_force

PARAMS = FieldParams(k_attract=8.0, k_repel=12.0, force_max=1e9)
NODE = Node(x=100.0, y=100.0, radius=200.0, core_radius=18.0)


def test_attract_points_at_the_node_with_magnitude_k_times_r():
    # player 50px to the left of the node
    fx, fy = charge_force(50.0, 100.0, NODE, Charge.ATTRACT, PARAMS)
    assert fy == pytest.approx(0.0)
    assert fx == pytest.approx(8.0 * 50.0)  # positive = toward the node


def test_repel_points_away_with_magnitude_k_times_radius_minus_r():
    fx, fy = charge_force(50.0, 100.0, NODE, Charge.REPEL, PARAMS)
    assert fy == pytest.approx(0.0)
    assert fx == pytest.approx(-12.0 * (200.0 - 50.0))  # negative = away


def test_attract_is_strongest_at_the_rim_and_repel_at_the_core():
    near = charge_force(90.0, 100.0, NODE, Charge.ATTRACT, PARAMS)
    far = charge_force(-90.0, 100.0, NODE, Charge.ATTRACT, PARAMS)
    assert math.hypot(*far) > math.hypot(*near)

    near_r = charge_force(90.0, 100.0, NODE, Charge.REPEL, PARAMS)
    far_r = charge_force(-90.0, 100.0, NODE, Charge.REPEL, PARAMS)
    assert math.hypot(*near_r) > math.hypot(*far_r)


def test_no_force_outside_the_influence_radius():
    assert charge_force(1000.0, 100.0, NODE, Charge.ATTRACT, PARAMS) == (0.0, 0.0)
    assert charge_force(1000.0, 100.0, NODE, Charge.REPEL, PARAMS) == (0.0, 0.0)


def test_no_force_when_neutral():
    assert charge_force(50.0, 100.0, NODE, Charge.NEUTRAL, PARAMS) == (0.0, 0.0)


def test_force_is_clamped_to_force_max():
    clamped = FieldParams(k_attract=8.0, k_repel=12.0, force_max=100.0)
    fx, fy = charge_force(50.0, 100.0, NODE, Charge.ATTRACT, clamped)
    assert math.hypot(fx, fy) == pytest.approx(100.0)


def test_dead_centre_does_not_divide_by_zero():
    assert charge_force(100.0, 100.0, NODE, Charge.ATTRACT, PARAMS) == (0.0, 0.0)
    assert charge_force(100.0, 100.0, NODE, Charge.REPEL, PARAMS) == (0.0, 0.0)


def test_diagonal_force_is_aligned_with_the_offset():
    node = Node(x=0.0, y=0.0, radius=500.0, core_radius=10.0)
    fx, fy = charge_force(-30.0, -40.0, node, Charge.ATTRACT, PARAMS)
    # offset is (30, 40), length 50 -> unit (0.6, 0.8), magnitude 8 * 50 = 400
    assert fx == pytest.approx(400.0 * 0.6)
    assert fy == pytest.approx(400.0 * 0.8)


def test_a_surface_pushes_hardest_at_contact_and_nothing_at_the_reach():
    params = FieldParams(k_attract=15.0, k_repel=15.0, force_max=1e9)
    normal = (1.0, 0.0)

    at_contact = surface_force(0.0, normal, params, 260.0)
    assert at_contact == pytest.approx((15.0 * 260.0, 0.0))

    halfway = surface_force(130.0, normal, params, 260.0)
    assert halfway == pytest.approx((15.0 * 130.0, 0.0))

    assert surface_force(260.0, normal, params, 260.0) == (0.0, 0.0)
    assert surface_force(400.0, normal, params, 260.0) == (0.0, 0.0)


def test_a_surface_force_is_capped_like_every_other_force():
    params = FieldParams(k_attract=15.0, k_repel=15.0, force_max=100.0)
    force = surface_force(0.0, (1.0, 0.0), params, 260.0)
    assert force == pytest.approx((100.0, 0.0))


def test_a_surface_pushes_along_its_normal():
    params = FieldParams(k_attract=15.0, k_repel=15.0, force_max=1e9)
    force = surface_force(60.0, (0.0, -1.0), params, 260.0)
    assert force[0] == pytest.approx(0.0)
    assert force[1] < 0.0


def test_a_negative_distance_is_contact_not_a_pull():
    """A player past the wall must never be sucked further through it."""
    params = FieldParams(k_attract=15.0, k_repel=15.0, force_max=1e9)
    force = surface_force(-50.0, (1.0, 0.0), params, 260.0)
    assert force[0] > 0.0
    assert force == pytest.approx((15.0 * 260.0, 0.0))


def test_a_nan_distance_produces_no_force_rather_than_a_phantom_one():
    """A nan must degrade to nothing, not to a maximum-strength push.

    The naive spelling `distance >= reach` is False for nan, so it falls
    through to `max(0.0, distance)` — which returns 0.0, because `nan > 0.0`
    is also False — laundering the nan into "at contact" and handing back a
    full-strength, correctly-directed phantom force. That is worse than nan
    poisoning: a nan velocity is loud, this is indistinguishable downstream
    from a real wall hit. field.py is shared with the trainer, where unstable
    exploration produces nan positions routinely.
    """
    params = FieldParams(k_attract=15.0, k_repel=15.0, force_max=1e9)
    assert surface_force(float("nan"), (1.0, 0.0), params, 260.0) == (0.0, 0.0)


def test_an_infinite_distance_produces_no_force():
    params = FieldParams(k_attract=15.0, k_repel=15.0, force_max=1e9)
    assert surface_force(float("inf"), (1.0, 0.0), params, 260.0) == (0.0, 0.0)


def test_a_surface_pushes_along_a_diagonal_normal():
    """The axis-aligned test cannot catch a component swap that happens to
    preserve one axis; this pins both components to exact values."""
    params = FieldParams(k_attract=15.0, k_repel=15.0, force_max=1e9)
    normal = (0.6, 0.8)
    force = surface_force(60.0, normal, params, 260.0)
    magnitude = 15.0 * (260.0 - 60.0)
    assert force == pytest.approx((magnitude * 0.6, magnitude * 0.8))
