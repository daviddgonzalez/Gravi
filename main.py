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

import pygame  # noqa: E402

from gravi import config  # noqa: E402


async def main() -> None:
    pygame.init()
    screen = pygame.display.set_mode((config.WINDOW_WIDTH, config.WINDOW_HEIGHT))
    pygame.display.set_caption("Gravi")
    clock = pygame.time.Clock()

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

        screen.fill(config.COLOR_BG)
        pygame.display.flip()

        clock.tick(config.TARGET_FPS)
        await asyncio.sleep(0)  # REQUIRED for pygbag; do not remove

    pygame.quit()


if __name__ == "__main__":
    asyncio.run(main())
