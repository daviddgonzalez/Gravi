import sys
sys.path.insert(0, "/home/ddgg0/projects/Gravi/.claude/worktrees/s1-chambers-and-rotation/src")
import random
from gravi.chamber import ChamberParams, make_chamber

cp = ChamberParams()  # real defaults: half_width=460, wall_reach zone starts at u=200
wall_reach = 260.0
half_width = cp.half_width
zone_start = half_width - wall_reach  # 200

total_nodes = 0
overlap_nodes = 0  # node's ring extends past zone_start (into the wall-reach band) on the near side
touches_or_past_wall = 0

for seed in range(200):
    rng = random.Random(seed)
    ch = make_chamber(0, (0.0, 0.0), (0.0, 1.0), cp, rng=rng, turn=0)
    for n in ch.nodes:
        total_nodes += 1
        # local u of node center (direction=(0,1), perp=(-1,0), entry=(0,0)):
        u = -n.x  # since perp = (-1,0): u = dx*px = x*(-1)... wait compute via ch.local
        t, u = ch.local(n.x, n.y)
        far_edge = abs(u) + n.radius
        if far_edge > zone_start:
            overlap_nodes += 1
        if far_edge >= half_width:
            touches_or_past_wall += 1

print(f"total nodes sampled: {total_nodes}")
print(f"nodes whose ring reaches into the wall_reach band (far edge > {zone_start}): {overlap_nodes} ({100*overlap_nodes/total_nodes:.1f}%)")
print(f"nodes whose ring reaches the wall or past it (far edge >= {half_width}): {touches_or_past_wall} ({100*touches_or_past_wall/total_nodes:.1f}%)")
