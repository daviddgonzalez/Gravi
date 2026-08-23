import sys, math
sys.path.insert(0, "/home/ddgg0/projects/Gravi/.claude/worktrees/s1-chambers-and-rotation/src")
sys.path.insert(0, "/home/ddgg0/projects/Gravi/.claude/worktrees/s1-chambers-and-rotation/tests")

import gravi.sim as sim
from gravi.field import Charge, FieldParams, Node
from gravi.chamber import ChamberChain, ChamberParams
from gravi.gravity import GravityState
from dataclasses import replace

PARAMS = FieldParams(k_attract=8.0, k_repel=12.0, force_max=1e9)

def chain_with(nodes, params=None):
    chain = ChamberChain(seed=0, params=params or ChamberParams())
    chain.chambers[0] = replace(chain.chambers[0], nodes=tuple(nodes))
    return chain

def make_world(nodes=(), flip_duration=0.3, gravity=500.0, spawn=None,
               chamber_params=None, player_radius=7.0, speed_max=600.0,
               fall_speed_max=600.0, rigid_rope=False, wall_reach=260.0):
    w = sim.World(
        chain=chain_with(nodes, chamber_params),
        params=PARAMS, gravity=gravity,
        gravity_state=GravityState(flip_duration=flip_duration),
        player_radius=player_radius, speed_max=speed_max,
        fall_speed_max=fall_speed_max, rigid_rope=rigid_rope,
        wall_reach=wall_reach,
    )
    if spawn is not None:
        w.x, w.y = spawn
    return w

def _seek_chamber(w, turning: bool):
    for _ in range(80):
        if (w.chain.current.turn != 0) == turning:
            return w.chain.current
        w.chain.advance()
    raise AssertionError("no chamber found")

# --- Monkeypatch World.step: replace the directional wall push with an
# isotropic drag on velocity whenever within wall_reach (same reach-gating,
# WRONG force direction/shape: opposes velocity instead of pushing off the
# wall's normal). ---

_orig_step = sim.World.step

DRAG_K = 6.0  # tuned so the effect is visible within the test's 120-step window

def wrong_step(self, charge):
    self.gravity_state.advance(self.dt)
    if self.dead:
        return
    gx, gy = self.gravity_state.direction()
    node = self._update_latch(charge)
    rigid = (self.rigid_rope and node is not None and charge is Charge.ATTRACT)
    self._update_rope(node, rigid)
    ax = gx * self.gravity
    ay = gy * self.gravity
    if node is not None and not rigid:
        from gravi.field import charge_force
        fx, fy = charge_force(self.x, self.y, node, charge, self.params,
                              ignore_radius=charge is Charge.ATTRACT)
        ax += fx
        ay += fy
    elif node is None and charge is Charge.REPEL:
        distance, normal = self.chain.current.nearest_wall(self.x, self.y)
        if distance < self.wall_reach:
            # WRONG: brakes velocity instead of pushing along the wall normal.
            ax += -DRAG_K * self.vx
            ay += -DRAG_K * self.vy
    self.vx += ax * self.dt
    self.vy += ay * self.dt
    self._clamp_speed(gx, gy)
    if rigid:
        nx, ny = self._rotate_on_rope(node)
    else:
        nx = self.x + self.vx * self.dt
        ny = self.y + self.vy * self.dt
    self.distance += math.hypot(nx - self.x, ny - self.y)
    self.x, self.y = nx, ny
    self.elapsed += self.dt
    self._check_bounds()
    if not self.dead:
        self._check_cores()

sim.World.step = wrong_step

# --- Run the exact integration test body ---
w = make_world(flip_duration=0.0)
ch = _seek_chamber(w, turning=True)
start = w.chain.at
w.x, w.y = ch.world(ch.params.depth - 2.0, 0.0)
w.vx = ch.direction[0] * 600.0
w.vy = ch.direction[1] * 600.0
for _ in range(20):
    w.step(Charge.NEUTRAL)
    if w.chain.at > start:
        break
assert w.chain.at > start, "the test needs an actual crossing"

nxt = w.chain.current
w.chain.chambers[w.chain.at - w.chain.chambers[0].index] = replace(nxt, nodes=())
nxt = w.chain.current
px, py = nxt.perp
before = w.vx * px + w.vy * py

for _ in range(120):
    w.step(Charge.REPEL)
    if w.dead:
        break

after = w.vx * px + w.vy * py
print(f"before={before:.3f} after={after:.3f} dead={w.dead}")
print("PASSES with wrong (drag) implementation:", abs(after) < abs(before))
