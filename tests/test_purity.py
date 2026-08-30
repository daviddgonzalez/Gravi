"""Spec section 8.1: the simulation core is shared with the offline validator
and the trainer, so it must not drag in pygame. A subprocess is used because
importing pygame anywhere else in the test session would mask the problem."""

import ast
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "gravi"


def test_sim_core_does_not_import_pygame():
    code = (
        "import gravi.sim, gravi.field, gravi.room, gravi.gravity, gravi.chamber, sys; "
        "assert 'pygame' not in sys.modules, sorted(m for m in sys.modules if 'pygame' in m)"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def imported_modules(path):
    """Top-level module names a file imports. Checked by parsing rather than
    by searching the text, because a docstring saying "never import pygame"
    would fail a substring check."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_gravity_module_is_pure():
    imports = imported_modules(SRC / "gravity.py")
    assert "pygame" not in imports
    assert imports <= {"__future__", "math", "dataclasses"}, imports


def test_chamber_module_is_pure():
    imports = imported_modules(SRC / "chamber.py")
    assert "pygame" not in imports
    assert imports <= {"__future__", "math", "random", "dataclasses", "field"}, imports


def test_ai_stack_does_not_import_pygame():
    """The trainer runs headless, natively, on boxes with no display (spec
    section 8.6). A stray pygame import here is the difference between a
    validation build that runs in CI and one that does not."""
    code = (
        "import gravi.ai, gravi.ai.env, gravi.ai.trainer, sys; "
        "assert 'pygame' not in sys.modules, sorted(m for m in sys.modules if 'pygame' in m)"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
