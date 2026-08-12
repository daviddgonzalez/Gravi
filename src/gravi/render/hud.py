"""The tuning overlay. Text only, drawn straight over the world."""

from __future__ import annotations

import pygame

from .. import config

_font: pygame.font.Font | None = None

HELP_LINES = (
    "J / LMB attract    K / RMB repel    R restart",
    "TAB overlay   UP/DOWN select   LEFT/RIGHT adjust   SHIFT x10",
    "F5 save preset   F9 load preset   F8 defaults",
    "ALT+LMB drag node   ALT+RMB add   DEL remove   [ ] radius   , . core",
    "CTRL+S save room",
)


def _get_font() -> pygame.font.Font:
    """`Font(None, ...)` uses pygame's bundled font. SysFont is avoided
    deliberately: the browser build has no system font directory to search."""
    global _font
    if _font is None:
        _font = pygame.font.Font(None, 22)
    return _font


def draw(surface: pygame.Surface, tuning, status: str = "") -> None:
    font = _get_font()
    x, y = 16, 14
    line_height = 19

    def line(text: str, color=config.COLOR_HUD) -> None:
        nonlocal y
        surface.blit(font.render(text, True, color), (x, y))
        y += line_height

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
