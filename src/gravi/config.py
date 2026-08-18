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
COLOR_CHAMBER = (80, 240, 255)    # the corridor you are inside
# Violet: hue is charge, and the exit arrow is not a charge, so it must not
# borrow the node cyan or the repel magenta.
COLOR_ARROW = (169, 123, 255)
COLOR_HUD = (200, 220, 235)

# Trail. Sampled every Nth physics step, not every step: at 240 Hz and 600
# px/s the player advances 2.5px per step, so sampling every step buys four
# points per barely-visible segment and costs four times the draw work. The
# render cost is per segment, and it is the single largest item in the frame.
TRAIL_SAMPLE_EVERY = 4
TRAIL_MAX_POINTS = 225  # ~3.75 s of trail at 240 Hz sampled every 4th step


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
    # A magnitude now, not a signed y component: the direction lives in
    # gravity.GravityState and turns a quarter at a time.
    "gravity":       TunableSpec(500.0,  25.0, -2000.0, 4000.0),
    # speed_max bounds HORIZONTAL speed only, and fall_speed_max bounds
    # downward speed. They are deliberately separate: a single isotropic
    # clamp on |v| makes gravity pay for its downward velocity out of the
    # player's horizontal velocity, so every swing silently loses its carry
    # while total speed sits pinned at the cap. Upward speed is uncapped —
    # capping it would blunt exactly the slingshot the game is built on.
    "speed_max":      TunableSpec(600.0,  50.0,  100.0, 8000.0),
    "fall_speed_max": TunableSpec(600.0,  50.0,  100.0, 8000.0),
    "player_radius":  TunableSpec(7.0,    1.0,    2.0,   40.0),
    # Spec 9's two open questions live here. flip_duration is what criterion 2
    # (comfortable at the one rate we ship) is judged on. chamber_depth is the
    # flip-FREQUENCY knob: at identical physics it sets how long a player
    # spends between arrows. 1150 gave ~26 gravity swaps per minute and read as
    # too hard; 1600 gives ~8.
    #
    # Both are COMFORT CONSTANTS, settled once by playtest (slice 2 spec,
    # amendment A1). Flip rate is not a difficulty axis: nothing may sample it
    # per chamber, ramp it with chamber index, or feed it to a difficulty
    # score. They are sliders here so a playtest can find the value, not so the
    # game can move it during a run.
    "flip_duration":  TunableSpec(0.30,   0.02,   0.0,     0.60),
    "chamber_depth":  TunableSpec(1600.0, 50.0,  800.0,  2600.0),
    "chamber_half_width": TunableSpec(460.0, 20.0, 260.0, 900.0),
}


def default_tunables() -> dict[str, float]:
    """A fresh mutable name -> value mapping seeded from TUNABLES defaults."""
    return {name: spec.default for name, spec in TUNABLES.items()}
