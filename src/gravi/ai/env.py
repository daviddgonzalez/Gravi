"""What the GA trains against.

BlueBall's agent saw raycasts, ability bits and key bits — a platformer with
twenty entity types. Gravi's agent sees a node field, and there is exactly one
verb with three states. The real encoding (relative position, charge, radius
and remaining life for the nearest few nodes, plus velocity, gravity direction
and arrow bearing) is designed in session S5, because the same encoding has to
serve the rival as well as the difficulty meter. This module is the seam it
plugs into, plus a stub good enough to prove the loop runs.

The seam is deliberately narrow. An environment declares how wide its
observation is *before* producing one, because the network sizes its input
layer from that number and must never guess it. Everything else is the
familiar reset / observe / act / step cycle.
"""

from __future__ import annotations

import random
from typing import Protocol, runtime_checkable

from ..field import Charge

__all__ = ["Environment", "StubEnvironment"]


@runtime_checkable
class Environment(Protocol):
    """One trainable task. Implementations must be deterministic given a seed —
    the whole GA rests on a genome scoring the same way twice."""

    #: How many floats `observe()` returns. Known before `reset()`.
    observation_size: int

    #: True once the episode is over and `outcome()` is meaningful.
    done: bool

    def reset(self) -> None:
        """Return to the starting state. Safe to call repeatedly."""
        ...

    def observe(self) -> tuple[float, ...]:
        """The current state, as a flat tuple of exactly `observation_size`
        floats."""
        ...

    def act(self, charge: Charge) -> None:
        """Set the player's charge for the next step. Gravi has one verb with
        three states; anything that is not a `Charge` is an error, not a
        no-op."""
        ...

    def step(self) -> None:
        """Advance one tick."""
        ...

    def outcome(self) -> dict:
        """What happened, for the fitness function to read. Always carries a
        `score` key."""
        ...


def _as_charge(value: object) -> Charge:
    """Coerce to a Charge or raise.

    Charge is an IntEnum, so a bare `7` would sail through an `isinstance(int)`
    check and then silently behave as some third thing. Round-tripping through
    the enum is what makes an out-of-range action loud.
    """
    if isinstance(value, Charge):
        return value
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"action must be a Charge, got {type(value).__name__}")
    return Charge(value)  # raises ValueError for anything outside -1/0/1


class StubEnvironment:
    """A one-dimensional tracking task: get to the target and stay there.

    Attract accelerates toward increasing position, repel toward decreasing,
    neutral coasts. Score is the negative integrated absolute error, so a
    policy that parks on the target scores near zero and a policy that ignores
    it scores badly.

    Deliberately trivial and deliberately learnable. Its only job is to fail
    loudly if the GA is broken — it is not a model of Gravi, and S5's real
    environment replaces it wholesale.
    """

    observation_size = 3

    #: Ticks per episode.
    EPISODE_STEPS = 120
    #: Acceleration applied per tick by a non-neutral charge.
    ACCEL = 0.05
    #: Velocity retained per tick, so the task needs braking, not just steering.
    DRAG = 0.98

    def __init__(self, seed: int = 0) -> None:
        self.seed = seed
        self.done = False
        self._started = False
        # Start position and target come from the seed, so different seeds are
        # genuinely different problems rather than the same one relabelled.
        rng = random.Random(seed)
        self._start = rng.uniform(-1.0, 1.0)
        self._target = rng.uniform(-1.0, 1.0)
        self._position = self._start
        self._velocity = 0.0
        self._charge = Charge.NEUTRAL
        self._steps = 0
        self._error_sum = 0.0

    def reset(self) -> None:
        self._position = self._start
        self._velocity = 0.0
        self._charge = Charge.NEUTRAL
        self._steps = 0
        self._error_sum = 0.0
        self.done = False
        self._started = True

    def observe(self) -> tuple[float, ...]:
        return (
            float(self._position),
            float(self._velocity),
            float(self._target - self._position),
        )

    def act(self, charge: Charge) -> None:
        self._charge = _as_charge(charge)

    def step(self) -> None:
        if not self._started:
            raise RuntimeError("reset() before step()")
        if self.done:
            return
        self._velocity = self._velocity * self.DRAG + int(self._charge) * self.ACCEL
        self._position += self._velocity
        self._error_sum += abs(self._target - self._position)
        self._steps += 1
        if self._steps >= self.EPISODE_STEPS:
            self.done = True

    def outcome(self) -> dict:
        return {
            "score": -self._error_sum,
            "steps": self._steps,
            "final_error": abs(self._target - self._position),
            "target": self._target,
        }
