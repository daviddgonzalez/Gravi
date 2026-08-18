"""Small key-value persistence that cannot be the reason a run dies.

Spec section 8.6: tuning presets, edited rooms, the player model (5.2) and
personal-best paths (6) all need to survive between sessions, and all of them
must fail soft. Natively that means a JSON file per key under a per-user
directory. In the browser there is no writable filesystem, so the same calls
go to ``localStorage`` instead.

The contract is narrow on purpose:

    save(key, obj) -> bool      True on success, False on *any* failure
    load(key, default) -> Any   the stored value, or default on any failure

Neither raises. A save keypress in the browser is a no-op, not a traceback.

The backend is injectable so tests touch neither a real disk nor a real
browser, and so a caller that wants its own store can pass one.

This module imports no pygame: the validator and the trainer share it.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

__all__ = [
    "Backend",
    "MemoryBackend",
    "FileBackend",
    "LocalStorageBackend",
    "default_backend",
    "load",
    "save",
    "namespaced",
]

NAMESPACE = "gravi"


def namespaced(key: str) -> str:
    """Prefix a key so the browser origin is not polluted by bare names."""
    return f"{NAMESPACE}.{key}"


@runtime_checkable
class Backend(Protocol):
    """Stores strings under string keys. Either method may raise; the module
    level save/load turn that into a False or a default."""

    def read(self, key: str) -> str | None: ...

    def write(self, key: str, value: str) -> None: ...


class MemoryBackend:
    """A dict. The test double, and a usable null-persistence backend."""

    def __init__(self, data: dict[str, str] | None = None) -> None:
        self.data: dict[str, str] = dict(data or {})

    def read(self, key: str) -> str | None:
        return self.data.get(key)

    def write(self, key: str, value: str) -> None:
        self.data[key] = value


class FileBackend:
    """One JSON file per key under a directory. The native backend."""

    def __init__(self, directory: str | os.PathLike[str]) -> None:
        self.directory = Path(directory)

    def _path(self, key: str) -> Path:
        # A key is a flat name, never a path. Refusing separators here keeps a
        # caller-supplied key from writing outside the store.
        if key != Path(key).name or key in (".", "..") or os.sep in key:
            raise ValueError(f"key is not a flat name: {key!r}")
        return self.directory / f"{key}.json"

    def read(self, key: str) -> str | None:
        path = self._path(key)
        if not path.is_file():
            return None
        return path.read_text(encoding="utf-8")

    def write(self, key: str, value: str) -> None:
        path = self._path(key)
        self.directory.mkdir(parents=True, exist_ok=True)
        # Write-then-rename so an interrupted save cannot leave a half file
        # that would later load as corrupt.
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(value, encoding="utf-8")
        temporary.replace(path)


class LocalStorageBackend:
    """``window.localStorage``, the only persistence the browser build has.

    pygbag exposes the DOM window as ``platform.window`` — its own ``platform``
    module, which shadows the standard library one under emscripten.
    """

    def __init__(self, window: Any = None) -> None:
        if window is None:
            import platform  # pygbag's, under emscripten

            window = platform.window
        self._store = window.localStorage

    def read(self, key: str) -> str | None:
        value = self._store.getItem(key)
        if value is None:
            return None
        return str(value)

    def write(self, key: str, value: str) -> None:
        self._store.setItem(key, value)


def _user_directory() -> Path:
    """Where a native install keeps its store. No new dependencies, so this is
    the XDG rule by hand, with the Windows and macOS conventions honoured."""
    if sys.platform == "win32":
        root = os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming"
        return Path(root) / "Gravi"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Gravi"
    root = os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
    return Path(root) / "gravi"


def default_backend() -> Backend:
    """Pick a backend for this platform. Falls back to memory rather than
    raising, so an unusual environment degrades to not persisting."""
    try:
        if sys.platform == "emscripten":
            return LocalStorageBackend()
        return FileBackend(_user_directory())
    except Exception:
        return MemoryBackend()


# Chosen once, at import, so the decision is not re-made every keypress.
_DEFAULT_BACKEND: Backend = default_backend()


def save(key: str, obj: Any, backend: Backend | None = None) -> bool:
    """Store ``obj`` under ``key``. Returns False on any failure, never raises."""
    try:
        encoded = json.dumps(obj)
    except Exception:
        return False
    try:
        target = _DEFAULT_BACKEND if backend is None else backend
        target.write(namespaced(key), encoded)
    except Exception:
        return False
    return True


def load(key: str, default: Any = None, backend: Backend | None = None) -> Any:
    """Return the value stored under ``key``, or ``default`` if it is missing,
    unreadable or corrupt. Never raises."""
    try:
        source = _DEFAULT_BACKEND if backend is None else backend
        raw = source.read(namespaced(key))
    except Exception:
        return default
    if raw is None:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default
