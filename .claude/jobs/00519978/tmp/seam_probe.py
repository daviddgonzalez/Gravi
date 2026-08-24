import sys
sys.path.insert(0, "/home/ddgg0/projects/Gravi/.claude/worktrees/s1-chambers-and-rotation/src")
sys.path.insert(0, "/home/ddgg0/projects/Gravi/.claude/worktrees/s1-chambers-and-rotation/tests")

from test_sim import make_world, _seek_chamber
from gravi.field import Charge

w = make_world(flip_duration=0.0)
ch = _seek_chamber(w, turning=True)   # current chamber turns at ITS exit
nxt = w.chain.by_index(ch.index + 1)  # already generated (generate_ahead=4)
print("old chamber: entry", ch.entry, "direction", ch.direction, "turn", ch.turn,
      "half_width", ch.params.half_width, "depth", ch.params.depth)
print("next chamber: entry", nxt.entry, "direction", nxt.direction)

hw = ch.params.half_width
depth = ch.params.depth

# Construct a point deep inside the "inside corner" overlap zone: near old's
# exit (large t, close to depth) and hugging the wall on the side the turn
# bends toward, so it should ALSO fall inside next chamber's box.
# The turn side is ch.turn (+1 or -1); the wall that overlaps with `nxt` is the
# one on the side the corridor turns TOWARD (matches the hand-derived case).
side = float(ch.turn)  # try +1 (turn direction) first; nearest_wall breaks ties by u>=0 -> -px,-py
u = side * (hw - 5.0)      # 5 units shy of that wall, comfortably not dead
t = depth - 100.0          # 100 units short of the exit arrow -> still "current" chamber
x, y = ch.world(t, u)

print(f"\nprobe point: world=({x:.2f},{y:.2f})  old-local t={t:.2f} u={u:.2f}")

# Is this point also inside next chamber's box (0<=t_next<=depth, |u_next|<=hw)?
t_next, u_next = nxt.local(x, y)
print(f"in NEXT chamber's local frame: t_next={t_next:.2f} u_next={u_next:.2f} "
      f"(inside next box: {0.0 <= t_next <= nxt.params.depth and abs(u_next) <= nxt.params.half_width})")

# chain.current is still `ch` (old) because old-t < depth.
w.x, w.y = x, y
assert w.chain.current.index == ch.index, "sanity: still tracked as old chamber"

dist_old, normal_old = ch.nearest_wall(x, y)
dist_next, normal_next = nxt.nearest_wall(x, y)
print(f"\nnearest_wall via chain.current (OLD, what sim.py actually uses): "
      f"distance={dist_old:.2f} normal={normal_old}")
print(f"nearest_wall via the NEXT chamber (what a 'geometrically real' wall "
      f"lookup might use instead): distance={dist_next:.2f} normal={normal_next}")

# What does the actual death boundary (_check_bounds) key off? Also `ch` (old).
print(f"\nold-frame |u|={abs(u):.2f} vs half_width+side_grace="
      f"{ch.params.half_width + ch.params.side_grace:.2f}  (this is what can kill the player right now)")
