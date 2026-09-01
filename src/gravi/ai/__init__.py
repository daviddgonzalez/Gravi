"""Gravi's genetic-algorithm stack, ported from BlueBall (spec section 8.5).

Ported by copy, deliberately: BlueBall stays untouched. The machinery — the
genome, the network it parameterises, the GA operators, the rollout loop and
the trainer — carries over. What the agent *observes* and what it is *rewarded
for* do not, and are not here: `observation.py` and `fitness.py` are rewritten
rather than ported, in session S5, because the same encoding has to serve the
rival as well as the difficulty meter.

Nothing in this package may import pygame. The trainer runs natively, headless,
and never in the browser (spec section 8.6); `tests/test_purity.py` enforces it.
"""

from . import ga
from .env import Environment, StubEnvironment
from .ftnn import CHARGE_BY_OUTPUT, FTNN, Shape
from .genome import random_genome, seed_population

__all__ = [
    "Environment",
    "StubEnvironment",
    "FTNN",
    "Shape",
    "CHARGE_BY_OUTPUT",
    "random_genome",
    "seed_population",
    "ga",
]
