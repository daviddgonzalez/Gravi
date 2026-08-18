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
import random  # noqa: E402

import pygame  # noqa: E402

from gravi import config  # noqa: E402
from gravi.chamber import ChamberChain, ChamberParams  # noqa: E402
from gravi.field import Charge, FieldParams, charge_force  # noqa: E402
from gravi.gravity import GravityState  # noqa: E402
from gravi.editor import RoomEditor  # noqa: E402
from gravi.render import hud, neon  # noqa: E402
from gravi.render.camera import Camera  # noqa: E402
from gravi.render.trail import Trail  # noqa: E402
from gravi.room import load_room, save_room  # noqa: E402
from gravi.sim import World, charge_from_input  # noqa: E402
from gravi.tuning import TuningState  # noqa: E402

ROOM_PATH = Path(__file__).parent / "rooms" / "slice1.json"
PRESET_PATH = Path(__file__).parent / "presets" / "current.json"
RESPAWN_DELAY = 0.6
STATUS_DURATION = 2.0
ADJUST_REPEAT_DELAY = 0.35     # seconds held before the sweep starts
ADJUST_REPEAT_INTERVAL = 0.05  # seconds between notches while sweeping


def chamber_params(tunables: dict[str, float]) -> ChamberParams:
    return ChamberParams(depth=tunables["chamber_depth"],
                         half_width=tunables["chamber_half_width"])


def build_world(seed: int, tunables: dict[str, float]) -> World:
    return World(
        chain=ChamberChain(seed=seed, params=chamber_params(tunables)),
        params=FieldParams(
            k_attract=tunables["k_attract"],
            k_repel=tunables["k_repel"],
            force_max=tunables["force_max"],
        ),
        gravity=tunables["gravity"],
        gravity_state=GravityState(flip_duration=tunables["flip_duration"]),
        player_radius=tunables["player_radius"],
        speed_max=tunables["speed_max"],
        fall_speed_max=tunables["fall_speed_max"],
    )


