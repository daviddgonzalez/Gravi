#!/usr/bin/env python3
"""Headless frame-cost probe.

Runs the real simulation and the real draw path against a dummy SDL video
driver and reports what a frame costs. No display, no window manager, no
vsync — so it runs in CI and on a build box, and the number it prints is
comparable run to run.

    SDL_VIDEODRIVER=dummy python tools/perf_probe.py --frames 600 --seed 1

The baseline to beat is about **1.10 ms** per frame, measured while rejecting
the rotate-the-finished-frame camera option (slice 2 spec 5.3).

Why the draw path and not just the simulation: the sim is a point mass and is
cheap. The renderer is where the budget goes — the trail alone is the single
largest item in the frame (config.TRAIL_SAMPLE_EVERY explains why it is
sampled rather than drawn per step). A probe that timed only World.step would
report a number that never moves and never warns anyone.

Determinism: the frame delta is fixed rather than measured, and the input is
scripted from a seeded PRNG, so the same --seed replays the same run. The
`checksum` line is what makes that testable — it is simulation state, not
timing, so it is stable across machines while the milliseconds are not.

NOTE (drift risk): main.py holds its draw sequence inline in the frame loop,
so there is no single function this probe can call. The draw block below is a
deliberate mirror of it. If main.py's draw order changes and this does not,
the probe keeps reporting a cost for a frame the game no longer draws. Keep
them in step.
"""

from __future__ import annotations

import argparse
import math
import os
import random
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# Must be set before pygame initialises its video subsystem, not after.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from gravi import config  # noqa: E402
from gravi.field import Charge, FieldParams, charge_force  # noqa: E402
from gravi.render import hud, neon  # noqa: E402
from gravi.render.trail import Trail  # noqa: E402
from gravi.room import load_room  # noqa: E402
from gravi.sim import World  # noqa: E402
from gravi.tuning import TuningState  # noqa: E402

ROOM_PATH = ROOT / "rooms" / "slice1.json"
RESPAWN_DELAY = 0.6
# Hold an input for a stretch of frames rather than re-rolling every frame:
# a per-frame coin flip never latches a node, so the beam would rarely draw
# and the probe would miss the most expensive thing on screen.
HOLD_FRAMES = 12


def build_world(room, tunables: dict[str, float]) -> World:
    return World(
        room=room,
        params=FieldParams(
            k_attract=tunables["k_attract"],
            k_repel=tunables["k_repel"],
            force_max=tunables["force_max"],
        ),
        gravity_y=tunables["gravity_y"],
        player_radius=tunables["player_radius"],
        speed_max=tunables["speed_max"],
        fall_speed_max=tunables["fall_speed_max"],
    )


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
    return ordered[index]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--frames", type=int, default=600,
                        help="frames to measure (default 600)")
    parser.add_argument("--seed", type=int, default=0,
                        help="PRNG seed for the scripted input (default 0)")
    parser.add_argument("--no-hud", action="store_true",
                        help="skip the HUD to isolate the game's own draw cost")
    parser.add_argument("--warmup", type=int, default=30,
                        help="unmeasured frames first, so font and glow caches "
                             "are warm (default 30)")
    args = parser.parse_args(argv)

    if args.frames <= 0:
        parser.error("--frames must be positive")

    rng = random.Random(args.seed)

    pygame.init()
    screen = pygame.display.set_mode((config.WINDOW_WIDTH, config.WINDOW_HEIGHT))

    tuning = TuningState(config.default_tunables())
    tunables = tuning.values
    room = load_room(ROOM_PATH)
    world = build_world(room, tunables)
    trail = Trail(config.TRAIL_MAX_POINTS)

    frame_dt = 1.0 / config.TARGET_FPS  # fixed, not measured: determinism
    accumulator = 0.0
    dead_timer = 0.0
    trail_sample = 0
    deaths = 0
    charge = Charge.NEUTRAL

    sim_times: list[float] = []
    draw_times: list[float] = []

    for frame in range(args.warmup + args.frames):
        measured = frame >= args.warmup

        if frame % HOLD_FRAMES == 0:
            charge = rng.choice([Charge.ATTRACT, Charge.ATTRACT,
                                 Charge.REPEL, Charge.NEUTRAL])

        # --- simulate, exactly as main.py's fixed-step accumulator does ---
        sim_start = time.perf_counter()
        accumulator += frame_dt
        steps = 0
        while accumulator >= world.dt and steps < config.MAX_STEPS_PER_FRAME:
            world.step(charge)
            accumulator -= world.dt
            steps += 1
            if not world.dead:
                trail_sample += 1
                if trail_sample >= config.TRAIL_SAMPLE_EVERY:
                    trail_sample = 0
                    trail.add(world.x, world.y)
        if steps == config.MAX_STEPS_PER_FRAME:
            accumulator = 0.0

        if world.dead:
            dead_timer += frame_dt
            if dead_timer >= RESPAWN_DELAY:
                world.reset()
                trail.clear()
                dead_timer = 0.0
                deaths += 1
        else:
            dead_timer = 0.0
        sim_elapsed = time.perf_counter() - sim_start

        # --- draw: a mirror of main.py's draw block, see the module note ---
        draw_start = time.perf_counter()
        screen.fill(config.COLOR_BG)
        neon.draw_trail(screen, trail.points())

        anchor = world.latched_node() or world.active_node()
        for node in room.nodes:
            neon.draw_node(screen, node, is_active=node is anchor)

        if anchor is not None and charge is not Charge.NEUTRAL and not world.dead:
            fx, fy = charge_force(
                world.x, world.y, anchor, charge, world.params,
                ignore_radius=(charge is Charge.ATTRACT
                               and world.latched_node() is not None))
            neon.draw_beam(screen, world.x, world.y, anchor, charge,
                           math.hypot(fx, fy), world.params.force_max)

        if not world.dead:
            neon.draw_player(screen, world.x, world.y, world.player_radius)

        if not args.no_hud:
            hud.draw(screen, tuning, "", fps=float(config.TARGET_FPS), steps=steps)

        pygame.display.flip()
        draw_elapsed = time.perf_counter() - draw_start

        if measured:
            sim_times.append(sim_elapsed * 1000.0)
            draw_times.append(draw_elapsed * 1000.0)

    pygame.quit()

    totals = [s + d for s, d in zip(sim_times, draw_times)]
    # Simulation state, not timing: identical on any machine for a given seed.
    checksum = f"{world.x:.6f},{world.y:.6f},{len(trail)},{deaths}"

    print(f"frames {args.frames}")
    print(f"seed {args.seed}")
    print(f"hud {'off' if args.no_hud else 'on'}")
    print(f"mean_ms {statistics.fmean(totals):.4f}")
    print(f"p95_ms {percentile(totals, 0.95):.4f}")
    print(f"max_ms {max(totals):.4f}")
    print(f"sim_mean_ms {statistics.fmean(sim_times):.4f}")
    print(f"draw_mean_ms {statistics.fmean(draw_times):.4f}")
    print(f"draw_p95_ms {percentile(draw_times, 0.95):.4f}")
    print(f"budget_frac {statistics.fmean(totals) / (1000.0 / config.TARGET_FPS):.4f}")
    print(f"checksum {checksum}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
