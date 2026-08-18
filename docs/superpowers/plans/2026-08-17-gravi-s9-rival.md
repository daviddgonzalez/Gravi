# Session S9 — The rival

**You are session S9 of Gravi.** Read `docs/superpowers/plans/2026-08-17-gravi-session-map.md` first.

**Blocked on:** S5's spec approved, S6's node depletion shipped, S7's measurement instrument running, S8's run event log recording.

**First move:** read S5's spec, then run `superpowers-extended-cc:writing-plans` against it.

---

## Goal

A second charged body running the same chamber chain, that never touches the player and hurts them anyway — by spending their anchors.

## Scope

**In:** `src/gravi/rival.py` and `src/gravi/playermodel.py`; the offline breeding of labelled brain styles (using S3's trainer and S7's measurement); runtime brain selection and weighting; the three-number aggression dial; intermittent pacing; the rival's on-screen presentation; cross-session identity and persistence via `storage.py`.

**Out:** background fine-tuning of a personal rival against the player's own recorded chamber sequences — explicitly an optional later tier (§5.2).

## Definition of done

- [ ] The rival never collides with the player, and nothing but hazards and node cores can kill the player — asserted as a test, because this is the property that keeps "I know why I died" true (§5.1)
- [ ] Nodes it spends deplete visibly, including three chambers ahead of the player, where the player watches the light go out (§7)
- [ ] Each labelled style is **verified to be that style**, not merely labelled one: a measurement over rollouts showing the tight-orbit brain actually orbits tighter than the wide-and-safe one
- [ ] The aggression dial changes observed behaviour across its range without retraining anything (§5.3)
- [ ] The rival is absent for stretches; absence is what makes reappearance mean something (§5.4)
- [ ] Its trajectory is replayable from a seed plus its brain (§9's replay fidelity), or the path map cannot be trusted
- [ ] A player who always takes the safe wide arc gets matched against a tight-orbit brain that reaches nodes first and burns them — demonstrated end to end with a synthetic player model, not asserted in prose
- [ ] Cold start behaves sensibly on a first-ever run with no model

## The constraint that defines this session

The rival is not the difficulty. The generator is. The rival is interference that is fair, readable, anticipatable and native to the mechanic — and it stays tunable only because the intelligence lives in the *selection*, not in a training loop that runs while the player plays (§5.2). Any design pressure toward "just retrain it a bit between runs" is the rejected tethered-rival concept coming back through a side door.
