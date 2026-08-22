# Charged surfaces, and a cost for repel

**Status:** approved in outline 2026-08-22, pending spec review.

## 1. The problem this solves

Slice 2's criterion 3 is *"a bad crossing is your fault."* The author played the
post-A4 build on 2026-08-22 and passed it with one named exception:

> "the only deaths that feel unlucky are when you flip gravities and no nodes
> are near"

That is not a crossing the player got wrong. Both of the player's verbs —
attract and repel — require a node, so a moment with no node in reach is a
moment with **no verb at all**. The terrain, not the player, decided.

Core spec §2.3 already assigned the answer and it has simply never been built:

> Repel gets a permanent job: the emergency out when an approach was misjudged.
>
> Charged **surfaces** obey the same law. Repel off a wall to launch without
> touching it; attract to a wall to slam flat against it and kill a bad arc.

A corridor always has walls. Today they are lethal boundaries and nothing else.

## 2. What the geometry actually does at a turn

Measured 2026-08-22 across twelve seeds, at the moment of crossing a turn at
full fall speed. Every seed, identically:

| Quantity | Value |
|---|---|
| Entry lateral offset | `0.0` — dead centre (§4.3 of the slice 2 spec) |
| Speed **across** the new corridor | `±600` — the full speed cap |
| Speed **along** the new corridor | `0.0` |
| Time until a wall is reached | `0.77 s` |

Because a 90° turn rotates the corridor and **not** the velocity, everything the
player carried down the old corridor becomes lateral speed in the new one. Three
consequences shape this design:

1. **A wall is the one guaranteed feature of every post-turn moment.** You are
   always crossing toward one, always about 0.77 s away. Anchoring the emergency
   out to walls matches the geometry better than anchoring it to anything else.
2. **The reach does not need to span the corridor.** An earlier draft of this
   design set the wall reach above the half-width so that a player sitting at
   dead centre could still push. That was wrong: nobody sits at dead centre. A
   node-scale reach engages roughly 0.27 s into the window, leaving most of it
   to press early and ride the force up as it ramps — a timing skill rather
   than a button that always works.
3. **Every turn resets your fall speed to zero.** Gravity has to rebuild it from
   nothing. This is why the post-flip moment feels vulnerable, and it is worth
   knowing before anyone tunes it away: it is also the game's strongest existing
   expression of "speed is earned, not handed to you."

## 3. Charged surfaces

