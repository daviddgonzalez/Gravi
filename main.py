"""Gravi entry point.

The loop is async because pygbag (the browser packager) drives the frame loop
through the JS event loop: without `await asyncio.sleep(0)` each frame the
browser tab locks up. Costs nothing natively, impossible to retrofit cheaply.
"""

from __future__ import annotations

import sys
from pathlib import Path

# pygbag runs main.py straight from the packaged directory with no install
# step, so the src/ layout that `pip install -e .` resolves natively is
# invisible in the browser: `import gravi` fails, pygbag then hunts for a
# PyPI package named gravi, 404s, and the canvas stays grey. Putting src/ on
# the path here fixes the browser and is a no-op natively.
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import asyncio  # noqa: E402
import math  # noqa: E402

import pygame  # noqa: E402

from gravi import config  # noqa: E402
from gravi.field import Charge, FieldParams, charge_force  # noqa: E402
from gravi.render import hud, neon  # noqa: E402
from gravi.render.trail import Trail  # noqa: E402
from gravi.room import load_room  # noqa: E402
from gravi.sim import World, charge_from_input  # noqa: E402
from gravi.tuning import TuningState  # noqa: E402

ROOM_PATH = Path(__file__).parent / "rooms" / "slice1.json"
PRESET_PATH = Path(__file__).parent / "presets" / "current.json"
RESPAWN_DELAY = 0.6
STATUS_DURATION = 2.0
ADJUST_REPEAT_DELAY = 0.35     # seconds held before the sweep starts
ADJUST_REPEAT_INTERVAL = 0.05  # seconds between notches while sweeping


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
    )


def apply_tunables(world: World, tunables: dict[str, float]) -> None:
    """Push live-edited values into a running world without losing motion."""
    world.params = FieldParams(
        k_attract=tunables["k_attract"],
        k_repel=tunables["k_repel"],
        force_max=tunables["force_max"],
    )
    world.gravity_y = tunables["gravity_y"]
    world.player_radius = tunables["player_radius"]
    world.speed_max = tunables["speed_max"]


async def main() -> None:
    pygame.init()
    screen = pygame.display.set_mode((config.WINDOW_WIDTH, config.WINDOW_HEIGHT))
    pygame.display.set_caption("Gravi")
    clock = pygame.time.Clock()

    tuning = TuningState(config.default_tunables())
    tunables = tuning.values
    show_hud = True
    status = ""
    status_timer = 0.0
    adjust_hold = 0.0
    adjust_accum = 0.0

    room = load_room(ROOM_PATH)
    world = build_world(room, tunables)
    trail = Trail(config.TRAIL_MAX_POINTS)

    accumulator = 0.0
    dead_timer = 0.0
    running = True

    while running:
        frame_dt = min(clock.tick(config.TARGET_FPS) / 1000.0, 0.25)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                shift = bool(event.mod & pygame.KMOD_SHIFT)
                ctrl = bool(event.mod & pygame.KMOD_CTRL)
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_r and not ctrl:
                    world.reset()
                    trail.clear()
                elif event.key == pygame.K_TAB:
                    show_hud = not show_hud
                elif event.key == pygame.K_UP:
                    tuning.cycle(-1)
                elif event.key == pygame.K_DOWN:
                    tuning.cycle(+1)
                elif event.key == pygame.K_LEFT:
                    tuning.adjust(-1, fast=shift)
                elif event.key == pygame.K_RIGHT:
                    tuning.adjust(+1, fast=shift)
                elif event.key == pygame.K_F5:
                    ok = tuning.save(PRESET_PATH)
                    status = "preset saved" if ok else "save unavailable (browser build)"
                    status_timer = STATUS_DURATION
                elif event.key == pygame.K_F9:
                    ok = tuning.load(PRESET_PATH)
                    status = "preset loaded" if ok else "no preset found"
                    status_timer = STATUS_DURATION
                elif event.key == pygame.K_F8:
                    tuning.restore_defaults()
                    status = "defaults restored"
                    status_timer = STATUS_DURATION

        keys = pygame.key.get_pressed()
        mouse = pygame.mouse.get_pressed(num_buttons=3)
        attract_held = keys[pygame.K_j] or mouse[0]
        repel_held = keys[pygame.K_k] or mouse[2]
        charge = charge_from_input(attract_held, repel_held)

        # Held Left/Right sweeps a value. Done by hand rather than with
        # pygame.key.set_repeat, which is global and would also strobe Tab
        # and R.
        if keys[pygame.K_LEFT] or keys[pygame.K_RIGHT]:
            adjust_hold += frame_dt
            if adjust_hold > ADJUST_REPEAT_DELAY:
                adjust_accum += frame_dt
                fast = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
                direction = 1 if keys[pygame.K_RIGHT] else -1
                while adjust_accum >= ADJUST_REPEAT_INTERVAL:
                    tuning.adjust(direction, fast=fast)
                    adjust_accum -= ADJUST_REPEAT_INTERVAL
        else:
            adjust_hold = 0.0
            adjust_accum = 0.0

        apply_tunables(world, tunables)

        accumulator += frame_dt
        steps = 0
        while accumulator >= world.dt and steps < config.MAX_STEPS_PER_FRAME:
            world.step(charge)
            accumulator -= world.dt
            steps += 1
            if not world.dead:
                trail.add(world.x, world.y)
        if steps == config.MAX_STEPS_PER_FRAME:
            accumulator = 0.0

        if world.dead:
            dead_timer += frame_dt
            if dead_timer >= RESPAWN_DELAY:
                world.reset()
                trail.clear()
                dead_timer = 0.0
        else:
            dead_timer = 0.0

        if status_timer > 0.0:
            status_timer -= frame_dt
            if status_timer <= 0.0:
                status = ""

        # --- draw ---
        screen.fill(config.COLOR_BG)
        neon.draw_trail(screen, trail.points())

        active = world.active_node()
        for node in room.nodes:
            neon.draw_node(screen, node, is_active=node is active)

        if active is not None and charge is not Charge.NEUTRAL and not world.dead:
            fx, fy = charge_force(world.x, world.y, active, charge, world.params)
            neon.draw_beam(screen, world.x, world.y, active, charge,
                           math.hypot(fx, fy), world.params.force_max)

        if not world.dead:
            neon.draw_player(screen, world.x, world.y, world.player_radius)

        if show_hud:
            hud.draw(screen, tuning, status)

        pygame.display.flip()
        await asyncio.sleep(0)  # REQUIRED for pygbag; do not remove

    pygame.quit()


if __name__ == "__main__":
    asyncio.run(main())
