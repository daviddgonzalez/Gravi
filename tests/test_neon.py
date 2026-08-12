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
from gravi.render.trail import Trail


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
    neon.draw_glow(screen, 400, 300, config.COLOR_PLAYER, 80)

    centre = brightness(screen, 400, 300)
    middle = brightness(screen, 400 + 40, 300)
    edge = brightness(screen, 400 + 72, 300)

    assert centre > middle > edge, (
        f"glow must fall off, got centre={centre} middle={middle} edge={edge}")


def test_the_active_node_is_visibly_brighter_than_an_inactive_one(screen):
    node = Node(400.0, 300.0, 120.0, 14.0)

    screen.fill(config.COLOR_BG)
    neon.draw_node(screen, node, is_active=True)
    active = peak_brightness(screen, 400 + 120, 300)

    screen.fill(config.COLOR_BG)
    neon.draw_node(screen, node, is_active=False)
    inactive = peak_brightness(screen, 400 + 120, 300)

    assert active > inactive, (
        f"active ring must read brighter, got active={active} inactive={inactive}")


def test_beam_brightness_tracks_force_magnitude(screen):
    node = Node(700.0, 300.0, 600.0, 12.0)
    samples = []
    for magnitude in (0.0, 2000.0, 4000.0):
        screen.fill(config.COLOR_BG)
        neon.draw_beam(screen, 100.0, 300.0, node, Charge.ATTRACT,
                       magnitude, 4000.0)
        samples.append(peak_brightness(screen, 400, 300))

    assert samples[0] < samples[1] < samples[2], (
        f"beam intensity must track force, got {samples}")


def test_the_trail_fades_from_tail_to_head(screen):
    trail = Trail(max_points=200)
    for i in range(200):
        trail.add(100.0 + i * 3.0, 300.0)  # straight line, x 100 -> 697

    screen.fill(config.COLOR_BG)
    neon.draw_trail(screen, trail.points())

    tail = peak_brightness(screen, 130, 300, window=3)
    head = peak_brightness(screen, 670, 300, window=3)

    assert head > tail, (
        f"trail must fade toward the tail, got head={head} tail={tail}")


def test_the_beam_is_tinted_by_charge(screen):
    node = Node(700.0, 300.0, 600.0, 12.0)

    screen.fill(config.COLOR_BG)
    neon.draw_beam(screen, 100.0, 300.0, node, Charge.ATTRACT, 4000.0, 4000.0)
    attract = screen.get_at((400, 300))[:3]

    screen.fill(config.COLOR_BG)
    neon.draw_beam(screen, 100.0, 300.0, node, Charge.REPEL, 4000.0, 4000.0)
    repel = screen.get_at((400, 300))[:3]

    # Attract is cyan (green-dominant), repel is pink (red-dominant).
    assert attract[1] > attract[0], f"attract beam should read cyan, got {attract}"
    assert repel[0] > repel[1], f"repel beam should read pink, got {repel}"
