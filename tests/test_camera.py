import math

import pytest

from gravi import config
from gravi.gravity import GravityState
from gravi.render.camera import Camera, chambers_in_view


def test_identity_at_angle_zero():
    cam = Camera.identity()
    assert cam.to_screen(120.0, -45.0) == pytest.approx((120.0, -45.0))


def test_the_followed_point_lands_on_the_eye():
    cam = Camera(1280, 720)
    cam.update(500.0, -300.0, angle=1.1, rotating=True)
    assert cam.to_screen(500.0, -300.0) == pytest.approx(cam.eye)


def test_rotation_carries_gravity_onto_screen_down_at_every_step():
    """Spec 3.3's required test. This invariant is the whole justification for
    rotating the camera at all, and it is the one the prototype got backwards."""
    g = GravityState(flip_duration=0.3)
    cam = Camera(1280, 720)
    g.flip_by(1)
    for _ in range(200):
        g.advance(1.0 / 240.0)
        cam.update(0.0, 0.0, angle=g.angle, rotating=True)
        gx, gy = g.direction()
        sx, sy = cam.direction_to_screen(gx, gy)
        assert (sx, sy) == pytest.approx((0.0, 1.0), abs=1e-9)


def test_fixed_camera_does_not_rotate():
    """Fixed means the world is not turned. It does not mean the eye is
    centred — see the lead tests below, and amendment A3."""
    cam = Camera(1280, 720)
    for angle in (0.0, 0.4, math.pi / 2, math.pi):
        cam.update(0.0, 0.0, angle=angle, rotating=False)
        assert cam.to_screen(cam._ox + 100.0, cam._oy) == pytest.approx(
            (cam.eye[0] + 100.0, cam.eye[1]))


def test_a_zero_lead_restores_the_strictly_centred_camera():
    """A3 reverses 5.2 by making the lead a knob, not by deleting the framing
    5.2 asked for: lead 0 is still exactly a dead-centre camera that does not
    move when gravity turns."""
    cam = Camera(1280, 720)
    eyes = []
    for angle in (0.0, 0.4, math.pi / 2, math.pi):
        cam.update(0.0, 0.0, angle=angle, rotating=False, lead=0.0)
        eyes.append(cam.eye)
    assert len(set(eyes)) == 1
    assert eyes[0] == (640.0, 360.0)


def test_rotating_camera_sits_back_from_centre():
    cam = Camera(1280, 720)
    cam.update(0.0, 0.0, angle=0.0, rotating=True)
    assert cam.eye[1] < 360.0        # more of the fall ahead is visible


def test_screen_to_world_round_trips():
    cam = Camera(1280, 720)
    cam.update(310.0, -90.0, angle=0.7, rotating=True)
    assert cam.to_world(*cam.to_screen(12.0, 34.0)) == pytest.approx((12.0, 34.0))


# --- field of view ------------------------------------------------------
# The knob exists so you can see far enough ahead to plan a grab before you
# arrive, rather than reacting to what enters a 1:1 window. It is a draw-time
# scale only: the simulation never learns about it (core spec 8.1).


def test_the_default_view_is_one_to_one():
    cam = Camera(1280, 720)
    cam.update(0.0, 0.0, angle=0.0, rotating=False, lead=0.0)
    assert cam.to_screen(100.0, 0.0) == pytest.approx((740.0, 360.0))
    assert cam.scale_length(100.0) == pytest.approx(100.0)


def test_a_wider_view_width_scales_the_world_down():
    cam = Camera(1280, 720)
    cam.update(0.0, 0.0, angle=0.0, rotating=False, view_width=2560.0, lead=0.0)
    # 2560 world units across a 1280px window is half scale, so the point
    # 1280 units to the right lands on the right edge instead of far past it.
    assert cam.to_screen(1280.0, 0.0) == pytest.approx((1280.0, 360.0))


def test_a_wider_view_brings_a_point_ahead_onto_the_screen():
    """This is the whole point of the knob: something too far ahead to see at
    1:1 becomes visible, which is what makes it plannable."""
    cam = Camera(1280, 720)
    ahead = (0.0, 700.0)

    cam.update(0.0, 0.0, angle=0.0, rotating=False, lead=0.0)
    assert cam.to_screen(*ahead)[1] > 720.0

    cam.update(0.0, 0.0, angle=0.0, rotating=False, view_width=2560.0, lead=0.0)
    assert cam.to_screen(*ahead)[1] <= 720.0


def test_lengths_scale_with_the_view():
    """Radii are world lengths. If they stayed in pixels, widening the view
    would grow every node relative to the corridor it sits in."""
    cam = Camera(1280, 720)
    cam.update(0.0, 0.0, angle=0.0, rotating=False, view_width=2560.0, lead=0.0)
    assert cam.scale_length(200.0) == pytest.approx(100.0)


def test_screen_to_world_round_trips_when_the_view_is_widened():
    """The editor turns mouse pixels back into world points through this."""
    cam = Camera(1280, 720)
    cam.update(310.0, -90.0, angle=0.7, rotating=True, view_width=1900.0)
    assert cam.to_world(*cam.to_screen(12.0, 34.0)) == pytest.approx((12.0, 34.0))


