import math

import pytest

from gravi.gravity import GravityState
from gravi.render.camera import Camera


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


def test_fixed_camera_does_not_rotate_and_does_not_pan():
    """Removing rotation is not enough: a fixed camera must have no
    gravity-driven motion of any kind, so the eye is dead centre and stays
    there. Leading in the gravity direction panned the view by up to twice the
    lead distance on every flip, which reads as a moving camera."""
    cam = Camera(1280, 720)
    eyes = []
    for angle in (0.0, 0.4, math.pi / 2, math.pi):
        cam.update(0.0, 0.0, angle=angle, rotating=False)
        eyes.append(cam.eye)
        assert cam.to_screen(100.0, 0.0) == pytest.approx((cam.eye[0] + 100.0, cam.eye[1]))
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
