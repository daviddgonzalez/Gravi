# Idea backlog — 2026-08-20

Four ideas raised during the slice 2 playtest, captured so none is lost, none is
half-built, and each can be specced properly when its turn comes. **Nothing here
is approved and nothing here is designed.** Each entry records the idea, what it
collides with, and what would have to be settled first.

They are listed in the order they should be taken, which is not the order they
were raised. The reasoning for that order is at the bottom.

---

## 1. Crystals — a ring of collectibles around a node

**The idea.** Crystals arranged in a circle around a node, worth points. Falling
straight down earns nothing; completing an arc around a node earns.

**Why it is first.** It attacks the "falling straight down is boring" problem
from the incentive side rather than the punishment side, and it pays the player
for exactly the behaviour the whole game is built on. It is also the smallest of
the four, and playing it would tell us whether ideas 2 and 3 are needed at all.

**What it collides with.** Session map invariant 6: *five entity types, and no
sixth — node, charged surface, hazard, gravity arrow, rival. A sixth entity
needs a spec amendment, not a commit.* A crystal is a sixth type.

**The case for the amendment.** The invariant exists because BlueBall died of
entities that were *additive rather than multiplicative* — adding a cannon did
not change what a spike meant. A crystal ring is multiplicative: it changes what
a **node** means. Today a node is grab-and-fling and the optimal use is the
shortest possible contact; a ring rewards completing the arc, which re-prices
every node already in the game. That is the bar the invariant sets, and this
clears it.

**Open before speccing.** Are crystals scored, or do they feed something (the
charge meter in idea 4)? Does taking one require the orbit, or just contact?
What stops a player farming one node forever — does the ring regenerate?

---

## 2. Mid-corridor hazards

**The idea.** Obstacles lying around the corridor, some of them in the middle,
so the straight-down path is not free.

**Cost.** Cheap in entity terms: this is **hazard**, already one of the five.

**What it collides with.** `chamber.py`'s standing rule that the centre lane must
be clear of cores while influence rings still reach across it, because every
player enters a turn on the centre line. Amendment A4 weakened that today —
straight seams now carry the player's lateral offset through, so most chambers
are no longer entered on the lane — but the rule still holds at a turn.

**Open before speccing.** Is the lane rule now "clear at turns only"? If so, the
generator needs to know which chambers turn before it places hazards, which it
now does (`turn_schedule`). Does a hazard kill, or deflect?

---

## 3. The repel charge system

**The idea.** Repel stops being always-available. Hold to spend a full charge,
tap to spend half. Charges recover passively, or by attaching to nodes. Usable
against the nearest node or against a wall.

**The wall half is already specced and needs no argument.** Core spec §2.3:
*"Charged surfaces obey the same law. Repel off a wall to launch without
touching it; attract to a wall to slam flat against it and kill a bad arc."*
Charged surface is one of the five, and the escalation table introduces them at
chambers 4–8. That is S6's work, not an amendment.

**The charge half contradicts a recorded decision.** Core spec §2.3 is titled
"Solid nodes are the entire balance system" and states the solid core *"does the
work that a stamina meter, a cooldown, and a tutorial would otherwise do"*. §11's
summary table lists the balance system as "no meter or UI". §2.3 also assigns
repel its job: *"the emergency out when an approach was misjudged."*

**The case for overruling it.** Unlimited repel makes a misjudged approach free.
Scarcity prices it, which sharpens the approach-angle skill §2.3 itself calls
"the deep skill". Recovering charge by attaching to nodes pays the player for the
behaviour the game wants, the same instinct as idea 1.

**The case against.** Slice 2's criterion 3 is "a bad crossing is your fault",
and it is still unjudged. A death from a misjudged angle is the player's fault; a
death because the meter was empty is only their fault if they could see it
coming. Any amendment must therefore require the meter to be legible without a
UI bar — this is a neon game where brightness and beam thickness already carry
information (spec §7) — and must not allow the emergency out to vanish silently.

**Open before speccing.** Does the charge gate repel only, or both charges? What
is the recovery rate, and is passive recovery even needed if attaching recovers?
Does a half charge push half as hard, or half as long?

---

## 4. L-shaped elbow chambers

**The idea.** Replace the flat exit arrow at a turn with a real corner: the
corridor bends, the outer wall is something you can slam into, and the inner
notch is the racing line. Gravity turns as you round it. Sides sized to the
current arrow, i.e. the full corridor width.

**Why it is last.** By far the largest. A chamber stops being a box, which
reaches into generation, `local()`/`world()`, the bounds check, the culling
window, the entry-offset rule (§4.3), and S10's path map. It is also the most
likely to be wasted: if ideas 1–3 fix how the corridor plays, the elbow is a
large change to something that already works.

**One thing that makes it cheaper than it looks.** Amendment A4 means turns now
happen every 3–7 chambers. An elbow would be a *rare special chamber*, and every
straight chamber between them stays exactly the box it is today. The elbow does
not have to be the general case.

**Open before speccing.** Does the outer wall kill, or is it a charged surface to
push off (idea 3)? What does the path map draw for an elbow? Does the entry
vector into the next chamber still come out well-defined?

---

## Why this order

Each of these changes what the others should be. Crystals may fix the falling
problem on their own, which would make hazards unnecessary. The charge system
changes what a wall is *for*, which changes what an elbow's outer wall should be.
The elbow is the most expensive thing to build and the most expensive thing to
throw away.

**And none of it should start before the slice 2 verdict.** That gate has been
open since 2026-08-17, the build has never been played for five minutes, and the
force-law constants cannot be frozen until it closes (session map invariant 2,
which blocks S7 from baking a chamber library). Gravity modes and the rigid rope
shipped today and have not been played either. Every idea above is a guess about
a game nobody has finished evaluating.
