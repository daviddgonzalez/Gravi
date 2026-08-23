import sys
sys.path.insert(0, "/home/ddgg0/projects/Gravi/.claude/worktrees/s1-chambers-and-rotation/src")

from gravi.field import Charge, FieldParams, Node, charge_force, surface_force
from gravi.chamber import ChamberParams, Chamber

# --- Real game defaults (config.py TUNABLES) ---
k_repel = 15.0
k_attract = 15.0
force_max = 4500.0
wall_reach = 260.0
half_width = 460.0

params = FieldParams(k_attract=k_attract, k_repel=k_repel, force_max=force_max)
cp = ChamberParams(half_width=half_width)
ch = Chamber(index=0, entry=(0.0, 0.0), direction=(0.0, 1.0), turn=0, nodes=(), params=cp)

print("=== Node-rim -> wall-fallback transition, real game constants ===")
# Node whose ring just touches the wall: center at u=200, radius=260 -> edge at u=460 (the wall)
node_u = 200.0
node_radius = 260.0
node = Node(x=ch.world(300.0, node_u)[0], y=ch.world(300.0, node_u)[1],
            radius=node_radius, core_radius=15.0)

for eps in (0.0, 1e-6, 0.5, 2.0, 5.0):
    # Position just outside the ring, at u = node_u + node_radius + eps
    u = node_u + node_radius + eps
    x, y = ch.world(300.0, u)
    # Node force (will be 0 since outside radius / at radius)
    fx, fy = charge_force(x, y, node, Charge.REPEL, params)
    node_mag = (fx**2 + fy**2) ** 0.5
    # Wall fallback force at this same point
    dist, normal = ch.nearest_wall(x, y)
    wfx, wfy = surface_force(dist, normal, params, wall_reach)
    wall_mag = (wfx**2 + wfy**2) ** 0.5
    print(f"eps={eps:7.4f}  u={u:8.3f}  dist_to_wall={dist:8.3f}  "
          f"node_force={node_mag:9.3f}  wall_force={wall_mag:9.3f}")

print()
print("=== Just-inside-ring force (last node-governed step) vs eps=1e-6-outside wall force ===")
for r_in in (node_radius - 0.001, node_radius - 0.05, node_radius - 1.0, node_radius - 5.0):
    u = node_u + r_in
    x, y = ch.world(300.0, u)
    fx, fy = charge_force(x, y, node, Charge.REPEL, params)
    node_mag = (fx**2 + fy**2) ** 0.5
    print(f"r_in={r_in:9.4f} (radius-{node_radius-r_in:.4f})  node_force={node_mag:9.3f}")

print()
print("=== Peak node force (contact) and peak wall force (at surface) for comparison ===")
contact_node = Node(x=ch.world(300.0, 0.0)[0], y=ch.world(300.0, 0.0)[1], radius=210.0, core_radius=15.0)
x, y = ch.world(300.0, 0.5)  # just off center, near contact
fx, fy = charge_force(x, y, contact_node, Charge.REPEL, params)
print("near-contact node force:", (fx**2+fy**2)**0.5)
wfx, wfy = surface_force(0.0, (1.0,0.0), params, wall_reach)
print("at-wall wall force magnitude:", (wfx**2+wfy**2)**0.5, "= k_repel*wall_reach =", k_repel*wall_reach)
