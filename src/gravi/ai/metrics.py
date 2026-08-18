"""Per-generation training statistics.

Not a port. BlueBall's `ai/metrics.py` computes `jumps_per_100px` and
`airtime_pct` — behaviour metrics for a platformer, meaningless here — while
its per-generation stats were inline dicts inside the trainer's loop. This is
that inline dict given a name and a wall clock, because S7 has to budget a
validation build and "how long did generation 12 take" is the number it needs.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

__all__ = ["GenerationStats", "summarise"]


@dataclass(frozen=True)
class GenerationStats:
    """What one generation did."""

    gen: int
    best: float
    mean: float
    worst: float
    #: Population standard deviation of fitness. A run whose std collapses to
    #: near zero has converged — or lost its diversity and stopped searching.
    std: float
    #: Seconds spent evaluating this generation.
    elapsed: float

    def as_dict(self) -> dict:
        return asdict(self)

    def line(self) -> str:
        """One terminal line, so a long run is legible while it runs."""
        return (
            f"gen {self.gen:>4}  "
            f"best {self.best:>12.4f}  "
            f"mean {self.mean:>12.4f}  "
            f"worst {self.worst:>12.4f}  "
            f"std {self.std:>10.4f}  "
            f"{self.elapsed:>6.2f}s"
        )


def summarise(gen: int, fitnesses: np.ndarray, elapsed: float) -> GenerationStats:
    """Reduce a generation's fitness array to its statistics."""
    arr = np.asarray(fitnesses, dtype=np.float64)
    if arr.size == 0:
        raise ValueError("summarise requires a non-empty fitness array")
    return GenerationStats(
        gen=int(gen),
        best=float(arr.max()),
        mean=float(arr.mean()),
        worst=float(arr.min()),
        std=float(arr.std()),
        elapsed=float(elapsed),
    )