def apply_tunables(world: World, tunables: dict[str, float]) -> bool:
    """Push live-edited values into a running world without losing motion.

    Returns True when a value changed that the chain is built FROM rather than
    stepped with. Chamber dimensions are structural: a live corridor cannot
    change width under a player halfway down it, so those rebuild the chain
    from the same seed and restart the run instead.
    """
    world.params = FieldParams(
        k_attract=tunables["k_attract"],
        k_repel=tunables["k_repel"],
        force_max=tunables["force_max"],
    )
    world.gravity = tunables["gravity"]
    # Takes effect on the NEXT flip; a flip already easing keeps its own pace.
    world.gravity_state.flip_duration = tunables["flip_duration"]
    world.player_radius = tunables["player_radius"]
    world.speed_max = tunables["speed_max"]
    world.fall_speed_max = tunables["fall_speed_max"]
    return world.chain.params != chamber_params(tunables)


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

    room = None
    editor = None
    seed = random.randrange(1 << 30)
    world = build_world(seed, tunables)
    trail = Trail(config.TRAIL_MAX_POINTS)
    camera = Camera(config.WINDOW_WIDTH, config.WINDOW_HEIGHT)
    # Rotating is the mode slice 2 is judging, so it is the one the game opens
    # in. The prototype defaults to fixed because it exists to compare them.
    rotating_camera = True

    accumulator = 0.0
    dead_timer = 0.0
    trail_sample = 0
    best = 0
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
                    # A new corridor, not the same one again: the run is the
                    # unit of play now, and its seed is what makes it one.
                    best = max(best, world.cleared)
                    seed = random.randrange(1 << 30)
                    world = build_world(seed, tunables)
                    trail.clear()
                    dead_timer = 0.0
                elif event.key == pygame.K_c:
                    rotating_camera = not rotating_camera
                    status = ("camera: rotating" if rotating_camera
                              else "camera: fixed")
                    status_timer = STATUS_DURATION
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
                elif event.key == pygame.K_s and ctrl and room is not None:
                    ok = save_room(room, ROOM_PATH)
                    status = "room saved" if ok else "save unavailable (browser build)"
                    status_timer = STATUS_DURATION
                elif event.key == pygame.K_DELETE and editor is not None:
                    mx, my = pygame.mouse.get_pos()
                    editor.delete(float(mx), float(my))
                elif (event.key in (pygame.K_LEFTBRACKET, pygame.K_RIGHTBRACKET)
                      and editor is not None):
                    mx, my = pygame.mouse.get_pos()
                    editor.resize_radius(
                        float(mx), float(my),
                        -1 if event.key == pygame.K_LEFTBRACKET else +1)
                elif (event.key in (pygame.K_COMMA, pygame.K_PERIOD)
                      and editor is not None):
                    mx, my = pygame.mouse.get_pos()
                    editor.resize_core(
                        float(mx), float(my),
                        -1 if event.key == pygame.K_COMMA else +1)
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if editor is not None and pygame.key.get_mods() & pygame.KMOD_ALT:
                    mx, my = float(event.pos[0]), float(event.pos[1])
                    if event.button == 1:
                        editor.grab(mx, my)
                    elif event.button == 3 and editor.hovered(mx, my) is None:
                        editor.add(mx, my)
            elif (event.type == pygame.MOUSEBUTTONUP and event.button == 1
                  and editor is not None):
                editor.release()
            elif (event.type == pygame.MOUSEMOTION and editor is not None
                  and editor.dragging is not None):
                # No Alt check here: releasing Alt mid-drag must not drop the node.
                editor.drag(float(event.pos[0]), float(event.pos[1]))

        keys = pygame.key.get_pressed()
        mouse = pygame.mouse.get_pressed(num_buttons=3)
        editing = editor is not None and bool(pygame.key.get_mods() & pygame.KMOD_ALT)
        attract_held = (keys[pygame.K_j] or mouse[0]) and not editing
        repel_held = (keys[pygame.K_k] or mouse[2]) and not editing
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

        if apply_tunables(world, tunables) and room is None:
            # Structural change: same seed, new dimensions, fresh run.
            best = max(best, world.cleared)
            world = build_world(seed, tunables)
            trail.clear()
            dead_timer = 0.0

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
                # Respawn at this chamber's entrance to keep a feel test
                # flowing (spec 9 leaves what the real game does to slice 3).
                # reset() zeroes the run's counters, so bank the score first.
                best = max(best, world.cleared)
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
        camera.update(world.x, world.y, world.gravity_state.angle,
                      rotating=rotating_camera)

        # Corridor first: the chamber you are in, one behind, two ahead.
        for index in range(max(0, world.chain.at - 1), world.chain.at + 3):
            chamber = world.chain.by_index(index)
            if chamber is None:
                continue
            is_current = index == world.chain.at
            neon.draw_chamber(screen, chamber, camera, is_current=is_current)
            neon.draw_arrow(screen, chamber, camera, is_current=is_current)

        neon.draw_trail(screen, trail.points(), camera)

        # The roped node is the one actually pulling, so it is the one that
        # lights up and the one the beam points at — the player may well be
        # outside its ring by now.
        anchor = world.latched_node() or world.active_node()
        for _, _, node in world.chain.nodes_near():
            neon.draw_node(screen, node, is_active=node is anchor, camera=camera)

        if anchor is not None and charge is not Charge.NEUTRAL and not world.dead:
            # Mirrors World.step exactly, or the beam would draw a force the
            # simulation is not applying.
            fx, fy = charge_force(
                world.x, world.y, anchor, charge, world.params,
                ignore_radius=(charge is Charge.ATTRACT
                               and world.latched_node() is not None))
            neon.draw_beam(screen, world.x, world.y, anchor, charge,
                           math.hypot(fx, fy), world.params.force_max, camera)

        if not world.dead:
            neon.draw_player(screen, world.x, world.y, world.player_radius, camera)

        if show_hud:
            # Screen space: the HUD never goes through the camera.
            run_line = (f"chambers {world.cleared}   best {max(best, world.cleared)}"
                        f"   distance {int(world.distance)}"
                        f"   camera {'rotating' if rotating_camera else 'fixed'}")
            hud.draw(screen, tuning, status, fps=clock.get_fps(), steps=steps,
                     run=run_line)

        pygame.display.flip()
        await asyncio.sleep(0)  # REQUIRED for pygbag; do not remove

    pygame.quit()


if __name__ == "__main__":
    asyncio.run(main())
