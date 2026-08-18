# Session S10 — The path map

**You are session S10 of Gravi.** Read `docs/superpowers/plans/2026-08-17-gravi-session-map.md` first.

**Blocked on:** S1 merged (the chain retains cleared chamber outlines — task 2 of S1 puts them there for you). Fully useful only once S9's rival exists, but it can and should be built before that.

---

## Goal

At the end of a run, zoom out and draw the whole route through the chamber chain. Core spec §6.

## Scope

`src/gravi/pathmap.py`: sample position every few frames during a run, keep the simplified chamber outlines the chain already retains, and render the full route at end-of-run — plus the personal-best line overlaid on future attempts, and the rival's path in another colour once S9 lands.

## Definition of done

- [ ] The map draws the actual route, and the tight orbits that earned the distance score are visible in it — this is what makes the score visually honest
- [ ] Sampling cost stays under 1% of frame time (`tools/perf_probe.py`), and the retained path is bounded in memory for a very long run
- [ ] The personal-best line persists via `storage.py` and fails soft in the browser
- [ ] The image is produced at a shareable resolution with zero additional art
- [ ] The rival's path draws alongside in another colour, showing exactly where it took the other branch and where it got ahead — this is the **perception layer** for §5, and a rival that learns you is worthless if the player cannot perceive it
- [ ] Rendering the map is a pure function of the recorded path plus outlines, so it can be tested headlessly by reading pixels the way `test_neon.py` already does

## Note on why this is cheap

Implementation cost is small, but it constrains the architecture: the run must **retain chamber geometry** rather than discarding it behind the camera. That constraint is already satisfied — S1 was instructed to keep `ChamberChain.outlines` from its first commit for exactly this reason. If you find it has been optimised away, restore it before writing anything else.
