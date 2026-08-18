"""Neon drawing primitives.

Light is the ruleset in Gravi (spec section 7): hue is charge, the glow ring
IS the influence radius, and beam intensity IS force magnitude. There is no
separate HUD for any of that.

Performance note that matters for the browser build: glow is expensive if you
generate gradients every frame, so every glow is baked once into a surface,
cached by (colour, radius), and blitted with BLEND_ADD. Sprites are only worth
it for a filled disc. A thin ring is drawn directly instead — a sprite for one
would be a square of mostly-black pixels, and compositing that costs far more
than rasterising the annulus.

**Intensity lives in RGB magnitude, never in an alpha channel.** BLEND_ADD is
BLEND_RGB_ADD: it adds the source RGB to the destination and does not look at
the source alpha at all. Setting a colour to `(*rgb, 40)` and compositing it
additively therefore draws it at full brightness — the alpha is computed and
silently discarded. This module got that wrong once, and the result was flat
discs instead of glow, identical active and inactive rings, and a beam whose
brightness never moved with force. Every surface here is a plain (non-alpha)
Surface on black, because black adds nothing under BLEND_ADD, and every
intensity is folded into the colour with `_scaled`.
"""

from __future__ import annotations

import math

import pygame

from .. import config
from ..field import Charge

_glow_cache: dict[tuple[tuple[int, int, int], int], pygame.Surface] = {}
_scratch: pygame.Surface | None = None

TRAIL_BANDS = 10


def _scaled(color: tuple[int, int, int], intensity: float) -> tuple[int, int, int]:
    """Fold an intensity in 0..1 into the colour itself.

    This is the additive-blending equivalent of setting alpha, and the only
    one that works: see the module docstring.
    """
    i = 0.0 if intensity < 0.0 else (1.0 if intensity > 1.0 else intensity)
    return (int(color[0] * i), int(color[1] * i), int(color[2] * i))


def _scratch_layer(size: tuple[int, int], rect: pygame.Rect) -> pygame.Surface:
    """One reusable full-screen layer, cleared only across `rect`.

    Plain, not SRCALPHA: additive compositing needs no alpha channel, and a
    non-alpha blit is materially cheaper.

    Clearing and compositing the whole 1280x720 surface to draw one beam is
    ~1.8M pixel operations for a handful of lit pixels, which is the obvious
    WASM cliff. Only the region actually drawn is touched; anything stale
    outside `rect` is never composited, so it cannot leak.

    Callers MUST blit their result before anyone else calls this — it is a
    single shared buffer, not a pool.
    """
    global _scratch
    if _scratch is None or _scratch.get_size() != size:
        _scratch = pygame.Surface(size)
    _scratch.fill((0, 0, 0), rect)
    return _scratch


def _composite(surface: pygame.Surface, layer: pygame.Surface,
               rect: pygame.Rect) -> None:
    """Additively composite just the drawn region."""
    rect = rect.clip(surface.get_rect())
    if rect.width <= 0 or rect.height <= 0:
        return
    surface.blit(layer, rect.topleft, rect, special_flags=pygame.BLEND_ADD)


def _glow_sprite(color: tuple[int, int, int], radius: int) -> pygame.Surface:
    """A radial falloff disc, baked once. Blit with BLEND_ADD."""
    key = (color, radius)
    cached = _glow_cache.get(key)
    if cached is not None:
        return cached

    size = radius * 2
    surface = pygame.Surface((size, size))
    for step in range(radius, 0, -1):
        # Quadratic falloff reads closer to real light than a linear ramp.
        t = step / radius
        pygame.draw.circle(surface, _scaled(color, (1.0 - t) ** 2),
                           (radius, radius), step)
    _glow_cache[key] = surface
    return surface


def _glow_at(surface: pygame.Surface, sx: float, sy: float,
             color: tuple[int, int, int], radius: int) -> None:
    """Glow at a point already in screen space."""
    sprite = _glow_sprite(color, radius)
    surface.blit(sprite, (int(sx) - radius, int(sy) - radius),
                 special_flags=pygame.BLEND_ADD)


def draw_glow(surface: pygame.Surface, x: float, y: float,
              color: tuple[int, int, int], radius: int, camera) -> None:
    _glow_at(surface, *camera.to_screen(x, y), color, radius)


def draw_node(surface: pygame.Surface, node, is_active: bool, camera) -> None:
    """Influence ring at `node.radius`, lethal core at `node.core_radius`.

    The ring is drawn straight onto the screen rather than blitted from a
    baked sprite. A sprite has to be a square of (2r+4)^2 pixels to hold a
    circle, so compositing five 240px rings additively touched 1.00M pixels
    per frame to light 0.014M — a 72x overdraw, measured 9.3x slower than
    drawing the annulus directly. What that costs is additive accumulation
    where two rings overlap; at these brightnesses over a near-black field
    the difference is a few units per channel.
    """
    # Only the centre transforms. Circles are rotation-invariant, which is
    # why rotating at draw time costs almost nothing here.
    sx, sy = camera.to_screen(node.x, node.y)
    pygame.draw.circle(surface,
                       _scaled(config.COLOR_NODE, (110 if is_active else 40) / 255.0),
                       (int(sx), int(sy)), int(node.radius), width=2)

    _glow_at(surface, sx, sy, config.COLOR_NODE,
             int(node.core_radius * (4 if is_active else 3)))
    pygame.draw.circle(surface, config.COLOR_CORE,
                       (int(sx), int(sy)), int(node.core_radius))


