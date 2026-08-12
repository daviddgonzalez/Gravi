"""Neon drawing primitives.

Light is the ruleset in Gravi (spec section 7): hue is charge, the glow ring
IS the influence radius, and beam intensity IS force magnitude. There is no
separate HUD for any of that.

Performance note that matters for the browser build: glow is expensive if you
generate gradients every frame. Every glow here is baked once into a surface,
cached by (colour, radius), and blitted with BLEND_ADD.
"""

from __future__ import annotations

import math

import pygame

from .. import config
from ..field import Charge

_glow_cache: dict[tuple[tuple[int, int, int], int], pygame.Surface] = {}
_ring_cache: dict[tuple[int, int], pygame.Surface] = {}
_scratch: pygame.Surface | None = None


def _scratch_layer(size: tuple[int, int]) -> pygame.Surface:
    """One reusable full-screen alpha layer, cleared per use. Allocating a
    1280x720 SRCALPHA surface twice a frame is the obvious WASM cliff.

    Callers MUST blit their result before anyone else calls this — it is a
    single shared buffer, not a pool.
    """
    global _scratch
    if _scratch is None or _scratch.get_size() != size:
        _scratch = pygame.Surface(size, pygame.SRCALPHA)
    _scratch.fill((0, 0, 0, 0))
    return _scratch


def _glow_sprite(color: tuple[int, int, int], radius: int) -> pygame.Surface:
    """A radial falloff disc, baked once. Blit with BLEND_ADD."""
    key = (color, radius)
    cached = _glow_cache.get(key)
    if cached is not None:
        return cached

    size = radius * 2
    surface = pygame.Surface((size, size), pygame.SRCALPHA)
    for step in range(radius, 0, -1):
        # Quadratic falloff reads closer to real light than a linear ramp.
        t = step / radius
        alpha = int(255 * (1.0 - t) ** 2)
        if alpha <= 0:
            continue
        pygame.draw.circle(surface, (*color, alpha), (radius, radius), step)
    _glow_cache[key] = surface
    return surface


def draw_glow(surface: pygame.Surface, x: float, y: float,
              color: tuple[int, int, int], radius: int) -> None:
    sprite = _glow_sprite(color, radius)
    surface.blit(sprite, (int(x) - radius, int(y) - radius),
                 special_flags=pygame.BLEND_ADD)


def _ring_sprite(radius: int, alpha: int) -> pygame.Surface:
    """The influence-radius ring, baked and cached — it is redrawn every frame
    for every node, so it must never be reallocated per frame."""
    key = (radius, alpha)
    cached = _ring_cache.get(key)
    if cached is not None:
        return cached

    size = radius * 2 + 4
    surface = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.circle(surface, (*config.COLOR_NODE, alpha),
                       (radius + 2, radius + 2), radius, width=2)
    _ring_cache[key] = surface
    return surface


def draw_node(surface: pygame.Surface, node, is_active: bool) -> None:
    """Influence ring at `node.radius`, lethal core at `node.core_radius`."""
    radius = int(node.radius)
    ring = _ring_sprite(radius, 70 if is_active else 34)
    surface.blit(ring, (int(node.x) - radius - 2, int(node.y) - radius - 2),
                 special_flags=pygame.BLEND_ADD)

    draw_glow(surface, node.x, node.y, config.COLOR_NODE,
              int(node.core_radius * (4 if is_active else 3)))
    pygame.draw.circle(surface, config.COLOR_CORE,
                       (int(node.x), int(node.y)), int(node.core_radius))


def draw_beam(surface: pygame.Surface, px: float, py: float, node,
              charge: Charge, force_magnitude: float, force_max: float) -> None:
    """Thickness and alpha track force magnitude, so the player reads F = k*r
    off the screen without ever being told it."""
    if charge is Charge.NEUTRAL:
        return

    strength = max(0.0, min(1.0, force_magnitude / force_max)) if force_max > 0 else 0.0
    color = (config.COLOR_BEAM_ATTRACT if charge is Charge.ATTRACT
             else config.COLOR_BEAM_REPEL)
    width = max(1, int(1 + strength * 7))
    alpha = int(60 + strength * 195)

    layer = _scratch_layer(surface.get_size())
    pygame.draw.line(layer, (*color, alpha), (px, py), (node.x, node.y), width)
    surface.blit(layer, (0, 0), special_flags=pygame.BLEND_ADD)


def draw_player(surface: pygame.Surface, x: float, y: float, radius: float) -> None:
    draw_glow(surface, x, y, config.COLOR_PLAYER, int(radius * 5))
    pygame.draw.circle(surface, config.COLOR_PLAYER, (int(x), int(y)), int(radius))


def draw_trail(surface: pygame.Surface, points) -> None:
    """Fades from tail to head so orbit shape is legible as a drawn line."""
    points = tuple(points)
    if len(points) < 2:
        return
    layer = _scratch_layer(surface.get_size())
    total = len(points)
    for index in range(1, total):
        t = index / total
        alpha = int(8 + 120 * t * t)
        pygame.draw.line(layer, (*config.COLOR_TRAIL, alpha),
                         points[index - 1], points[index], 2)
    surface.blit(layer, (0, 0), special_flags=pygame.BLEND_ADD)


def force_magnitude(fx: float, fy: float) -> float:
    return math.hypot(fx, fy)
