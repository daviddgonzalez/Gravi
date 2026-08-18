import math

import pytest

from gravi.gravity import QUARTER, GravityState, ease_in_out


def test_starts_settled_pointing_world_down():
    g = GravityState(flip_duration=0.3)
    assert g.settled
    assert g.direction() == pytest.approx((0.0, 1.0), abs=1e-12)


def test_flip_eases_and_lands_exactly_on_target():
    g = GravityState(flip_duration=0.3)
    g.flip_by(1)
    assert not g.settled
    assert g.angle == pytest.approx(0.0)
    for _ in range(300):
        g.advance(1.0 / 240.0)
    assert g.settled
    assert g.angle == pytest.approx(QUARTER, abs=1e-12)
    assert g.direction() == pytest.approx((1.0, 0.0), abs=1e-12)


def test_ease_is_monotonic_and_clamped():
    assert ease_in_out(-1.0) == 0.0
    assert ease_in_out(0.0) == 0.0
    assert ease_in_out(1.0) == 1.0
    assert ease_in_out(2.0) == 1.0
    values = [ease_in_out(i / 20.0) for i in range(21)]
    assert values == sorted(values)


def test_integer_target_never_drifts():
    """Hundreds of flips accumulating += pi/2 as floats would drift. The
    target is an integer count of quarter turns, so it cannot."""
    g = GravityState(flip_duration=0.05)
    for i in range(500):
        g.flip_by(1 if i % 3 else -1)
        for _ in range(20):
            g.advance(1.0 / 240.0)
        assert g.settled
    assert g.angle == g.target_turns * QUARTER
    assert isinstance(g.target_turns, int)


def test_half_turn_goes_clockwise():
    """Shortest path is ambiguous for 180 degrees, so the convention is
    clockwise on screen, which is DECREASING phi (screen y points down)."""
    g = GravityState(flip_duration=0.3)
    g.flip_to(2)
    g.advance(0.15)
    assert g.angle < 0.0
    for _ in range(300):
        g.advance(1.0 / 240.0)
    assert g.angle == pytest.approx(-2 * QUARTER, abs=1e-12)
    assert g.direction() == pytest.approx((0.0, -1.0), abs=1e-9)


def test_flip_to_takes_the_short_way_round():
    g = GravityState(flip_duration=0.1)
    g.flip_to(3)          # three quarter turns one way, one the other
    assert g.target_turns == -1


def test_zero_duration_snaps():
    g = GravityState(flip_duration=0.0)
    g.flip_by(1)
    assert g.settled
    assert g.angle == pytest.approx(QUARTER)


def test_settle_puts_gravity_on_an_orientation_with_no_ease():
    """A run must never open mid-flip, so spawning into a chamber sets
    gravity to that chamber's orientation outright."""
    g = GravityState(flip_duration=0.3)
    g.flip_by(1)
    g.settle(-1)
    assert g.settled
    assert g.target_turns == -1
    assert g.angle == pytest.approx(-QUARTER)


def test_vector_scales_the_direction():
    g = GravityState(flip_duration=0.3)
    assert g.vector(500.0) == pytest.approx((0.0, 500.0), abs=1e-12)
