"""The tuning overlay. Text only, drawn straight over the world."""

from __future__ import annotations

import pygame

from .. import config

_font: pygame.font.Font | None = None

HELP_LINES = (
    "J / LMB attract    K / RMB repel    R new run    C camera",
    "TAB overlay   UP/DOWN select   LEFT/RIGHT adjust   SHIFT x10",
    "F5 save preset   F9 load preset   F8 defaults",
    "ALT+LMB drag node   ALT+RMB add   DEL remove   [ ] radius   , . core",
    "CTRL+S save room",
)


_text_cache: dict[tuple[str, tuple[int, int, int]], pygame.Surface] = {}


def _get_font() -> pygame.font.Font:
    """`Font(None, ...)` uses pygame's bundled font. SysFont is avoided
    deliberately: the browser build has no system font directory to search."""
    global _font
    if _font is None:
        _font = pygame.font.Font(None, 22)
    return _font


def _text(text: str, color: tuple[int, int, int]) -> pygame.Surface:
    """Rasterised text, cached. `font.render` allocates a fresh surface every
    call, and the overlay draws a dozen-plus lines every frame while most of
    them change only when a value is edited."""
    key = (text, color)
    surface = _text_cache.get(key)
    if surface is None:
        surface = _get_font().render(text, True, color)
        if len(_text_cache) > 512:
            # Values change as they are swept, so this is unbounded in
            # principle. Dropping the whole cache is fine; it refills in a
            # frame.
            _text_cache.clear()
        _text_cache[key] = surface
    return surface


def draw(surface: pygame.Surface, tuning, status: str = "",
         fps: float | None = None, steps: int | None = None,
         run: str | None = None) -> None:
    x, y = 16, 14
    line_height = 19

    def line(text: str, color=config.COLOR_HUD) -> None:
        nonlocal y
        surface.blit(_text(text, color), (x, y))
        y += line_height

    if fps is not None:
        # `steps` is the diagnostic that matters, not the frame rate itself.
        # The loop can only afford MAX_STEPS_PER_FRAME physics steps per
        # frame; once it saturates, the leftover accumulator is discarded and
        # game time silently falls behind wall-clock time. Saturation, not a
        # low number, is the thing to react to — so it is called out in red.
        saturated = steps is not None and steps >= config.MAX_STEPS_PER_FRAME
        detail = "" if steps is None else f"   sim {steps}/{config.MAX_STEPS_PER_FRAME}"
        warning = "  SLOW MOTION — sim cannot keep up" if saturated else ""
        line(f"fps {fps:5.1f}{detail}{warning}",
             (255, 110, 110) if saturated else config.COLOR_HUD)

    if run is not None:
        # A playtester must never be unsure which camera mode they are judging.
        line(run, (255, 255, 255))

    line(f"orbit period  {tuning.orbital_period():6.2f} s   "
         f"(2*pi/sqrt(k_attract) — same at any orbit size)")
    y += 4

    for name in config.TUNABLES:
        is_selected = name == tuning.selected
        marker = ">" if is_selected else " "
        color = (255, 255, 255) if is_selected else config.COLOR_HUD
        line(f"{marker} {name:<14}{tuning.values[name]:10.2f}", color)

    y += 6
    for text in HELP_LINES:
        line(text, (120, 140, 160))

    if status:
        y += 6
        line(status, (255, 230, 140))
