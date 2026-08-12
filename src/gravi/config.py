"""Default tunable values for Gravi. Everything in TUNABLES is live-adjustable
in-game via the HUD overlay (see render/hud.py); the values here are only the
starting point a session begins from."""

from __future__ import annotations

from typing import NamedTuple

# Display
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 720
TARGET_FPS = 60

# Simulation. 240 Hz because orbits under a central force integrate more
# accurately at higher rates, and a point mass is cheap enough to afford it.
PHYS_HZ = 240
PHYS_DT = 1.0 / PHYS_HZ
MAX_STEPS_PER_FRAME = 12  # avoid a spiral of death after a long stall

# Palette — near-black field, everything else is emitted light.
COLOR_BG = (5, 6, 11)
COLOR_NODE = (80, 240, 255)      # cyan: an anchor you can use
COLOR_CORE = (235, 255, 255)     # the solid, lethal centre
COLOR_PLAYER = (255, 240, 120)
COLOR_BEAM_ATTRACT = (80, 240, 255)
COLOR_BEAM_REPEL = (255, 120, 200)
COLOR_TRAIL = (120, 180, 255)
COLOR_HUD = (200, 220, 235)

# Trail
TRAIL_MAX_POINTS = 900  # ~15 s at 60 fps


class TunableSpec(NamedTuple):
    default: float
    step: float
    lo: float
    hi: float


# Live-tunable simulation values. Name -> (default, step, min, max).
# The HUD iterates this dict in insertion order.
#
# TUNABLES itself must never be mutated directly — it is the process-wide
# set of starting points. Callers that need to adjust values in place (e.g.
# the HUD overlay in render/hud.py) take a per-session copy via
# default_tunables() and mutate that instead.
TUNABLES: dict[str, TunableSpec] = {
    # Orbital period is 2*pi/sqrt(k_attract) and is independent of orbit size.
    "k_attract":     TunableSpec(15.0,   0.5,   0.5,  60.0),
    "k_repel":       TunableSpec(15.0,   0.5,   0.5, 120.0),
    "force_max":     TunableSpec(4500.0, 100.0, 100.0, 20000.0),
    "gravity_y":     TunableSpec(500.0,  25.0, -2000.0, 4000.0),
    "speed_max":     TunableSpec(600.0,  50.0,  100.0, 8000.0),
    "player_radius": TunableSpec(7.0,    1.0,    2.0,   40.0),
}


def default_tunables() -> dict[str, float]:
    """A fresh mutable name -> value mapping seeded from TUNABLES defaults."""
    return {name: spec.default for name, spec in TUNABLES.items()}
