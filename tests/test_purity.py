"""Spec section 8.1: the simulation core is shared with the offline validator
and the trainer, so it must not drag in pygame. A subprocess is used because
importing pygame anywhere else in the test session would mask the problem."""

import subprocess
import sys


def test_sim_core_does_not_import_pygame():
    code = (
        "import gravi.sim, gravi.field, gravi.room, sys; "
        "assert 'pygame' not in sys.modules, sorted(m for m in sys.modules if 'pygame' in m)"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_ai_stack_does_not_import_pygame():
    """The trainer runs headless, natively, on boxes with no display (spec
    section 8.6). A stray pygame import here is the difference between a
    validation build that runs in CI and one that does not."""
    code = (
        "import gravi.ai, gravi.ai.env, sys; "
        "assert 'pygame' not in sys.modules, sorted(m for m in sys.modules if 'pygame' in m)"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
