# Session S11 — Calibration, escalation tuning, and ship

**You are session S11 of Gravi.** Read `docs/superpowers/plans/2026-08-17-gravi-session-map.md` first.

**Blocked on:** S6, S7, S9 and S10 all merged. This is the last session, and it is the one that decides whether the game is any good.

---

## Goal

Make the measured difficulty curve match what a human actually experiences, settle the escalation schedule with real play, and ship.

## Scope

**Calibration.** Core spec §4.4 is explicit: difficulty is measured *for the agent*, whose weaknesses are not a human's, and it needs calibration against real play data or the curve will be wrong in a specific, systematic direction. This is core spec §12's second open question, deliberately left until now because it cannot be settled before slice 4 exists.

- Collect real runs (S8's event log is the instrument)
- Fit the mapping from agent-measured difficulty to human-observed difficulty — death rate, time-to-clear, retry behaviour per archetype
- Re-emit the library with calibrated ratings, and re-verify the escalation schedule (§3.6) against it

**Escalation tuning.** Confirm — by playing — that the knob-rotation policy actually produces "steady pressure, constantly changing texture" rather than a curve that rises and a texture that does not change.

**The remaining open questions from core spec §12:**
- [ ] Hue assignments for the charge palette, and whether hostile-charge nodes are a separate entity or a node property
- [ ] Whether the fixed-camera accessibility mode needs a different node-field presentation to stay readable without the rotation cue
- [ ] Whether core contact stays unconditional death or becomes speed-gated (nominally resolved in slice 1, worth re-checking now that hazards and depletion exist)

**Accessibility and polish.** The fixed-camera option is required, not optional (§3.3) — some players will prefer it outright, and motion sickness at high flip frequency is a hard cap on an escalation axis. Verify it is genuinely playable at the shipped flip rates, not merely present.

## Definition of done

- [ ] A calibration runbook with real play data, in the style of the slice 1 feel verdict — including its coverage gaps stated plainly
- [ ] The shipped library is calibrated, and the difficulty curve is a single tunable curve over chambers cleared
- [ ] The browser build is deployed, played end to end, and linked from the README
- [ ] The full suite passes; the perf probe is inside budget; determinism, force-law purity and replay fidelity — core spec §9's three tests — all still hold
- [ ] `README.md` describes the game that exists, not the game that was designed
