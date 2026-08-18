"""The probe is a measuring instrument, so the suite checks that it runs,
reports, and repeats — never that any particular number holds. A frame-cost
assertion would fail on a slower CI runner for reasons that say nothing about
Gravi."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROBE = ROOT / "tools" / "perf_probe.py"


def run_probe(*args: str) -> dict[str, str]:
    environment = dict(os.environ, SDL_VIDEODRIVER="dummy", PYTHONPATH=str(ROOT / "src"))
    result = subprocess.run(
        [sys.executable, str(PROBE), *args],
        capture_output=True, text=True, env=environment, cwd=ROOT,
    )
    assert result.returncode == 0, result.stderr
    fields = {}
    for line in result.stdout.splitlines():
        if " " in line:
            key, _, value = line.partition(" ")
            fields[key] = value.strip()
    return fields


def test_the_probe_exists_and_is_executable():
    assert PROBE.is_file()


def test_it_exits_zero_and_reports_mean_and_p95():
    fields = run_probe("--frames", "30", "--seed", "1")
    assert float(fields["mean_ms"]) > 0.0
    assert float(fields["p95_ms"]) > 0.0


def test_it_reports_the_draw_cost_separately_from_the_simulation():
    fields = run_probe("--frames", "30", "--seed", "1")
    assert float(fields["draw_mean_ms"]) > 0.0
    assert float(fields["sim_mean_ms"]) >= 0.0


def test_it_runs_the_number_of_frames_it_was_asked_for():
    assert run_probe("--frames", "17", "--seed", "1")["frames"] == "17"


def test_the_same_seed_produces_the_same_run():
    first = run_probe("--frames", "40", "--seed", "7")["checksum"]
    second = run_probe("--frames", "40", "--seed", "7")["checksum"]
    assert first == second


def test_a_different_seed_produces_a_different_run():
    # 200 frames, not 40: the run opens with the player falling out of range
    # of every node, where a charge applies no force at all. Two seeds whose
    # input scripts differ only in those first holds produce byte-identical
    # state, which says nothing about --seed being wired up. Measure once the
    # inputs can actually bite.
    first = run_probe("--frames", "200", "--seed", "7")["checksum"]
    other = run_probe("--frames", "200", "--seed", "8")["checksum"]
    assert first != other


def test_p95_is_at_least_the_mean():
    fields = run_probe("--frames", "40", "--seed", "1")
    assert float(fields["p95_ms"]) >= float(fields["mean_ms"])


def test_it_imports_nothing_outside_the_declared_dependencies():
    source = PROBE.read_text()
    for forbidden in ("import numpy", "import pytest", "import psutil", "import pygbag"):
        assert forbidden not in source
