"""Live tuning state. Pure — no pygame — so the values and the persistence can
be tested without a display.

Feel is found by sweeping values while playing, not by editing a file and
restarting, so this is deliberately in the first slice rather than deferred.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from . import config

FAST_MULTIPLIER = 10.0


class TuningState:
    def __init__(self, values: dict[str, float]) -> None:
        self.values = values
        self._names = list(config.TUNABLES)
        self._index = 0

    @property
    def selected(self) -> str:
        return self._names[self._index]

    def select(self, name: str) -> None:
        self._index = self._names.index(name)

    def cycle(self, direction: int) -> None:
        self._index = (self._index + direction) % len(self._names)

    def adjust(self, direction: int, fast: bool = False) -> None:
        name = self.selected
        _default, step, low, high = config.TUNABLES[name]
        delta = step * direction * (FAST_MULTIPLIER if fast else 1.0)
        self.values[name] = max(low, min(high, self.values[name] + delta))

    def orbital_period(self) -> float:
        """2*pi/sqrt(k_attract). Independent of orbit size under a linear
        central force, which makes it the single best predictor of feel."""
        k = self.values["k_attract"]
        return math.inf if k <= 0 else 2.0 * math.pi / math.sqrt(k)

    def restore_defaults(self) -> None:
        self.values.update(config.default_tunables())

    def save(self, path: str | Path) -> bool:
        """False rather than an exception on failure: the browser build has no
        writable filesystem and a save keypress must not crash the game."""
        try:
            target = Path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "w", encoding="utf-8") as handle:
                json.dump(self.values, handle, indent=2, sort_keys=True)
            return True
        except OSError:
            return False

    def load(self, path: str | Path) -> bool:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return False
        for name in config.TUNABLES:
            if name in data:
                self.values[name] = float(data[name])
        return True
