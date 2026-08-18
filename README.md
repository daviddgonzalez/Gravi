# Gravi

You never jump. You push and pull against the world.

Gravi is an endless 2D physics game with one verb: your **charge**. Hold attract and a
charged node whips you around it; hold repel and you kick off a surface without touching
it. Node cores are solid, so your approach angle decides whether an anchor is a slingshot
or a wall. Gravity arrows rotate the world as you fly through them, and the run is a chain
of procedurally generated chambers that get harder the further you go.

A rival that has watched every run you've made runs the same chain. It never touches you —
it just spends your anchors before you get to them.

## Play it

**[daviddgonzalez.github.io/Gravi](https://daviddgonzalez.github.io/Gravi/)** — runs in
the browser, no install. Hold **J** or left mouse to attract, **K** or right mouse to
repel. Published from `main` by `.github/workflows/deploy.yml`.

Natively:

    pip install -e ".[dev]"
    python main.py

## Status

Slice 1 shipped and was judged playable: one room, live tuning, an in-session editor and
a neon renderer. Slice 2 (gravity arrows and camera) is designed and not yet built.
Start here:

- [Core design spec](docs/superpowers/specs/2026-08-11-gravi-core-design.md)
- [Slice 1 verdict](docs/superpowers/runbooks/2026-08-11-slice-1-feel-verdict.md)
- [Web build notes](docs/web-build.md)

Gravi is a from-scratch successor to [BlueBall](../BlueBall). BlueBall is untouched;
the parts of it that survive are ported deliberately, by copy.
