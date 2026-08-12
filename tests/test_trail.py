from gravi.render.trail import Trail


def test_trail_records_points_in_order():
    t = Trail(max_points=5)
    t.add(1.0, 2.0)
    t.add(3.0, 4.0)
    assert list(t.points()) == [(1.0, 2.0), (3.0, 4.0)]


def test_trail_drops_the_oldest_point_past_the_cap():
    t = Trail(max_points=3)
    for i in range(5):
        t.add(float(i), 0.0)
    assert list(t.points()) == [(2.0, 0.0), (3.0, 0.0), (4.0, 0.0)]


def test_clear_empties_the_trail():
    t = Trail(max_points=3)
    t.add(1.0, 1.0)
    t.clear()
    assert list(t.points()) == []
