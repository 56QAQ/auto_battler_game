# Developing hsrsim: kits, light cones and relic sets

This guide explains how to add game content on top of the engine. Everything numeric
comes from the datamined snapshot (`hsrsim/data/gamedata`), so content code encodes
**logic only** and reads its numbers from the data.

## 1. Where things live

| Path | What |
|---|---|
| `hsrsim/battle.py` | Engine: timeline, turns, actions (`Action`), hits (`Hit`), damage, toughness, break, modifiers, SP, energy |
| `hsrsim/modifiers.py` | `Modifier` (buff/debuff/field), `DotModifier`, `Tick`, `Stacking`, `ModKind`, helpers `buff/debuff/hidden` |
| `hsrsim/stats.py` | Stat keys (`S.ATK_PCT`, `S.CRIT_DMG`, `S.DMG_PCT`, ...) and qualifier syntax |
| `hsrsim/events.py` | Event names (`E.ACTION_END`, `E.BEFORE_HIT`, ...) |
| `hsrsim/kits/<name>.py` | One character kit per module (`@register` class deriving `Kit`) |
| `hsrsim/gear/relics.py` | Relic set / planar ornament conditional effects |
| `hsrsim/gear/lightcones_*.py` | Light cone conditional effects |
| `tools/build_gamedata.py` | Rebuilds the data snapshot after a game patch |

Print everything needed to implement a character (skills with parameters at max level,
traces, eidolons): `python tools/kitinfo.py "Jing Yuan"` (append `+` for the enhanced kit).

Audit a kit against the game's own ability script (modifier lifetimes / `LifeStepMoment`, events,
hit splits, gameplay operations): `python tools/ability_summary.py "Jing Yuan" [--grep Passive]`.

## 2. Stats

Stats are string keys summed additively. A key can carry a qualifier after `:` that
restricts it to hits whose element or damage tags match:

* `dmg%` all DMG, `dmg%:Fire`, `dmg%:ult`, `dmg%:fua`, `dmg%:dot`, `dmg%:basic`, `dmg%:skill`, `dmg%:memosprite`
* `crit_rate`, `crit_dmg` (+ qualifiers, e.g. `crit_dmg:ult`)
* `atk%`, `atk_flat`, `hp%`, `hp_flat`, `def%`, `def_flat`, `spd%`, `spd_flat`
* `break_effect`, `break_eff` (Weakness Break Efficiency), `break_dmg%`, `super_break_dmg%`
* `err` (energy regen, 0 = 100%), `ehr`, `effect_res`, `effect_res_pen`, `heal%`
* `def_ignore`, `res_pen` (+ `res_pen:Fire` ...), `weaken`
* target side: `vuln` (DMG taken, `vuln:dot`, `vuln:break` ...), `def_reduction`,
  `res_reduction` (+ element), `mitigation` (multiplicative), `res:<Element>`
* `final_dmg` — the multiplicative "final DMG" layer
* Elements use data names: `Physical Fire Ice Thunder Wind Quantum Imaginary`.

Damage tags (`DmgTag`): `basic skill ult fua dot break super_break additional memosprite elation true`.

## 3. Modifiers

```python
from hsrsim.modifiers import Modifier, ModKind, Tick, Stacking, hidden

Modifier(
    "Name",
    stats={S.ATK_PCT: 0.2},          # per stack when per_stack=True
    duration=2,                       # None = permanent
    tick=Tick.HOLDER_TURN_END,        # when the duration counts down (see below)
    kind=ModKind.BUFF,                # BUFF / DEBUFF / OTHER
    stacking=Stacking.REFRESH,        # REFRESH / STACK / INDEPENDENT
    max_stacks=1,
    scope=None,                       # callable(entity)->bool: turns the modifier into a FIELD
    dyn=None, dyn_keys=set(),         # dynamic stat: dyn(mod, key, entity) -> float
    skip_first_tick=None,             # None = engine default rule (see below)
    key=None,                         # stacking identity; default "<name>#<source uid>"
    tags=set(),
)
```

* **Apply**: `battle.apply(mod, target, source)`; with a hit chance:
  `battle.try_debuff(mod, target, source, base_chance, fixed=False, debuff_type=None)`.
