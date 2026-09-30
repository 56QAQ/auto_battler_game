"""Firefly (流萤) — Destruction / Fire. Complete Combustion: SPD, Break Efficiency, Super Break.

Base kit and enhanced kit (``FireflyEnhanced``).
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..control import MenuItem
from ..entities import Enemy, Summon
from ..enums import ActionKind, Element
from ..modifiers import Modifier, ModKind, hidden
from . import register, register_enhanced
from .base import Kit

# Enhanced kit, Enhanced Skill (1131009): literal in the text and the ability script (HealPercentage=0.25,
# FireWeakType LifeTime=2 on the target and its adjacent targets); the record's parameters #3/#4 are 0
ENH_SKILL_HEAL = 0.25
ENH_SKILL_WEAKNESS_TURNS = 2


@register
class Firefly(Kit):
    char_id = "1310"

    def setup(self) -> None:
        self.combustion: Modifier | None = None
        self.countdown: Summon | None = None
        self.e2_ready_turn = -1
        if self.trace(3):
            self.passive("Module γ: Core Overload", {}, dyn=self._a6, dyn_keys={S.BREAK_EFFECT})
        self.on(E.ATTACK_END, self._super_break)

    # not modelled: the Talent's HP-based DMG reduction and its debuff dispel (defensive only)
    def on_battle_start(self) -> None:
        floor = self.p("talent", 1) * self.char.max_energy
        if self.char.energy < floor:
            self.char.energy = floor

    def technique(self) -> None:
        # "At the start of each wave" (MAvatar_Sam_00_Maze / _Maze_AddWeakness fire on every wave's OnEnterBattle)
        self._technique_wave()
        self.on(E.WAVE_START, lambda ev: self._technique_wave())

    def _technique_wave(self) -> None:
        p = self.sk("technique")["params"][0]
        with self.action(ActionKind.EXTRA, None, label="Firefly Technique", energy=0, sp=0) as act:
            for e in self.enemies():
                self.fire_weakness(e, int(p[2]))
            act.aoe(p[1], toughness=self.toughness("technique"))

    def _a6(self, mod: Modifier, key: str, ent: object) -> float:
        over = self.char.atk - self.tp(3, 0)
        return max(0.0, int(over / self.tp(3, 1))) * self.tp(3, 2) if over > 0 else 0.0

    @property
    def in_combustion(self) -> bool:
        return self.combustion is not None

    def fire_weakness(self, e: Enemy, turns: int) -> None:
        self.battle.apply(
            Modifier(
                "Fire Weakness (Firefly)",
                duration=turns,
                kind=ModKind.DEBUFF,
                tags={f"weak:{Element.FIRE.value}"},
                key="Firefly Fire Weakness",
            ),
            e,
            self.char,
        )

    # ------------------------------------------------------------ policy
    def ult_ready(self) -> bool:
        return not self.in_combustion and super().ult_ready()

    def can_skill(self) -> bool:
        if self.in_combustion and self.e(1):
            return True
        return self.battle.sp >= 1

    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        if self.opts.get("rotation", "skill") == "skill" and self.can_skill():
            self.skill(target)
        else:
            self.basic(target)

    def menu(self) -> list[MenuItem]:
        """Complete Combustion: Enhanced Basic ATK and Enhanced Skill (E1: the Enhanced Skill costs no SP)."""
        if not self.in_combustion:
            return super().menu()
        free = {"sp": 0} if self.e(1) else {}
        return [self.basic_item(self.sk(f"{self.prefix}08")), self.skill_item(self.sk(f"{self.prefix}09"), **free)]

    # ----------------------------------------------------------- helpers
    def _enhanced_mod(self) -> Modifier:
        stats = {S.BREAK_EFF: self.p("ult", 1), S.BREAK_DMG_PCT: self.p("ult", 0)}
        if self.e(6):
            stats[S.BREAK_EFF] += self.ep(6, 1)
        return self.buff_self(hidden("Combustion (attack)", stats))

    def _tough(self, e: Enemy, base: float) -> tuple[float, bool]:
        """Toughness of a hit; in Combustion non-Fire-weak enemies take 55% (A2)."""
        if self.in_combustion and self.trace(1) and not e.is_weak_to(Element.FIRE):
            return base * self.tp(1, 0), True
        return base, False

    def _e2(self, act: object, broke_or_killed: bool) -> None:
        if self.e(2) and broke_or_killed and self.e2_ready_turn < self.battle.turns:
            self.e2_ready_turn = self.battle.turns + 1
            self.battle.queue_extra_turn(self.char)

    # ----------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        if not self.in_combustion:
            self.simple_basic(target)
            return
        rec = self.sk(f"{self.prefix}08")  # 131008 / enhanced 1131008 (at the variant's own skill level)
        lv = rec["params"][self.level_of(rec) - 1]
        mod = self._enhanced_mod()
        with self.action(ActionKind.BASIC, rec, target) as act:
            self.battle.heal(self.char, lv[1] * self.char.max_hp, self.char)
            tough, ign = self._tough(target, rec["toughness"][0])
            hits = act.hit(target, lv[0], toughness=tough, ignore_weakness=ign, splits="data")
        self.battle.remove_modifier(mod)
        self._e2(act, any(h.broke for h in hits) or target.hp <= 0)

    def skill(self, target: Enemy | None) -> None:
        assert target is not None
        if not self.in_combustion:
            with self.action(ActionKind.SKILL, "skill", target) as act:
                self.battle.lose_hp(self.char, self.p("skill", 1) * self.char.max_hp, self.char)
                self.battle.gain_energy(self.char, self.p("skill", 2) * self.char.max_energy, fixed=True)
                act.hit(target, self.p("skill", 0), toughness=self.toughness("skill"), splits="data")
            self.battle.advance(self.char, self.p("skill", 3))
            return
        rec = self.sk(f"{self.prefix}09")  # 131009 / enhanced 1131009 (at the variant's own skill level)
        lv = rec["params"][self.level_of(rec) - 1]
        mod = self._enhanced_mod()
        sp = 0 if self.e(1) else None
        extra = {S.DEF_IGNORE: self.ep(1, 0)} if self.e(1) else None
        with self.action(ActionKind.SKILL, rec, target, sp=sp) as act:
            self._enhanced_skill_prelude(target, lv)
            be = min(self.char.stat(S.BREAK_EFFECT), lv[6])
            hits = []
            adjs = self.battle.adjacent(target)
            # Skill21_Phase02: 4 x (15% target, 15% each adjacent), then 40% target and 40% each adjacent
            main_r = rec.get("splits") or [1.0]
            adj_r = rec.get("splits_adj") or main_r
            for i in range(max(len(main_r), len(adj_r))):
                if i < len(main_r):
                    tough, ign = self._tough(target, rec["toughness"][0])
                    hits += act.hit(
                        target,
                        lv[4] * be + lv[0],
                        toughness=tough,
                        ignore_weakness=ign,
                        extra=extra,
                        splits=[main_r[i]],
                    )
                if i < len(adj_r):
                    for adj in adjs:
                        tough, ign = self._tough(adj, rec["toughness"][2])
                        hits += act.hit(
                            adj,
                            lv[5] * be + lv[1],
                            toughness=tough,
                            ignore_weakness=ign,
                            extra=extra,
                            primary=False,
                            splits=[adj_r[i]],
                        )
        self.battle.remove_modifier(mod)
        self._e2(act, any(h.broke for h in hits) or any(h.target.hp <= 0 for h in hits))

    def _enhanced_skill_prelude(self, target: Enemy, lv: list[float]) -> None:
        """Enhanced Skill: heal (#3 of Max HP), then Fire Weakness on the target for #4 turns."""
        self.battle.heal(self.char, lv[2] * self.char.max_hp, self.char)
        self.fire_weakness(target, int(lv[3]))

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult"):
            stats = {S.SPD_FLAT: self.p("ult", 2), S.EFFECT_RES: self.p("talent", 3)}
            if self.e(4):
                stats[S.EFFECT_RES] += self.ep(4, 0)
            if self.e(6):
                stats[f"{S.RES_PEN}:Fire"] = self.ep(6, 0)
            self.combustion = self.buff_self(hidden("Complete Combustion", stats))
            self.countdown = self.battle.add_unit(
                Summon("Combustion Countdown", self.char, spd=self.p("ult", 3), on_turn=self._end_combustion)
            )
        self.battle.advance(self.char, 1.0)

    def _end_combustion(self, unit: Summon, battle: object) -> None:
        if self.combustion is not None:
            self.battle.remove_modifier(self.combustion)
        self.combustion = None
        if self.countdown is not None:
            self.battle.remove_unit(self.countdown)
            self.countdown = None

    # ------------------------------------------------------- super break
    def _super_break(self, ev: E.Ev) -> None:
        act = ev.attack
        if act.owner is not self.char or not self.in_combustion or not self.trace(2):
            return
        be = self.char.stat(S.BREAK_EFFECT)
        if be >= self.tp(2, 1):
            mult = self.tp(2, 3)
        elif be >= self.tp(2, 0):
            mult = self.tp(2, 2)
        else:
            return
        for t in act.attacked:
            tough = self.battle.super_break_toughness(act, t)
            if tough > 0:
                self.battle.super_break(self.char, t, tough, mult, label="Super Break (Module β)")


@register_enhanced
class FireflyEnhanced(Firefly):
    """Enhanced Firefly: Combustion Break Effect, countdown delay on breaks, lower Super Break thresholds."""

    def ult(self, target: Enemy | None) -> None:
        super().ult(target)
        self.delays_left = int(self.tp(1, 2)) if self.trace(1) else 0
        if self.trace(1) and self.combustion is not None:
            self.combustion.stats[S.BREAK_EFFECT] = self.tp(1, 0)

    def _tough(self, e: Enemy, base: float) -> tuple[float, bool]:
        return base, False  # the enhanced A2 no longer lets SAM reduce non-Fire-weak Toughness

    def _e2(self, act: object, broke_or_killed: bool) -> None:
        if self.e(2) and broke_or_killed and self.e2_ready_turn != self.battle.turns:
            self.e2_ready_turn = self.battle.turns
            self.battle.queue_extra_turn(self.char)

    def setup(self) -> None:
        super().setup()
        self.delays_left = 0
        self.on(E.BREAK, self._a2_delay)

    def _enhanced_skill_prelude(self, target: Enemy, lv: list[float]) -> None:
        # the enhanced record's #3/#4 are 0: the heal and the Weakness duration are literal (module constants)
        self.battle.heal(self.char, ENH_SKILL_HEAL * self.char.max_hp, self.char)
        for e in [target, *self.battle.adjacent(target)]:
            self.fire_weakness(e, ENH_SKILL_WEAKNESS_TURNS)

    def _a2_delay(self, ev: E.Ev) -> None:
        """A2: every Weakness Break inflicted by the Enhanced Basic ATK / Skill delays the countdown by #2
        (OnTriggerBreak, up to #3 times per Complete Combustion)."""
        act = self.battle.current_action
        if (
            not self.trace(1)
            or self.delays_left <= 0
            or self.countdown is None
            or not self.in_combustion
            or act is None
            or act.owner is not self.char
            or act.kind not in (ActionKind.BASIC, ActionKind.SKILL)
        ):
            return
        self.delays_left -= 1
        self.battle.delay(self.countdown, self.tp(1, 1))
