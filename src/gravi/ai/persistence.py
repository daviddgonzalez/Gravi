"""Saving and loading a population.

Not a port, for two reasons.

**Format.** BlueBall wrote `.npy` — a numpy binary. Gravi's cross-session
invariant is that whatever the offline trainer emits has to load in the
browser, and the browser has no numpy. So a checkpoint is JSON: a shape, a list
of weight lists, and a metadata block. float32 values are exactly representable
in the float64 JSON uses, so the round trip is lossless rather than merely
close — which matters, because "close" would break the byte-identical
reproducibility the rest of this package promises.

**Failure behaviour.** BlueBall's writer called `mkdir` and `np.save` and let
them raise. There is no writable filesystem in the browser (spec section 8.6),
so saving here fails soft and returns False, the same contract `room.save_room`
already uses. A checkpoint that cannot be written is a thing that did not
happen, not a crash.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .ftnn import Shape

__all__ = ["save_population", "load_population", "Checkpoint"]

#: Bumped when the on-disk layout changes incompatibly, so a stale checkpoint
#: is a clear error rather than a confusing one.
FORMAT_VERSION = 1


class Checkpoint:
    """A loaded population, with the shape needed to interpret it."""

    def __init__(self, shape: Shape, genomes: list[np.ndarray], meta: dict) -> None:
        self.shape = shape
        self.genomes = genomes
        self.meta = meta

    def __len__(self) -> int:
        return len(self.genomes)


def save_population(
    population: list[np.ndarray],
    path: Path | str,
    *,
    shape: Shape,
    meta: dict | None = None,
) -> bool:
    """Write a population to `path` as JSON. Returns True on success.

    Never raises on a filesystem problem — returns False instead. The caller
    decides whether a missing checkpoint matters; in the browser it never does.
    """
    payload = {
        "version": FORMAT_VERSION,
        "shape": shape.as_dict(),
        "meta": dict(meta or {}),
        # .tolist() gives Python floats. float32 -> float64 is exact, so this
        # round-trips bit-for-bit through JSON.
        "genomes": [np.asarray(g, dtype=np.float32).tolist() for g in population],
    }
    try:
        target = Path(path)
        if target.parent != Path(""):
            target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload))
    except (OSError, TypeError, ValueError):
        return False
    return True


def load_population(path: Path | str) -> Checkpoint | None:
    """Read a checkpoint back. Returns None if it cannot be read at all.

    A file that is present but malformed raises ValueError — that is a bug in
    whatever wrote it, and swallowing it would hand the trainer a silently
    empty population.
    """
    try:
        raw = Path(path).read_text()
    except OSError:
        return None

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON") from exc

    if not isinstance(payload, dict):
        raise ValueError(f"{path} is not a checkpoint object")
    version = payload.get("version")
    if version != FORMAT_VERSION:
        raise ValueError(
            f"{path} is checkpoint format {version!r}, expected {FORMAT_VERSION}"
        )
    try:
        shape = Shape.from_dict(payload["shape"])
        genomes = [np.asarray(g, dtype=np.float32) for g in payload["genomes"]]
    except (KeyError, TypeError) as exc:
        raise ValueError(f"{path} is missing checkpoint fields") from exc

    for i, g in enumerate(genomes):
        if g.shape != (shape.genome_size,):
            raise ValueError(
                f"{path} genome {i} has length {g.shape[0]}, expected "
                f"{shape.genome_size} for shape {shape}"
            )

    return Checkpoint(shape=shape, genomes=genomes, meta=payload.get("meta", {}))
