"""Silver Wolf LV.999 (银狼LV.999) — Elation / Imaginary. "Hidden MMR" instead of Energy (CRIT from MMR),
"Godmode Player" state: bouncing Enhanced Basic ATK, Top Loot Boxes on allies' Skill Point use.

Policy: outside Godmode, Skill when Skill Points allow, else Basic ATK; in Godmode, Enhanced Basic ATK.
The Ultimate is cast as soon as Hidden MMR reaches the activation threshold.
"""

from __future__ import annotations

import math
from typing import Any

from .. import events as E
from .. import stats as S
from ..elation import PUNCHLINE_CHANGED
from ..entities import Enemy, Entity
from ..enums import ActionKind, DmgTag, Element, Side
from ..modifiers import Modifier, ModKind, Tick
from . import register
from .base import Kit

ENH_BASIC_ID = "150608"
BOX_IDS = {"sword": "150610", "egg": "150612", "bean": "150618"}
DEMO_ID = "150621"  # enhanced Elation Skill (Godmode)
MMR_E2_STEP_INDEX = 0  # E2 parameter: MMR gained per extra turn


@register
class SilverWolfLV999(Kit):
    char_id = "1506"
    has_elation_skill = True
    elation_skill_id = "150620"

    def setup(self) -> None:
        self.char.max_energy = 0.0  # Hidden MMR replaces Energy
        self.mmr = 0.0
        self.god = False
        self.basics_left = 0
        self.box_chance = 1.0
        self.e2_progress = 0.0
        self.in_enh_basic = False
        self.pending: dict[str, Any] | None = None  # enhanced Basic ATK interrupted by a wave clear
        self.extended_turn = -1
        self.tech = False
        self._mmr_off = False
        self.passive("Hidden MMR", {}, dyn=self._mmr_crit, dyn_keys={S.CRIT_RATE, S.CRIT_DMG})
        if self.trace(1):
            self.passive("False Ending Speedrun", {}, dyn=self._a2, dyn_keys={S.ELATION_DMG_PCT})
        if self.e(1):
            self.passive(
                "Aether Editing",
                {},
                scope=self.enemy_scope,
                dyn=lambda m, k, e: self.ep(1, 0) if self.god else 0.0,
                dyn_keys={S.VULN},
            )
        self.on(PUNCHLINE_CHANGED, self._on_punchline)
        self.on(E.SP_CHANGED, self._on_sp)
        self.on(E.BEFORE_HIT, self._enh_basic_bonus)
        self.on(E.WAVE_START, self._on_wave)
        if self.e(6):
            self.on(E.ENEMY_SPAWNED, lambda ev: self._absolute_weakness(ev.enemy))

    def on_battle_start(self) -> None:
        if self.e(6):
            for e in self.enemies():
                self._absolute_weakness(e)

    def technique(self) -> None:
        self.tech = True
        self.battle.queue_action(self._technique_box, self.char, "Funky Munch Bean", priority=5)

    def _technique_box(self) -> None:
        fixed = self.sk("technique")["params"][0][0]
        self.loot_box(None, fixed_p=fixed, kind="bean")

    def _on_wave(self, ev: E.Ev) -> None:
        if ev.wave > 0 and self.tech:
            self.battle.queue_action(self._technique_box, self.char, "Funky Munch Bean", priority=5)
        if ev.wave > 0 and self.pending is not None:
            self.battle.queue_extra_turn(self.char)

    def _absolute_weakness(self, e: Enemy) -> None:
        stats: dict[str, float] = {}
        for el in Element:
            base = e.base.get(f"{S.RES}:{el.value}", 0.0)
            stats[f"{S.RES}:{el.value}"] = -base if base > 0 else -self.ep(6, 0)
        self.battle.apply(
            Modifier(
                "Absolute Weakness",
                stats=stats,
                kind=ModKind.OTHER,
                tick=Tick.NONE,
                dispellable=False,
                tags={f"weak:{el.value}" for el in Element},
            ),
            e,
            self.char,
        )

    # ---------------------------------------------------------- Hidden MMR
    def mmr_cap(self) -> float:
        return self.p("talent", 0) + self.p("talent", 1)

    def gain_mmr(self, n: float) -> None:
        if n <= 0:
            return
        before = self.mmr
        self.mmr = min(self.mmr_cap(), self.mmr + n)
        if self.god and self.e(2):
            self.e2_progress += self.mmr - before
            self._e2_check()

    def _e2_check(self) -> None:
        step = self.ep(2, MMR_E2_STEP_INDEX)
        while self.e2_progress >= step:
            self.e2_progress -= step
            self.basics_left += 1
            self.battle.queue_extra_turn(self.char)

    def _on_punchline(self, ev: E.Ev) -> None:
        if ev.delta > 0:
            self.gain_mmr(float(ev.delta))

    def _mmr_crit(self, mod: Modifier, key: str, ent: Entity) -> float:
        if self._mmr_off or self.mmr <= 0:
            return 0.0
        per_cr = self.p("talent", 3)
        if key == S.CRIT_RATE:
            base = self.char.stat(S.CRIT_RATE)  # recursion guard: dynamic CRIT Rate bonuses excluded
            return min(self.mmr, math.ceil(max(0.0, 1.0 - base) / per_cr - 1e-9)) * per_cr
        self._mmr_off = True
        try:
            base = self.char.stat(S.CRIT_RATE)
        finally:
            self._mmr_off = False
        cr_points = min(self.mmr, math.ceil(max(0.0, 1.0 - base) / per_cr - 1e-9))
        return (self.mmr - cr_points) * self.p("talent", 5)

    def _a2(self, mod: Modifier, key: str, ent: Entity) -> float:
        spd = self.char.spd
        if spd < self.tp(1, 0):
            return 0.0
        excess = min(spd - self.tp(1, 0), self.tp(1, 4))
        return self.tp(1, 1) + int(excess / self.tp(1, 2)) * self.tp(1, 3)

    # ------------------------------------------------------------ Ultimate
    def ult_ready(self) -> bool:
        return not self.god and self.mmr >= self.p("talent", 0)

    def pay_ult_cost(self) -> None:
        pass  # Hidden MMR is not consumed (it is cleared when Godmode ends)

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult", energy=0):
            self.god = True
            self.box_chance = 1.0
            self.basics_left = int(self._enh_lv()[4])
            self.e2_progress = self.mmr
            if self.e(2):
                self._extend_buffs()
            if self.trace(3):
                self.gain_mmr(self.tp(3, 0))
            if self.e(2):
                self._e2_check()
        self.battle.advance(self.char, 1.0)

    def _exit_god(self) -> None:
        self.god = False
        self.basics_left = 0
        self.mmr = self.mmr * self.ep(1, 1) if self.e(1) else 0.0

    def _extend_buffs(self) -> None:
        for m in self.char.modifiers:
            if m.is_buff and m.duration is not None and not m.removed:
                m.duration += 1

    # ------------------------------------------------------ Top Loot Box
    def _on_sp(self, ev: E.Ev) -> None:
        if ev.delta >= 0 or not self.god or self.banger() <= 0:
            return
        who = ev.entity
        if who is None or getattr(who, "side", None) != Side.ALLY:
            return
        for _ in range(-ev.delta):
            if self.battle.rng.random() < self.box_chance:
                self.box_chance *= self.p("ult", 3)
                self.battle.queue_action(lambda: self.loot_box(None), self.char, "Top Loot Box", priority=6)

    def loot_box(self, act: Any, fixed_p: float | None = None, kind: str | None = None) -> None:
        kind = kind or self.battle.rng.choice(sorted(BOX_IDS))
        rec = self.sk(BOX_IDS[kind])
        if act is None:
            with self.action(ActionKind.EXTRA, rec, label=f"Top Loot Box: {rec['name']}", sp=0, energy=0) as a:
                self._box_hits(a, rec, kind, fixed_p)
        else:
            self._box_hits(act, rec, kind, fixed_p)

    def _box_hits(self, act: Any, rec: dict[str, Any], kind: str, fixed_p: float | None) -> None:
        enemies = self.enemies()
        if not enemies:
            return
        p = self.banger() if fixed_p is None else fixed_p
        total = 0.0
        for e in enemies:  # distributed evenly among all enemies
            h = self.elation_hit(
                e,
                self.p("ult", 2) / len(enemies),
                p,
                label=f"Top Loot Box: {rec['name']}",
                action=act,
                toughness=rec["toughness"][1],
            )
            total += h.damage
        if kind == "sword":
            alive = [e for e in self.enemies() if e.hp > 0] or self.enemies()
            if alive:
                t = max(alive, key=lambda e: e.hp)
                self.battle.true_damage(total, self.p("ult", 4), t, self.char, "Big Flipping Sword (True DMG)")
        elif kind == "egg":
            self.battle.gain_sp(int(self.p("ult", 6)), self.char)
        else:
            self.gain_punchline(int(self.p("ult", 5)))

    # ------------------------------------------------------------- actions
    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        if self.pending is not None:
            self.enhanced_basic(target)
        elif self.god:
            self.enhanced_basic(target)
        elif self.opts.get("rotation", "skill") == "skill" and self.can_skill():
            self.skill(target)
        else:
            self.basic(target)

    def _talent_proc(self, act: Any) -> None:
        p = self.banger()
        if p <= 0:
            return
        for e in list(act.attacked):
            if e.alive:
                self.elation_hit(e, self.p("talent", 2), p, label="I Carry, We Win", action=act)

    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.BASIC, "basic", target) as act:
            act.hit(target, self.p("basic", 0), toughness=self.toughness("basic"))
            self._talent_proc(act)

    def skill(self, target: Enemy | None) -> None:
        with self.action(ActionKind.SKILL, "skill", target) as act:
            act.aoe(self.p("skill", 0), toughness=self.toughness("skill", 1), main_target=target)
            self._talent_proc(act)
        self.gain_punchline(int(self.p("skill", 1)))

    def _enh_lv(self) -> list[float]:
        rec = self.sk(ENH_BASIC_ID)
        return list(rec["params"][self.level_of(rec) - 1])

    def _enh_basic_bonus(self, ev: E.Ev) -> None:
        h = ev.hit
        if not self.in_enh_basic or h.attacker is not self.char:
            return
        lv = self._enh_lv()
        stacks = min(int(lv[6]), int(self.mmr / lv[5]))
        if stacks:
            h.add(S.FINAL_DMG, lv[7] * stacks)
        if self.e(6) and DmgTag.ELATION in h.tags:
            h.add(S.MERRYMAKE_PCT, self.ep(6, 1))

    def enhanced_basic(self, target: Enemy) -> None:
        rec = self.sk(ENH_BASIC_ID)
        lv = self._enh_lv()
        total, boxes = int(lv[2]), int(lv[4])
        state = self.pending or {"bounces": total, "boxes": boxes, "final": True}
        if self.pending is not None and self.extended_turn != self.battle.turns:
            self.extended_turn = self.battle.turns
            self._extend_buffs()
        self.pending = None
        per = lv[0] / total
        tough = rec["toughness"][0] / total
        self.in_enh_basic = True
        interrupted = False
        try:
            with self.action(ActionKind.BASIC, rec, target, sp=0) as act:
                segment = math.ceil(total / boxes)
                while state["bounces"] > 0 or state["boxes"] > 0:
                    if not [e for e in self.enemies() if e.hp > 0]:
                        interrupted = True
                        break
                    n = min(segment, state["bounces"])
                    if n > 0:
                        self._bounces(act, n, per, tough)
                        state["bounces"] -= n
                    if state["boxes"] > 0 and [e for e in self.enemies() if e.hp > 0]:
                        state["boxes"] -= 1
                        self.loot_box(act)
                if not interrupted and [e for e in self.enemies() if e.hp > 0]:
                    enemies = self.enemies()
                    for e in enemies:
                        self._enh_hit(act, e, lv[3] / len(enemies), rec["toughness"][1], "αWolf Instant (Final Hit)")
                    state["final"] = False
                    self._talent_proc(act)
        finally:
            self.in_enh_basic = False
        if interrupted or state["final"]:
            self.pending = state  # resumes with an extra turn when new enemies appear
            return
        self.basics_left -= 1
        if self.basics_left <= 0:
            self._exit_god()

    def _bounces(self, act: Any, n: int, per: float, tough: float) -> None:
        # approximation: bounces of one segment are grouped per enemy (one hit per enemy with the summed ratio)
        counts: dict[int, int] = {}
        pool = [e for e in self.enemies() if e.hp > 0] or self.enemies()
        for _ in range(n):
            e = self.battle.rng.choice(pool)
            counts[id(e)] = counts.get(id(e), 0) + 1
        for e in pool:
            k = counts.get(id(e), 0)
            if k:
                self._enh_hit(act, e, per * k, tough * k, "αWolf Instant (bounce)")

    def _enh_hit(self, act: Any, e: Enemy, mult: float, tough: float, label: str) -> None:
        p = self.banger()
        if p > 0:  # while holding Certified Banger the Enhanced Basic ATK deals Elation DMG instead
            self.elation_hit(e, mult, p, label=label, action=act, toughness=tough)
        else:
            act.hit(e, mult, toughness=tough, label=label)

    # -------------------------------------------------------- elation skill
    def elation_skill(self, punchline: float) -> None:
        if self.god:
            rec = self.sk(DEMO_ID)
            lv = rec["params"][self.level_of(rec) - 1]
            p = punchline * (1.0 + self.ep(4, 0)) if self.e(4) else punchline
            with self.action(ActionKind.ELATION, rec, label=rec["name"]) as act:
                for _ in range(int(lv[1])):
                    pool = [e for e in self.enemies() if e.hp > 0] or self.enemies()
                    if not pool:
                        break
                    self.elation_hit(
                        self.battle.rng.choice(pool),
                        lv[0],
                        p,
                        label=rec["name"],
                        action=act,
                        tags=("elation_skill",),
                        toughness=rec["toughness"][0],
                    )
            self.box_chance = 1.0
        else:
            rec = self.sk(self.elation_skill_id)
            lv = rec["params"][self.level_of(rec) - 1]
            with self.action(ActionKind.ELATION, rec, label=rec["name"]):
                self.gain_mmr(lv[0])
        if self.trace(2):
            if punchline >= self.tp(2, 0):
                self.gain_mmr(self.tp(2, 2))
            if punchline >= self.tp(2, 1):
                self.gain_mmr(self.tp(2, 3))
