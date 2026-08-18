import math

import pytest

from gravi.chamber import QUARTER, ChamberChain, ChamberParams, make_chamber, rot

PARAMS = ChamberParams()


def test_rot_turns_a_direction_from_phi_to_phi_minus_a():
    """The sign trap from spec 3.3, pinned as an assertion rather than a
    comment. A direction at gravity-angle phi maps to phi - a."""
    down = (0.0, 1.0)
    turned = rot(down, QUARTER)
    assert turned == pytest.approx((-1.0, 0.0), abs=1e-12)
    assert math.atan2(turned[0], turned[1]) == pytest.approx(-QUARTER)


def test_local_coordinates_are_depth_and_offset():
    ch = make_chamber(0, (0.0, 0.0), (0.0, 1.0), PARAMS, seed=1)
    assert ch.local(0.0, 300.0) == pytest.approx((300.0, 0.0))
    # +perp of down is (-1, 0), so a point to the LEFT is positive offset
    assert ch.local(-50.0, 300.0) == pytest.approx((300.0, 50.0))


def test_world_and_local_round_trip():
    ch = make_chamber(3, (120.0, -40.0), (1.0, 0.0), PARAMS, seed=7)
    x, y = ch.world(400.0, -120.0)
    assert ch.local(x, y) == pytest.approx((400.0, -120.0))


def test_arrow_spans_the_full_far_side():
    ch = make_chamber(0, (0.0, 0.0), (0.0, 1.0), PARAMS, seed=2)
    a, b = ch.arrow_endpoints()
    assert math.dist(a, b) == pytest.approx(2 * PARAMS.half_width)
    for point in (a, b):
        t, _ = ch.local(*point)
        assert t == pytest.approx(PARAMS.depth)


def test_no_core_lies_in_the_centre_lane():
    """Spec 4.3: every chamber is entered at lateral offset exactly zero, so
    a core on the axis is an unavoidable death for a player who does nothing.
    The prototype shipped one at offset 18 and killed every run in 0.8 s."""
    clearance = PARAMS.lane_clear
    for seed in range(300):
        chain = ChamberChain(seed=seed, params=PARAMS)
        for ch in chain.chambers:
            for node in ch.nodes:
                _, u = ch.local(node.x, node.y)
                assert abs(u) >= clearance, (seed, ch.index, u)


def test_influence_rings_still_reach_the_lane():
    """Clear of cores is not enough — there must be something to grab from
    the lane, or the clearance rule just makes an empty corridor."""
    for seed in range(50):
        chain = ChamberChain(seed=seed, params=PARAMS)
        for ch in chain.chambers:
            reaching = [n for n in ch.nodes if abs(ch.local(n.x, n.y)[1]) < n.radius]
            assert reaching, (seed, ch.index)


def test_chambers_chain_without_gaps():
    chain = ChamberChain(seed=11, params=PARAMS)
    chain.ensure_ahead(10)
    for a, b in zip(chain.chambers, chain.chambers[1:]):
        assert b.entry == pytest.approx(a.exit_center)
        assert b.direction == pytest.approx(a.next_direction)
        assert b.index == a.index + 1


def test_turns_are_quarter_turns_only():
    chain = ChamberChain(seed=5, params=PARAMS)
    chain.ensure_ahead(20)
    assert {ch.turn for ch in chain.chambers} <= {1, -1}


def test_same_seed_same_chain():
    a = ChamberChain(seed=99, params=PARAMS)
    b = ChamberChain(seed=99, params=PARAMS)
    a.ensure_ahead(12)
    b.ensure_ahead(12)
    assert [ch.entry for ch in a.chambers] == [ch.entry for ch in b.chambers]
    assert [[(n.x, n.y, n.radius, n.core_radius) for n in ch.nodes] for ch in a.chambers] == \
           [[(n.x, n.y, n.radius, n.core_radius) for n in ch.nodes] for ch in b.chambers]


def test_advance_streams_ahead_and_retains_an_outline_behind():
    chain = ChamberChain(seed=3, params=PARAMS)
    for _ in range(8):
        chain.advance()
    assert chain.by_index(chain.at + 3) is not None      # still generating ahead
    assert chain.by_index(chain.at - 4) is None          # and culling behind
    assert len(chain.outlines) == 8          # one per cleared chamber, for the path map
    assert chain.current.index == 8


def test_nodes_near_covers_the_neighbours_only():
    chain = ChamberChain(seed=4, params=PARAMS)
    chain.ensure_ahead(6)
    chain.at = 3
    indices = {c for c, _, _ in chain.nodes_near()}
    assert indices == {2, 3, 4}
