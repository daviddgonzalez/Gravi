"""`python -m gravi.ai` — the entry point S7 invokes as a build step.

Driven through subprocess rather than by calling main() directly, because the
things that break a build step are exit codes, imports and stdout, and none of
those are visible from in-process.
"""

import json
import subprocess
import sys

import pytest


def run_cli(*args, expect_ok=True):
    result = subprocess.run(
        [sys.executable, "-m", "gravi.ai", *args],
        capture_output=True, text=True,
    )
    if expect_ok:
        assert result.returncode == 0, result.stderr
    return result


def test_a_short_run_exits_clean_and_writes_a_checkpoint(tmp_path):
    out = tmp_path / "pop.json"
    run_cli("--generations", "3", "--population", "8", "--seed", "1", "--out", str(out))
    assert out.exists()

    payload = json.loads(out.read_text())
    assert len(payload["genomes"]) == 8
    assert payload["shape"]["outputs"] == 3
    assert payload["meta"]["generations"] == 3


def test_help_documents_every_flag():
    out = run_cli("--help").stdout
    for flag in ("--generations", "--population", "--seed", "--out", "--hidden",
                 "--episodes", "--max-steps", "--aggregate", "--lam", "--quiet"):
        assert flag in out, f"{flag} is undocumented"


def test_progress_is_one_line_per_generation(tmp_path):
    result = run_cli("--generations", "4", "--population", "6", "--seed", "1",
                     "--out", str(tmp_path / "p.json"))
    gen_lines = [ln for ln in result.stdout.splitlines() if ln.startswith("gen ")]
    assert len(gen_lines) == 4
    assert "best" in gen_lines[0] and "mean" in gen_lines[0]


def test_quiet_suppresses_the_per_generation_lines(tmp_path):
    result = run_cli("--generations", "3", "--population", "6", "--seed", "1",
                     "--quiet", "--out", str(tmp_path / "p.json"))
    assert not [ln for ln in result.stdout.splitlines() if ln.startswith("gen ")]


def test_the_same_seed_produces_an_identical_checkpoint(tmp_path):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    args = ("--generations", "3", "--population", "8", "--seed", "5", "--quiet")
    run_cli(*args, "--out", str(a))
    run_cli(*args, "--out", str(b))

    pa, pb = json.loads(a.read_text()), json.loads(b.read_text())
    assert pa["genomes"] == pb["genomes"]
    # Wall clock legitimately differs between runs; nothing else may.
    for h in (pa["meta"]["history"], pb["meta"]["history"]):
        for entry in h:
            entry.pop("elapsed")
    assert pa["meta"] == pb["meta"]


def test_running_without_an_out_file_still_trains(tmp_path):
    """Useful for a smoke check in CI that does not want an artifact."""
    result = run_cli("--generations", "2", "--population", "4", "--seed", "1")
    assert "best" in result.stdout


def test_an_unwritable_out_path_is_a_failure_not_a_shrug(tmp_path):
    """save_population fails soft by design, but a build step that was asked
    for an artifact and produced none must not report success."""
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("")
    result = run_cli("--generations", "1", "--population", "4", "--seed", "1",
                     "--out", str(blocker / "pop.json"), expect_ok=False)
    assert result.returncode != 0
    assert "could not write" in result.stderr


def test_nonsense_arguments_are_rejected(tmp_path):
    result = run_cli("--generations", "0", "--population", "4", expect_ok=False)
    assert result.returncode != 0


def test_the_cli_never_imports_pygame(tmp_path):
    """The trainer has to run on a headless box with no display."""
    code = (
        "import runpy, sys; sys.argv = ['gravi.ai', '--generations', '1', "
        "'--population', '2', '--quiet']; "
        "runpy.run_module('gravi.ai', run_name='__main__'); "
        "assert 'pygame' not in sys.modules, "
        "sorted(m for m in sys.modules if 'pygame' in m)"
    )
    result = subprocess.run([sys.executable, "-c", code],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