def test_widening_the_view_never_moves_the_eye():
    """The two knobs stay independent: view_width changes how much you can see
    and camera_lead changes where you sit, and neither leaks into the other."""
    cam = Camera(1280, 720)
    for angle in (0.0, 0.4, math.pi):
        eyes = set()
        for view_width in (1280.0, 1900.0, 2560.0):
            cam.update(0.0, 0.0, angle=angle, rotating=False,
                       view_width=view_width, lead=0.25)
            eyes.add(cam.eye)
            assert cam.to_screen(0.0, 0.0) == pytest.approx(cam.eye)
        assert len(eyes) == 1


def test_the_rotating_lead_is_tunable():
    cam = Camera(1280, 720)
    cam.update(0.0, 0.0, angle=0.0, rotating=True, lead=0.0)
    assert cam.eye == pytest.approx((640.0, 360.0))
    cam.update(0.0, 0.0, angle=0.0, rotating=True, lead=0.30)
    assert cam.eye == pytest.approx((640.0, 144.0))


def test_the_lead_is_screen_space_so_the_two_knobs_stay_independent():
    cam = Camera(1280, 720)
    cam.update(0.0, 0.0, angle=0.0, rotating=True, lead=0.2, view_width=2560.0)
    assert cam.eye == pytest.approx((640.0, 216.0))




def test_the_visible_span_matches_the_one_to_one_window_by_default():
    """Unchanged framing must draw exactly the chambers it drew before: the
    one behind, the one you are in, and two ahead."""
    assert chambers_in_view(5, 1280.0, 1600.0) == range(4, 8)


def test_the_visible_span_widens_for_a_wide_view_of_shallow_chambers():
    """Widening the view is pointless if the corridor ahead is not drawn into.
    Nodes are drawn over this same span, so an outline can never appear with
    its node field missing — that would be an empty corridor to plan against."""
    wide = chambers_in_view(5, 3200.0, 800.0)
    assert wide.stop > chambers_in_view(5, 1280.0, 800.0).stop


def test_the_visible_span_never_runs_below_the_first_chamber():
    assert chambers_in_view(0, 1280.0, 1600.0).start == 0


# --- the fixed camera leads along gravity (amendment A3) ----------------


def test_the_fixed_camera_leads_along_gravity_not_along_screen_up():
    """5.2 rejected a lead on the fixed camera because a lead fixed to
    screen-up flew the player into the screen edge as soon as gravity went
    sideways. Following gravity is what makes it safe: the extra room is always
    in front of the player, whichever way "in front" currently points."""
    cam = Camera(1280, 720)

    cam.update(0.0, 0.0, angle=0.0, rotating=False, lead=0.2)     # gravity down
    assert cam.eye[1] < 360.0 and cam.eye[0] == pytest.approx(640.0)

    cam.update(0.0, 0.0, angle=math.pi / 2, rotating=False, lead=0.2)  # right
    assert cam.eye[0] < 640.0 and cam.eye[1] == pytest.approx(360.0)

    cam.update(0.0, 0.0, angle=-math.pi / 2, rotating=False, lead=0.2)  # left
    assert cam.eye[0] > 640.0 and cam.eye[1] == pytest.approx(360.0)

    cam.update(0.0, 0.0, angle=math.pi, rotating=False, lead=0.2)   # gravity up
    assert cam.eye[1] > 360.0 and cam.eye[0] == pytest.approx(640.0)


def test_the_lead_gives_the_same_share_of_the_travel_axis_either_way():
    """A 16:9 window already puts more world ahead when you travel sideways
    than when you fall, which is why up-and-down chambers read worse. The lead
    is a fraction of the axis being travelled, so the framing rule is the same
    in both: half the axis plus the lead."""
    cam = Camera(1280, 720)

    cam.update(0.0, 0.0, angle=0.0, rotating=False, lead=0.25)
    down_ahead = (720.0 - cam.eye[1]) / 720.0

    cam.update(0.0, 0.0, angle=math.pi / 2, rotating=False, lead=0.25)
    right_ahead = (1280.0 - cam.eye[0]) / 1280.0

    assert down_ahead == pytest.approx(right_ahead)
    assert down_ahead == pytest.approx(0.75)


def test_the_fixed_eye_does_not_drift_while_gravity_is_settled():
    """The pan A3 accepts is the one that happens DURING a flip. A settled
    gravity must hold the eye perfectly still, or the camera is just moving."""
    cam = Camera(1280, 720)
    cam.update(0.0, 0.0, angle=math.pi / 2, rotating=False, lead=0.3)
    first = cam.eye
    for _ in range(10):
        cam.update(50.0, -20.0, angle=math.pi / 2, rotating=False, lead=0.3)
        assert cam.eye == first


def test_the_lead_never_puts_the_player_off_screen():
    cam = Camera(1280, 720)
    high = config.TUNABLES["camera_lead"].hi
    for angle in (0.0, math.pi / 4, math.pi / 2, math.pi, -math.pi / 2):
        for rotating in (True, False):
            cam.update(0.0, 0.0, angle=angle, rotating=rotating, lead=high)
            assert 0.0 < cam.eye[0] < 1280.0
            assert 0.0 < cam.eye[1] < 720.0
