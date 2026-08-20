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


def test_flipping_by_nothing_is_a_no_op():
    """Straight chambers cross their seam with turn 0. That must not start an
    ease to the angle gravity is already at: for flip_duration seconds the
    state would report itself mid-flip while nothing moved."""
    g = GravityState(flip_duration=0.3)
    g.advance(1.0)
    before = (g.angle, g.target_turns, g.settled)
    g.flip_by(0)
    assert (g.angle, g.target_turns, g.settled) == before


from gravi.gravity import GravityMode, apply_gravity


def test_along_is_the_old_behaviour():
    v = apply_gravity(GravityMode.ALONG, (0.0, 1.0), 30.0, 0.0, 500.0, 1.0 / 240.0)
    assert v == pytest.approx((30.0, 500.0 / 240.0))


def test_perp_corridor_pushes_across_the_gravity_axis():
    """perp(g) with the same handedness as chamber.perp: (-gy, gx)."""
    v = apply_gravity(GravityMode.PERP_CORRIDOR, (0.0, 1.0), 0.0, 0.0,
                      500.0, 1.0 / 240.0)
    assert v == pytest.approx((-500.0 / 240.0, 0.0))


def test_perp_corridor_adds_nothing_along_gravity():
    gx, gy = 0.0, 1.0
    vx, vy = 120.0, 40.0
    for _ in range(500):
        vx, vy = apply_gravity(GravityMode.PERP_CORRIDOR, (gx, gy), vx, vy,
                               500.0, 1.0 / 240.0)
    assert vx * gx + vy * gy == pytest.approx(40.0)


def test_perp_velocity_never_changes_speed():
    """The whole point of the mode. Adding a perpendicular acceleration each
    step instead of rotating walks the velocity off its circle and the speed
    creeps up — invisibly, and in exactly the direction of the complaint this
    mode exists to answer."""
    vx, vy = 300.0, -120.0
    start = math.hypot(vx, vy)
    for _ in range(10_000):
        vx, vy = apply_gravity(GravityMode.PERP_VELOCITY, (0.0, 1.0), vx, vy,
                               500.0, 1.0 / 240.0)
    assert math.hypot(vx, vy) == pytest.approx(start, rel=1e-9)


def test_perp_velocity_turns_the_heading():
    vx, vy = 400.0, 0.0
    before = math.atan2(vy, vx)
    for _ in range(240):                      # one second
        vx, vy = apply_gravity(GravityMode.PERP_VELOCITY, (0.0, 1.0), vx, vy,
                               500.0, 1.0 / 240.0)
    turned = math.atan2(vy, vx) - before
    # omega = magnitude / speed, and speed is preserved, so one second of it.
    assert turned == pytest.approx(500.0 / 400.0, rel=1e-3)


def test_perp_velocity_falls_back_when_stationary():
    """Perpendicular to nothing is undefined, and a player who stopped would
    have nothing left to start them moving: the mode would be a soft-lock."""
    v = apply_gravity(GravityMode.PERP_VELOCITY, (0.0, 1.0), 0.0, 0.0,
                      500.0, 1.0 / 240.0)
    assert v == pytest.approx((0.0, 500.0 / 240.0))


def test_modes_cycle_with_wraparound():
    mode = GravityMode.ALONG
    seen = []
    for _ in range(4):
        seen.append(mode)
        mode = mode.next()
    assert seen == [GravityMode.ALONG, GravityMode.PERP_CORRIDOR,
                    GravityMode.PERP_VELOCITY, GravityMode.ALONG]
