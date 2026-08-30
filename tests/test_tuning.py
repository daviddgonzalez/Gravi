import json

from gravi import config
from gravi.tuning import TuningState


def test_adjust_moves_by_the_step_for_that_parameter():
    state = TuningState(config.default_tunables())
    state.select("k_attract")
    before = state.values["k_attract"]
    state.adjust(+1)
    assert state.values["k_attract"] == before + config.TUNABLES["k_attract"][1]


def test_adjust_clamps_to_bounds():
    state = TuningState(config.default_tunables())
    state.select("k_attract")
    for _ in range(10_000):
        state.adjust(-1)
    assert state.values["k_attract"] == config.TUNABLES["k_attract"][2]


def test_shift_multiplies_the_step():
    state = TuningState(config.default_tunables())
    state.select("force_max")
    before = state.values["force_max"]
    state.adjust(+1, fast=True)
    assert state.values["force_max"] == before + config.TUNABLES["force_max"][1] * 10


def test_cycle_wraps_around_the_parameter_list():
    state = TuningState(config.default_tunables())
    names = list(config.TUNABLES)
    assert state.selected == names[0]
    state.cycle(-1)
    assert state.selected == names[-1]
    state.cycle(+1)
    assert state.selected == names[0]


def test_orbital_period_matches_the_closed_form():
    import math
    state = TuningState(config.default_tunables())
    state.values["k_attract"] = 4.0
    assert state.orbital_period() == math.pi  # 2*pi/sqrt(4)


def test_save_and_load_round_trips(tmp_path):
    state = TuningState(config.default_tunables())
    state.values["k_attract"] = 17.5
    path = tmp_path / "preset.json"
    assert state.save(path) is True

    fresh = TuningState(config.default_tunables())
    assert fresh.load(path) is True
    assert fresh.values["k_attract"] == 17.5


def test_save_returns_false_on_an_unwritable_path(tmp_path):
    state = TuningState(config.default_tunables())
    blocker = tmp_path / "file"
    blocker.write_text("not a directory")
    assert state.save(blocker / "nested" / "preset.json") is False


def test_load_ignores_unknown_keys(tmp_path):
    path = tmp_path / "preset.json"
    path.write_text(json.dumps({"k_attract": 3.0, "nonsense": 1.0}))
    state = TuningState(config.default_tunables())
    assert state.load(path) is True
    assert state.values["k_attract"] == 3.0
    assert "nonsense" not in state.values


def test_restore_defaults():
    state = TuningState(config.default_tunables())
    state.values["k_attract"] = 99.0
    state.restore_defaults()
    assert state.values["k_attract"] == config.TUNABLES["k_attract"][0]


def test_load_ignores_unknown_and_missing_keys(tmp_path):
    """A preset written before the rename must not crash the game."""
    path = tmp_path / "old.json"
    path.write_text('{"gravity_y": 900.0, "k_attract": 12.0}', encoding="utf-8")
    state = TuningState(config.default_tunables())
    assert state.load(path) is True
    assert state.values["k_attract"] == 12.0
    assert state.values["gravity"] == config.TUNABLES["gravity"].default


def test_nudge_adjusts_a_named_knob_without_moving_the_selection():
    """Field of view is on its own keys, not on the overlay's cursor: hunting
    for it eleven rows down while playing is not a control."""
    state = TuningState(config.default_tunables())
    state.select("k_attract")
    before = state.values["view_width"]

    state.nudge("view_width", +1)

    assert state.values["view_width"] == before + config.TUNABLES["view_width"].step
    assert state.selected == "k_attract"


def test_nudge_clamps_to_the_knobs_own_bounds():
    state = TuningState(config.default_tunables())
    for _ in range(500):
        state.nudge("view_width", +1, fast=True)
    assert state.values["view_width"] == config.TUNABLES["view_width"].hi
    for _ in range(500):
        state.nudge("view_width", -1, fast=True)
    assert state.values["view_width"] == config.TUNABLES["view_width"].lo