def draw_beam(surface: pygame.Surface, px: float, py: float, node,
              charge: Charge, force_magnitude: float, force_max: float,
              camera) -> None:
    """Thickness and brightness track force magnitude, so the player reads
    F = k*r off the screen without ever being told it."""
    if charge is Charge.NEUTRAL:
        return

    strength = max(0.0, min(1.0, force_magnitude / force_max)) if force_max > 0 else 0.0
    color = (config.COLOR_BEAM_ATTRACT if charge is Charge.ATTRACT
             else config.COLOR_BEAM_REPEL)
    width = max(1, int(1 + strength * 7))
    tint = _scaled(color, (60 + strength * 195) / 255.0)

    ax, ay = camera.to_screen(px, py)
    bx, by = camera.to_screen(node.x, node.y)
    pad = width + 2
    rect = pygame.Rect(int(min(ax, bx)) - pad, int(min(ay, by)) - pad,
                       int(abs(bx - ax)) + 2 * pad,
                       int(abs(by - ay)) + 2 * pad)
    layer = _scratch_layer(surface.get_size(), rect)
    pygame.draw.line(layer, tint, (ax, ay), (bx, by), width)
    _composite(surface, layer, rect)


def draw_player(surface: pygame.Surface, x: float, y: float, radius: float,
                camera) -> None:
    sx, sy = camera.to_screen(x, y)
    _glow_at(surface, sx, sy, config.COLOR_PLAYER, int(radius * 5))
    pygame.draw.circle(surface, config.COLOR_PLAYER, (int(sx), int(sy)), int(radius))


def draw_chamber(surface: pygame.Surface, chamber, camera,
                 is_current: bool) -> None:
    """The corridor outline. Dim for neighbours, brighter for the one you are
    in, so the seam is legible without a HUD element."""
    points = [camera.to_screen(x, y) for x, y in chamber.outline()]
    colour = _scaled(config.COLOR_CHAMBER, (42 if is_current else 18) / 255.0)
    pygame.draw.lines(surface, colour, True, points, 2)


def draw_arrow(surface: pygame.Surface, chamber, camera,
               is_current: bool = True) -> None:
    """The exit arrow spans the chamber's FULL far side, so it reads as a
    threshold you cross rather than a target you aim at. Chevrons point along
    next_direction, which is where gravity will pull once you are through."""
    a, b = (camera.to_screen(*point) for point in chamber.arrow_endpoints())
    pygame.draw.line(surface, _scaled(config.COLOR_ARROW,
                                      (204 if is_current else 90) / 255.0),
                     a, b, 3)

    dx, dy = camera.direction_to_screen(*chamber.next_direction)
    ux, uy = -dy, dx
    colour = _scaled(config.COLOR_ARROW, (242 if is_current else 102) / 255.0)
    width, height = surface.get_size()
    half = chamber.params.half_width
    for k in range(-2, 3):
        cx, cy = camera.to_screen(*chamber.world(chamber.params.depth,
                                                 k * half * 0.42))
        if not (-60 <= cx <= width + 60 and -60 <= cy <= height + 60):
            continue
        pygame.draw.lines(surface, colour, False, [
            (cx + ux * 13 - dx * 10, cy + uy * 13 - dy * 10),
            (cx + dx * 10, cy + dy * 10),
            (cx - ux * 13 - dx * 10, cy - uy * 13 - dy * 10),
        ], 3)


def draw_trail(surface: pygame.Surface, points, camera) -> None:
    """Fades from tail to head so orbit shape is legible as a drawn line.

    The fade is drawn in TRAIL_BANDS constant-brightness bands rather than
    per segment. One `draw.line` per segment means one Python-level call per
    segment every frame, and that loop was the single most expensive thing in
    the frame; `draw.lines` takes the whole band in one call. Banding is
    invisible at these alphas — consecutive segments differ by under two
    levels out of 255.
    """
    points = tuple(camera.to_screen(x, y) for x, y in points)
    total = len(points)
    if total < 2:
        return

    pad = 3
    left = min(p[0] for p in points)
    right = max(p[0] for p in points)
    top = min(p[1] for p in points)
    bottom = max(p[1] for p in points)
    rect = pygame.Rect(int(left) - pad, int(top) - pad,
                       int(right - left) + 2 * pad, int(bottom - top) + 2 * pad)

    layer = _scratch_layer(surface.get_size(), rect)
    for band in range(TRAIL_BANDS):
        low = band * (total - 1) // TRAIL_BANDS
        high = (band + 1) * (total - 1) // TRAIL_BANDS
        segment = points[low:high + 1]  # +1 so consecutive bands join up
        if len(segment) < 2:
            continue
        t = (band + 0.5) / TRAIL_BANDS
        pygame.draw.lines(layer, _scaled(config.COLOR_TRAIL,
                                         (8 + 120 * t * t) / 255.0),
                          False, segment, 2)
    _composite(surface, layer, rect)


def force_magnitude(fx: float, fy: float) -> float:
    return math.hypot(fx, fy)
