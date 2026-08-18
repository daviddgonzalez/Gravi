"""Rendering tests for the intensity cues.

Spec section 7 makes light the ruleset: glow falls off with distance, the
active node is visibly brighter than the others, and beam intensity IS force
magnitude. All of it was previously encoded in an alpha channel and then
composited with BLEND_ADD, which reads only RGB — so every cue was computed
and discarded, and the screen showed flat discs and uniform lines.

These tests read actual pixels, because that bug was invisible to any test
that only checked the drawing code ran.
"""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
import pytest

from gravi import config
from gravi.field import Charge, Node
from gravi.render import neon
from gravi.render.camera import Camera
from gravi.render.trail import Trail

# An identity camera maps world coordinates straight to pixels, so every
# assertion below is the slice 1 assertion, unchanged: threading the camera
# through must not move a single pixel.
IDENTITY = Camera.identity()


@pytest.fixture(scope="module")
def screen():
    pygame.init()
    surface = pygame.display.set_mode((800, 600))
    yield surface
    pygame.quit()


def brightness(surface, x, y):
    r, g, b = surface.get_at((int(x), int(y)))[:3]
    return r + g + b


def peak_brightness(surface, x, y, window=4):
    """Brightest pixel in a small window, so a test does not fail over a
    one-pixel rasterisation offset."""
    return max(
        brightness(surface, x + dx, y + dy)
        for dx in range(-window, window + 1)
        for dy in range(-window, window + 1)
    )


def test_glow_falls_off_with_distance_from_the_centre(screen):
    screen.fill(config.COLOR_BG)
    neon.draw_glow(screen, 400, 300, config.COLOR_PLAYER, 80, IDENTITY)

    centre = brightness(screen, 400, 300)
    middle = brightness(screen, 400 + 40, 300)
    edge = brightness(screen, 400 + 72, 300)

    assert centre > middle > edge, (
        f"glow must fall off, got centre={centre} middle={middle} edge={edge}")


def test_the_active_node_is_visibly_brighter_than_an_inactive_one(screen):
    node = Node(400.0, 300.0, 120.0, 14.0)

    screen.fill(config.COLOR_BG)
    neon.draw_node(screen, node, is_active=True, camera=IDENTITY)
    active = peak_brightness(screen, 400 + 120, 300)

    screen.fill(config.COLOR_BG)
    neon.draw_node(screen, node, is_active=False, camera=IDENTITY)
    inactive = peak_brightness(screen, 400 + 120, 300)

    assert active > inactive, (
        f"active ring must read brighter, got active={active} inactive={inactive}")


def test_beam_brightness_tracks_force_magnitude(screen):
    node = Node(700.0, 300.0, 600.0, 12.0)
    samples = []
    for magnitude in (0.0, 2000.0, 4000.0):
        screen.fill(config.COLOR_BG)
        neon.draw_beam(screen, 100.0, 300.0, node, Charge.ATTRACT, magnitude, 4000.0, IDENTITY)
        samples.append(peak_brightness(screen, 400, 300))

    assert samples[0] < samples[1] < samples[2], (
        f"beam intensity must track force, got {samples}")


def test_the_trail_fades_from_tail_to_head(screen):
    trail = Trail(max_points=200)
    for i in range(200):
        trail.add(100.0 + i * 3.0, 300.0)  # straight line, x 100 -> 697

    screen.fill(config.COLOR_BG)
    neon.draw_trail(screen, trail.points(), IDENTITY)

    tail = peak_brightness(screen, 130, 300, window=3)
    head = peak_brightness(screen, 670, 300, window=3)

    assert head > tail, (
        f"trail must fade toward the tail, got head={head} tail={tail}")