**Walls become repel-only surfaces.** Wall-attract (§2.3's "slam flat against
it") is deliberately deferred — see §7.

**The law is the node's law**, as §2.3 requires:

```
distance = half_width - |u|          # to the nearer wall
force    = k_repel * (wall_reach - distance)     for distance < wall_reach
         = 0                                      otherwise
```

capped by `force_max`, directed along the inward normal — away from the wall,
across the corridor. Zero at the rim, strongest at the surface, exactly like
node repel.

**The nearest wall only.** Not both. At or near the centre lane the two walls
would push equally and cancel, which would delete the force precisely in the
middle of the corridor. Ties break to one side deterministically, because the
validator has to reproduce it.

**A node in range always wins; the wall is the fallback.** This aims the feature
squarely at the no-verb moment and leaves node play untouched. It also means the
rule is easy to state to a player: *the wall is what you have when you have
nothing else.*

**No latch.** A node repel latches and breaks on leaving the ring. A wall is
continuous — there is nothing to hold on to and nothing to break — so the wall
push simply applies while the button is held and the player is in reach.

## 4. Repel costs charge

Repel stops being free. This is the author's requirement, and the reasoning is
that an unlimited emergency out is a button you hold whenever you are unsure,
which is the same degeneracy §2.3 was written to kill, on the other button.

**The cost applies to every repel**, against a node or against a wall. It is the
verb that costs, not the target — otherwise the cheap option is always the one
the player should take, and the choice stops being about the situation.

**Three charges, drained continuously.** One charge is `repel_charge_seconds` of
push. Holding spends a full charge; a tap spends what it uses. There is no
discrete inventory to track, and the tap-versus-hold decision becomes a matter
of timing rather than accounting.

**A press that produces force costs at least half a charge.** Precisely: a press
costs `max(seconds_pushed / repel_charge_seconds, repel_min_spend)`, settled when
the press ends. Draining below the floor mid-press is not possible, because the
floor is reserved when the first force is produced and the remainder is drained
as it is used. Without the floor, a rapid micro-tap is free and the spam this
exists to prevent comes back in a new form.

**A press that produces no force costs nothing.** Holding repel in open space,
away from every node and wall, is not punished. The player is allowed to be
wrong about whether something was in reach.

**Below half a charge, repel does not fire at all.** A push that could not be
paid for must not start, or the floor is meaningless.

**Recovery is passive regen plus a bump on every new attach.** Both matter, for
different reasons:

- The **attach bump** keeps the swing loop paying twice: grabbing a node is
  already how you steer, and now it is also how you rearm.
- The **passive trickle** is the safety valve, and it is not optional. Node
  recovery is unavailable in exactly the stretch this mechanic exists for — a
  flip into terrain with no nodes near is also a flip with nothing to recharge
  on. Passive regen is the only thing topping the player up during the gap.

**Regen pauses while a push is draining**, so the two never fight over the same
frame.

### 4.1 The constraint the playtest imposes

**The charge budget must never be the reason the emergency out was unavailable
at a flip.** The whole feature exists to remove a death that felt unlucky; a
meter that is empty at the moment of a turn reintroduces exactly that death
wearing a different hat. This is a tuning claim, and it is falsifiable: at the
proposed defaults, the ~10–23 s between turns (amendment A4's cadence) regenerates
several charges, so arriving at a turn empty should be rare and should always be
traceable to the player having spent them.

If playtesting shows otherwise, the fix is the regen rate, not the removal of
the floor.

### 4.2 Proposed starting values

All tunable, all live-adjustable in the overlay, none of them settled.

| Knob | Value | Note |
|---|---|---|
| `wall_reach` | 260.0 | Node scale (node radii are 190–280). Engages ~0.27 s into the 0.77 s post-turn window |
| `repel_charges_max` | 3.0 | Enough for tap-tap-hold without becoming inventory |
| `repel_charge_seconds` | 0.35 | Seconds of push per charge |
| `repel_min_spend` | 0.5 | Charge floor for a press that produced force |
| `repel_regen` | 0.4 | Charges per second, passive |
| `repel_attach_bonus` | 0.5 | Granted once per NEW attract latch |

## 5. The readout is light, not UI

**Three short arcs around the player**, in the repel hue, each fading as its
charge is spent. Partial charges show as a partly-lit arc.

This is deliberate and it is the part that keeps §2.3's intent alive. Gravi's
rule is that light *is* the ruleset (§7): hue is charge, the glow ring is the
influence radius, beam intensity is force magnitude. A resource drawn on the
player in the colour of the verb it powers is the same language. A bar in the
corner of the screen is a different language, and the core spec's summary table
rejects it by name.

The arcs must be readable at a glance while moving. If they are not, the
fallback is the player's own aura brightness — less countable, still diegetic —
and that is a playtest question, not a decision to make here.

## 6. Amendment to core spec §2.3

§2.3 is titled "Solid nodes are the entire balance system" and says the solid
core *"does the work that a stamina meter, a cooldown, and a tutorial would
otherwise do"*. §11's summary table records the balance system as "no meter or
UI". This design adds a meter, so the amendment must be explicit:

> **Amendment — 2026-08-22. Repel has a cost; attract does not.**
>
> §2.3 stands unchanged for **attract**: the solid core is still the entire
> balance system for the pull, still geometric, still no meter. Approach angle
> still decides whether a node is a slingshot or a wall, and that remains the
> deep skill.
>
> **Repel** gains a charge cost, because the argument in §2.3 does not reach it.
> Solid cores make holding attract fatal, which is what makes the pull
> self-limiting. Nothing makes holding repel fatal — it pushes you *away* from
> the thing that would punish you — so the pull's geometric limiter has no
> equivalent on the push, and repel was unlimited by omission rather than by
> design.
>
> The cost is drawn **in light on the player**, not in a UI panel, so §11's
> "no meter or UI" holds as to UI and is amended as to meter.
>
> §2.3's assignment of repel's job — *"the emergency out when an approach was
> misjudged"* — is strengthened rather than weakened: charged surfaces make the
> out available where no node exists, which is where it was previously missing.

## 7. Deliberately out of scope

- **Wall attract** ("slam flat against it and kill a bad arc", §2.3). One new
  interaction is easier to judge than two. Add it once wall-repel has been
  played.
- **Charged surfaces as an escalation entity.** The core spec's table introduces
  them at chambers 4–8 with varying properties. This design makes every corridor
  wall a surface, uniformly, from chamber zero. Per-chamber variation is S6's.
- **Attract costing anything.** It does not, and §2.3 explains why it must not.

## 8. Where the code goes

| Unit | Responsibility |
|---|---|
| `chamber.py` | `Chamber.nearest_wall(x, y)` → distance and inward normal. Geometry belongs with the chamber, and it stays pure. |
| `field.py` | `surface_force(distance, normal, params, reach)` — the wall's force law, beside `charge_force`. Pure, shared with the validator and trainer. |
| `sim.py` | Charge state, drain, regen, the attach bump, and the node-then-wall fallback in the repel path. |
| `config.py` | The six tunables in §4.2. |
| `render/neon.py` | `draw_charges` — the arcs. |
| `main.py` | Passes the charge level to the draw. |

Nothing here touches attract, the rigid rope, gravity, or the camera.

## 9. Testing

- The wall force is zero at the reach, maximal at the surface, and directed
  inward — the same shape as node repel.
- Only the nearest wall contributes; a player at dead centre gets a real push,
  not two that cancel.
- A node in range takes priority over a wall.
- Charge drains only while force is produced; a press in open space is free.
- A press that produced force costs at least `repel_min_spend`.
- Repel does not fire below `repel_min_spend`.
- Regen is passive, pauses while draining, is bumped once per new attach, and
  never exceeds `repel_charges_max`.
- **The integration test that matters:** a player crossing a turn at full speed,
  with no node in reach, can press repel and change their trajectory before
  reaching the wall. This is the death the whole design exists to remove, so it
  gets an explicit test rather than being implied by unit tests.
- `chamber.py` and `field.py` stay pure — no pygame (`tests/test_purity.py`).

## 10. Open questions for the playtest

- Do three arcs read at a glance while moving, or is the count invisible in
  practice?
- Is `wall_reach` 260 enough to make the out feel available, or does it demand
  more precision than the 0.77 s window allows?
- Does the half-charge floor actually stop tap-spam, or does it just make the
  optimal play "tap at exactly the floor, repeatedly"?
- Does repel costing charge make the player hoard it and die holding a full
  meter — the opposite failure to the one this fixes?