* **Durations** (validated against the datamine, see `docs/RESEARCH.md`):
  * default: counts down at the end of the holder's turn; a modifier applied during the
    holder's own turn skips that turn's decrement ("lasts for 1 turn" from your own Skill
    covers your next turn).
  * `skip_first_tick=False` for effects flagged `LifeStepImmediately` in the game
    (Bronya ult, Tingyun ult, Welt imprisonment): the current turn counts.
  * `Tick.HOLDER_TURN_START`: DoTs, break states, "until the start of the next turn", and every modifier whose
    script header shows `LifeStepMoment=ModifierPhase1End` (it counts down in the holder's turn-start phase,
    after DoTs).
  * `Tick.SOURCE_TURN_START`: caster-held zones/auras ("decreases by 1 at the start of X's
    every turn"): Ruan Mei, Robin, Huohuo, Tribbie, Sunday, ...
* **Fields / auras**: give the modifier a `scope` and apply it to its holder (usually the
  caster): its stats apply to every entity in scope. Fields with an explicit `key` count
  once even if several sources apply them ("this effect cannot be stacked").
* **Hidden permanent stats** (traces, gear): `hidden(name, stats)` (never ticks, not dispellable).
* **Listeners** that live exactly as long as a modifier: override `on_apply(self, battle)` and
  call `self.listen(event, fn)`.

## 4. Events

Register with `battle.events.on(name, fn, owner=self)` (kits and gear have `self.on(...)`).
The callback receives an `Ev`; payload attributes are listed in `hsrsim/events.py`.

| Event | Payload | Typical use |
|---|---|---|
| `BATTLE_START` | – | start-of-battle effects |
| `TURN_START` / `TURN_END` | `entity`, `extra` | "at the start of the wearer's turn" |
| `PRE_TURN` | `entity`, set `ev.data["cancel"]` | cancel a turn (Ruan Mei Rebloom) |
| `ACTION_START` / `ACTION_END` | `action` (`.actor .owner .kind .target .attacked .hits`) | "when/after using Skill" |
| `ATTACK_START` / `ATTACK_END` | `attack` (an `Action`) | "after attacking" (once per attack) |
| `BEFORE_HIT` | `hit` | conditional DMG bonuses: `ev.hit.add(key, value)` |
| `AFTER_HIT` | `hit` (`.damage .broke .was_broken .toughness_potential`) | per-hit triggers |
| `BREAK` | `target attacker credited element hit` | "after breaking weakness" |
| `KILL` | `target killer` | "when an enemy is defeated" |
| `MOD_APPLIED` / `MOD_REMOVED` | `mod target` | "after inflicting a debuff" |
| `ULT_USED` | `entity` | "when an ally uses Ultimate" (fires before the ult action) |
| `SP_CHANGED` | `delta entity` | SP consumption |
| `ENERGY_OVERFLOW` | `entity amount` | Energy lost to the Max Energy cap ("overflow Energy" traces) |
| `ENERGY_GAINED`, `HP_CHANGED` (`entity delta source`), `ALLY_ATTACKED`, `DOT_TRIGGERED`, `ENEMY_SPAWNED`, `WAVE_START` | | |

`ActionKind`: `BASIC SKILL ULT FUA MEMOSPRITE EXTRA ENEMY`.

## 5. Hits and damage helpers (inside an action)

```python
with self.action(ActionKind.SKILL, "skill", target) as act:   # SP + energy from the skill data
    act.hit(target, mult, stat="atk", toughness=20, splits=[0.3, 0.7])
    act.blast(target, main_mult, adj_mult, toughness=(20, 10))
    act.aoe(mult, toughness=10, main_target=target)
    act.bounce(target, count=5, mult=0.5, toughness=5)
```

Outside of attacks: `battle.additional_damage(...)`, `battle.dot_damage(...)`,
`battle.break_damage(...)`, `battle.super_break(...)`, `battle.true_damage(...)`,
`battle.detonate(target, ratio)`, `battle.reduce_toughness(...)`.
Other helpers: `battle.advance(entity, 0.25)`, `battle.delay(...)`, `battle.gain_energy(c, x, fixed=False)`,
`battle.gain_sp/use_sp`, `battle.lose_hp`, `battle.queue_action(fn, owner)` (follow-ups),
`battle.queue_extra_turn(entity)`, `battle.add_unit(Summon(...))`.

Healing: `battle.heal(target, base, source, bonus=0.0)` takes the **base** amount (scaling stat × multiplier + flat)
and applies the healer's Outgoing Healing (`heal%` + a conditional `bonus` from the kit text) and the target's
Incoming Healing (`heal_taken%`); never multiply by them in the kit. "Sets HP to X%" and revives use
`battle.set_hp(target, value, source)` (no boosts, no `HEALED`). `self.char.on_timeline = False` takes a unit off the
Action Order (gauge frozen) until set back to `True`.

## 6. Writing a kit

```python
@register
class MyChar(Kit):
    char_id = "1234"
    def setup(self): ...            # listeners, permanent passives
    def basic(self, target): ...
    def skill(self, target): ...
    def ult(self, target): ...
    def take_turn(self): ...        # rotation policy (default: Skill if SP else Basic)
```

Parameters: `self.p("skill", i)` (current level incl. eidolons), `self.tp(n, i)` major trace
A2/A4/A6 (`n` = 1/2/3, check `self.trace(n)`), `self.ep(n, i)` eidolon parameters (check `self.e(n)`),
`self.toughness("skill", which)` where `which` = 0 main target, 1 all targets (AoE), 2 adjacent.

### Common patterns

| Mechanic | How |
|---|---|
| Follow-up attack | `self.battle.queue_action(fn, self.char, "label")`; inside `fn` open `self.action(ActionKind.FUA, "talent", target)` |
| Counter when an ally is attacked | listen `E.ALLY_ATTACKED` (`ev.attacker` enemy, `ev.targets`); `E.BEFORE_ALLY_HIT` fires per hit before shields absorb it |
| "When targeted by an ally's ability" | listen `E.ALLY_TARGETED` (`ev.action`, `ev.target`) |
| "Slowed" enemies | `hsrsim.modifiers.is_slowed(enemy)`; tag your own SPD debuffs `"slow"` |
| Extra turn | `self.battle.queue_extra_turn(self.char)` |
| Enhanced Basic ATK / Skill (other skill ID) | `rec = self.sk("<skill id>")`; `self.action(ActionKind.BASIC, rec, target, sp=-2)` (explicit SP cost); params: `rec["params"][self.level_of(rec) - 1]` |
| Resource that replaces Energy (Acheron, Rappa ...) | override `ult_ready()` and `pay_ult_cost()`; set `self.char.max_energy = 0` if the unit has no Energy |
| Countdown / summon with own SPD | `self.battle.add_unit(Summon(name, self.char, spd=90, on_turn=fn))`, remove with `self.battle.remove_unit(u)`; take the owner off the bar with `self.char.on_timeline = False` |
| Memosprite (Remembrance) | `memo = self.summon_memosprite("Name", on_turn=fn)` (HP/SPD from `AvatarServantConfig`, other stats synced from the owner); its actions: `self.battle.action(memo, ActionKind.MEMOSPRITE, skill=rec, target=t)`; `self.memosprite()` returns the live one |
| HP consumption / healing / shields | `battle.lose_hp(unit, x, source)`, `battle.heal(unit, x, source)`, `battle.add_shield(unit, value, source, duration=2)` |
| Super Break | at `E.ATTACK_END`: `tough = battle.super_break_toughness(act, t)`; `battle.super_break(attacker, t, tough, mult)` |
| True DMG | `battle.true_damage(hit, ratio, target, credited, label)` |
| "Final DMG" (multiplicative) | stat `final_dmg` (each source a separate factor) or `hit.add(S.FINAL_DMG, x)` |
| Elation (Punchline / Aha) | class attrs `has_elation_skill = True`, `elation_skill_id = "<id>"`; implement `elation_skill(self, punchline)`; `self.gain_punchline(n)`; `self.elation_hit(target, scaling, punchline, action=act, tags=("elation_skill",), toughness=x)`; `self.banger()` = Punchline stored in Certified Banger; `self.battle.elation.extra_turn(fixed_p, self.char)`; events `AHA_INSTANT_START/END` in `hsrsim.elation` |
| Break-type damage | `battle.break_damage(attacker, target, element, mult=x)` ("x% of <element> Break DMG") |

Use `tools/kitinfo.py <name>` for the data and keep kits readable; comment every approximation
with `# approximation:` or `# not modelled:`.

### Manual control (the web UI)

The UI (`python -m hsrsim ui`) plays battles through `hsrsim.control` / `hsrsim.session`: at each of the
character's turns it shows `Kit.menu()` and executes the chosen item with `Kit.perform(item_id, target)`.

* The default menu is Basic ATK + Skill (`basic_item()` / `skill_item()`, labels, SP and target kind from the
  records). Override `menu()` / `perform()` when the kit has other actions or enhanced forms: return
  `MenuItem(id, label, target, enabled, ends_turn, sp, kind, note, label_cn, shape)`; `ends_turn=False` keeps the
  turn going (Qingque's Skill); disable what the game disables and say why in `note`.
* Summons whose turns the player controls in the game: `menu_for(unit)` / `perform_for(unit, item, target)`.
* `target` passed to `perform` / `use_ult(target)` is an enemy (main target) or an ally; `with_target(target, fn)`
  routes an ally to `main_dps()` through the `target` option, so ally-targeted abilities keep working.
* `ult_resource()` returns (current, required, label) for the Ultimate gauge when the Ultimate is not paid with
  Energy (Acheron's Slashed Dream, Phainon's Coreflame ...).
* `take_turn()` / `want_ult()` remain the automatic policy ("auto" in the UI and all CLI runs).

Ultimate timing (`Battle`, same for manual control and the automatic policies):

* A character's turn: turn start -> the actor's menu (Ultimates may be cast before choosing) -> the action ->
  window `"after_action"` (the action, its effects and Energy have resolved, the turn has not ended: Yao Guang's
  Skill fills her Energy, then her Ultimate, still in her turn) -> turn end -> queued inserts.
* Whatever an Ultimate queues (follow-ups, extra turns: Aha's from Yao Guang's Ultimate, the Aesthetic Archetype's
  from Pearl's) resolves **right after it**, interrupting the current turn, which then resumes
  (`Battle._cast_ult` / `_resolve_inserts`). Kits just queue as usual (`queue_action`, `queue_extra_turn`,
  `elation.extra_turn`).
* While those inserts resolve, `Battle.ults_locked` is true: no window opens and an Ultimate tried in such an extra
  turn is deferred (`Battle.deferred_ults`) and cast as soon as it ends.

## 7. Writing a light cone / relic set

```python
from hsrsim.equipment import LightCone, register_lc

@register_lc
class InTheNight(LightCone):
    lc_id = "23001"
    def setup(self):
        # always-on props (the "properties" list in the data) are ALREADY applied.
        # self.p(i) = parameter i at the equipped superimposition
        ...
```

Relic sets: see `hsrsim/gear/relics.py` (`self.p(pieces, i)`, `self.pieces` is 2 or 4).

A set or light cone with parameters but no registered class shows the build note "only static stats
modelled" in the editor; `tests/test_gear_smoke.py` runs every registered one. Character groups used by
scripts (`ByIsInCharacterIDGroup`, e.g. Trailblaze Companions = `"AstralExpress"`, Chrysos Heirs = `"Chrysos"`)
come from the data: `get_data().character_group(name)` — do not hard-code ID lists.

Monster traits: enemies built from endgame data carry `Enemy.template` (e.g. `"W3_TV_03"`) and their passive skill
parameters (`Enemy.passives["SkillP01"]`). Register behaviour with `@trait(template, passive_key)` in
`hsrsim/monsters.py`; numbers come from the passive's parameters.

## 8. Checking a kit against the game script

`python tools/kitinfo.py <id>` prints the skill texts and parameters; `python tools/ability_summary.py <id>`
prints the ability script (`--grep X`, `--full`, `--servant` for memosprites, `"<name>+"` for enhanced kits).
Conventions that recur in audits:

* **Order**: effects the script applies before `DamageByAttackProperty` (buffs, debuffs, stacks, resources) must be
  applied before the hit in the kit, so the same attack benefits.
* **Hit splits**: use `splits="data"` when the record has `splits` / `splits_adj` / `splits_aoe`; otherwise take the
  ratios from the script (`split=` values, `MaxLoopCount=` loops) into a named constant.
* **Energy**: `ModifySPNew AddValue=` scales with the receiver's ERR (`battle.gain_energy(c, x)`);
  `FixedAddValue=` does not (`fixed=True`).
* **Durations**: `LifeStepMoment=ModifierPhase1End` → `Tick.HOLDER_TURN_START` (see §3).
* **Gates**: `if ... NOT ...` conditions around listeners (e.g. "not transformed") must be reproduced.
* **Parameters**: `#1` in the description is index 0 of `self.p(...)` / `self.tp(...)` / `self.ep(...)`.

## 9. Checks

```bash
PYTHONPATH=. pytest -q
ruff check hsrsim tools tests
```