def test_the_beam_is_tinted_by_charge(screen):
    node = Node(700.0, 300.0, 600.0, 12.0)

    screen.fill(config.COLOR_BG)
    neon.draw_beam(screen, 100.0, 300.0, node, Charge.ATTRACT, 4000.0, 4000.0, IDENTITY)
    attract = screen.get_at((400, 300))[:3]

    screen.fill(config.COLOR_BG)
    neon.draw_beam(screen, 100.0, 300.0, node, Charge.REPEL, 4000.0, 4000.0, IDENTITY)
    repel = screen.get_at((400, 300))[:3]

    # Attract is cyan (green-dominant), repel is pink (red-dominant).
    assert attract[1] > attract[0], f"attract beam should read cyan, got {attract}"
    assert repel[0] > repel[1], f"repel beam should read pink, got {repel}"


def test_the_chamber_outline_is_drawn_on_its_corners(screen):
    """The corridor has to be visible or the arrow is a line in the dark."""
    from gravi.chamber import ChamberParams, make_chamber

    params = ChamberParams(depth=400.0, half_width=150.0)
    chamber = make_chamber(0, (400.0, 100.0), (0.0, 1.0), params, seed=1)
    screen.fill(config.COLOR_BG)
    neon.draw_chamber(screen, chamber, IDENTITY, is_current=True)
    for x, y in chamber.outline():
        assert peak_brightness(screen, x, y) > brightness(screen, 400, 300)


def test_the_current_chamber_reads_brighter_than_a_neighbour(screen):
    from gravi.chamber import ChamberParams, make_chamber

    params = ChamberParams(depth=400.0, half_width=150.0)
    chamber = make_chamber(0, (400.0, 100.0), (0.0, 1.0), params, seed=1)
    corner = chamber.outline()[0]

    screen.fill(config.COLOR_BG)
    neon.draw_chamber(screen, chamber, IDENTITY, is_current=True)
    current = peak_brightness(screen, *corner)

    screen.fill(config.COLOR_BG)
    neon.draw_chamber(screen, chamber, IDENTITY, is_current=False)
    assert peak_brightness(screen, *corner) < current


def test_the_arrow_spans_the_whole_far_side(screen):
    """It is a threshold you cross, not a target you aim at (spec 4.2), so it
    must be lit end to end rather than marked in the middle."""
    from gravi.chamber import ChamberParams, make_chamber

    params = ChamberParams(depth=400.0, half_width=150.0)
    chamber = make_chamber(0, (400.0, 100.0), (0.0, 1.0), params, seed=1)
    screen.fill(config.COLOR_BG)
    neon.draw_arrow(screen, chamber, IDENTITY)
    a, b = chamber.arrow_endpoints()
    middle = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
    dark = brightness(screen, 400, 550)
    for point in (a, b, middle):
        assert peak_brightness(screen, *point) > dark


def test_a_widened_view_draws_a_smaller_node_ring(screen):
    """Node radii are world lengths, not pixels. If they did not scale, the
    influence ring would lie about where the force actually reaches once the
    view is widened — and the ring IS the ruleset (spec section 7)."""
    node = Node(400.0, 300.0, 120.0, 14.0)
    cam = Camera(800, 600)
    cam.update(400.0, 300.0, angle=0.0, rotating=False, view_width=1600.0)

    screen.fill(config.COLOR_BG)
    neon.draw_node(screen, node, is_active=False, camera=cam)

    dark = brightness(screen, 400, 560)
    assert peak_brightness(screen, 400 + 60, 300) > dark, "ring at half radius"
    assert peak_brightness(screen, 400 + 120, 300) <= dark, "nothing at full radius"


def test_a_widened_view_draws_a_smaller_player(screen):
    cam = Camera(800, 600)

    cam.update(400.0, 300.0, angle=0.0, rotating=False, view_width=1600.0)
    screen.fill(config.COLOR_BG)
    neon.draw_player(screen, 400.0, 300.0, 20.0, cam)
    widened = brightness(screen, 412, 300)

    cam.update(400.0, 300.0, angle=0.0, rotating=False)
    screen.fill(config.COLOR_BG)
    neon.draw_player(screen, 400.0, 300.0, 20.0, cam)
    assert brightness(screen, 412, 300) > widened
