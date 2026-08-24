from gravi import config


def test_every_tunable_default_is_inside_its_own_bounds():
    for name, (default, step, lo, hi) in config.TUNABLES.items():
        assert lo <= default <= hi, f"{name} default {default} outside [{lo}, {hi}]"
        assert step > 0, f"{name} step must be positive"


def test_default_tunables_returns_a_fresh_dict():
    a = config.default_tunables()
    b = config.default_tunables()
    a["k_attract"] = 999.0
    assert b["k_attract"] == config.TUNABLES["k_attract"][0]


def test_gravity_is_a_magnitude_now():
    assert "gravity_y" not in config.TUNABLES
    assert config.TUNABLES["gravity"].default == 500.0


def test_flip_and_chamber_knobs_are_tunable():
    assert config.TUNABLES["flip_duration"].lo == 0.0
    assert config.TUNABLES["flip_duration"].hi >= 0.6
    assert config.TUNABLES["chamber_depth"].lo <= 800.0
    assert config.TUNABLES["chamber_depth"].hi >= 2600.0
    assert "chamber_half_width" in config.TUNABLES


def test_the_field_of_view_knobs_are_tunable():
    """Sweeping how far ahead you can see is the point; both are draw-time
    only, so neither may be something the chain is rebuilt from."""
    view = config.TUNABLES["view_width"]
    assert view.hi >= 4000.0
    assert view.lo <= float(config.WINDOW_WIDTH)   # 1:1 is still reachable
    lead = config.TUNABLES["camera_lead"]
    assert lead.lo == 0.0
    assert lead.hi <= 0.5


def test_the_game_opens_at_one_to_one():
    """Reversed on 2026-08-19 by the author, who asked for more room in FRONT
    rather than a wider view of everything. Room ahead is camera_lead's job
    now; view_width stays available for anyone who does want the whole view
    pulled back."""
    assert config.TUNABLES["view_width"].default == float(config.WINDOW_WIDTH)


def test_the_lead_is_what_buys_room_ahead():
    lead = config.TUNABLES["camera_lead"]
    assert lead.default > 0.0
    assert lead.hi <= 0.45   # beyond this the player is against the screen edge


def test_the_turn_cadence_is_tunable():
    """Gravity turning at every arrow is what made the corridor exhausting, so
    how often it turns has to be sweepable while playing."""
    low = config.TUNABLES["turn_gap_min"]
    high = config.TUNABLES["turn_gap_max"]
    assert low.default == 3.0
    assert high.default == 7.0
    assert low.lo >= 1.0


def test_the_surface_and_charge_knobs_are_tunable():
    """None of these is settled, and the playtest sweeps them live."""
    assert config.TUNABLES["wall_reach"].default == 260.0
    assert config.TUNABLES["repel_charges_max"].default == 3.0
    assert config.TUNABLES["repel_charge_seconds"].default == 0.35
    assert config.TUNABLES["repel_min_spend"].default == 0.5
    assert config.TUNABLES["repel_regen"].default == 0.4
    assert config.TUNABLES["repel_attach_bonus"].default == 0.5


def test_a_press_floor_can_never_exceed_the_tank():
    """A floor larger than the maximum would make repel permanently unusable:
    every press would be unaffordable no matter how long the player waited."""
    assert config.TUNABLES["repel_min_spend"].hi <= config.TUNABLES["repel_charges_max"].lo
