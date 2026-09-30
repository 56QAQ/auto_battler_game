"""Rappa (乱破) — Erudition / Imaginary. Sealform: 3-hit Enhanced Basic ATK, Charge-scaled Break DMG, Super Break.

Options:
  rotation: "skill" (default) AoE Skill whenever SP allows outside Sealform, "basic" never uses the Skill
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .. import events as E
from .. import stats as S
from ..control import MenuItem
from ..entities import Enemy
from ..enums import ActionKind, Element, EnemyRank
from ..modifiers import Modifier, ModKind, hidden
from . import register
from .base import Kit

if TYPE_CHECKING:
    from ..battle import Action

HIT1, HIT2, HIT3, ENHANCED = "08", "10", "12", "18"  # skill ID suffixes of "Ningu: Demonbane Petalblade"
ATK_STEP = 100.0  # A6 "for every 100 excess ATK" (literal)
CHARGE_PER_BREAK = 1  # Talent "Each time the enemy target is Weakness Broken, Rappa gains 1 point of Charge" (literal)


@register
class Rappa(Kit):
    char_id = "1317"
    default_opts = {"rotation": "skill"}

    def setup(self) -> None:
        self.charge = 0
        self.charge_max = int(self.p("talent", 0)) + (int(self.ep(6, 1)) if self.e(6) else 0)
        self.ink = 0
        self.seal: list[Modifier] = []
        self.on(E.BREAK, self._on_break)
        if self.trace(2):
            self.on(E.AFTER_HIT, self._sea_echo)

    def on_battle_start(self) -> None:
        if self.e(6):
            self.add_charge(int(self.ep(6, 0)))

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        main = self.battle.default_target()
        if main is None:
            return
        b = self.battle
        # approximation: the Technique's struck enemy is the default target; its neighbours take the adjacent DMG
        b.reduce_toughness(main, self.char, p[4], Element.IMAGINARY)
        b.break_damage(self.char, main, Element.IMAGINARY, mult=p[1], label="Ninja Dash (technique)")
        for adj in b.adjacent(main):
            b.break_damage(self.char, adj, Element.IMAGINARY, mult=p[2], label="Ninja Dash (technique)")
        b.gain_energy(self.char, p[3])

    # ------------------------------------------------------------ Charge
    def add_charge(self, n: int) -> None:
        self.charge = max(0, min(self.charge_max, self.charge + n))

    def _on_break(self, ev: E.Ev) -> None:
        t = ev.target
        self.add_charge(CHARGE_PER_BREAK)
        if self.trace(1) and t.rank in (EnemyRank.ELITE, EnemyRank.BOSS):
            self.add_charge(int(self.tp(1, 1)))
            self.battle.gain_energy(self.char, self.tp(1, 0))
        if self.trace(3) and t.alive:
            over = self.char.atk - self.tp(3, 1)
            extra = min(self.tp(3, 3), int(over / ATK_STEP) * self.tp(3, 2)) if over > 0 else 0.0
            self.battle.apply(
                Modifier(
                    "Withered Leaf",
                    stats={f"{S.VULN}:break": self.tp(3, 0) + extra},  # snapshot of Rappa's ATK when applied
                    duration=int(self.tp(3, 4)),
                    kind=ModKind.DEBUFF,
                    key="Withered Leaf",
                ),
                t,
                self.char,
            )

    # ---------------------------------------------------------- Sealform
    @property
    def in_seal(self) -> bool:
        return bool(self.seal)

    def ult_ready(self) -> bool:
        return not self.in_seal and super().ult_ready()

    def can_skill(self) -> bool:
        return not self.in_seal and super().can_skill()

    def _exit_seal(self) -> None:
        for m in self.seal:
            self.battle.remove_modifier(m)
        self.seal = []
        self.ink = 0
        if self.e(1):
            self.battle.gain_energy(self.char, self.ep(1, 1))

    def _sea_echo(self, ev: E.Ev) -> None:
        h = ev.hit
        act = h.action
        if act is None or act.owner is not self.char or not act.data.get("petalblade") or not self.in_seal:
            return
        if h.was_broken and h.toughness_potential > 0:
            self.battle.super_break(
                self.char, h.target, h.toughness_potential, self.tp(2, 0), label="Super Break (Sea Echo)"
            )

    # ------------------------------------------------------------- policy
    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        if self.in_seal:
            self.basic(target)
        elif self.opts.get("rotation", "skill") == "skill" and self.can_skill():
            self.skill(target)
        else:
            self.basic(target)

    def menu(self) -> list[MenuItem]:
        """Sealform: the Enhanced Basic ATK replaces the Basic ATK; Skill (and Ultimate) cannot be used."""
        if self.in_seal:
            return [
                self.basic_item(self.sk(self.char.char_id + ENHANCED), note=f"【彩墨】{self.ink}"),
                self.skill_item(enabled=False, note="【结印】状态下无法施放战技"),
            ]
        return super().menu()

    # ------------------------------------------------------------ actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        if self.in_seal:
            self._petalblade(target)
        else:
            self.simple_basic(target)

    @staticmethod
    def _hit(act: Action, e: Enemy, mult: float, tough: float, ratio: float, primary: bool) -> None:
        """Enemies without Imaginary Weakness still take ``ratio`` of the Toughness Reduction."""
        weak = e.is_weak_to(Element.IMAGINARY)
        act.hit(e, mult, toughness=tough if weak else tough * ratio, ignore_weakness=not weak, primary=primary)

    def _petalblade(self, target: Enemy) -> None:
        cid = self.char.char_id
        recs = [self.sk(cid + HIT1), self.sk(cid + HIT2), self.sk(cid + HIT3)]
        main = self.sk(cid + ENHANCED)
        lv = main["params"][self.level_of(main) - 1]
        energy = sum(float(r["energy"]) for r in recs)
        b = self.battle
        with self.action(ActionKind.BASIC, main, target, energy=energy, sp=0) as act:
            act.data["petalblade"] = True
            for r in recs[:2]:
                t = target if target.alive and target.hp > 0 else b.default_target()
                if t is None:
                    break
                tough = float(r["toughness"][0]) * ((1.0 + self.ep(2, 0)) if self.e(2) else 1.0)
                self._hit(act, t, lv[0], tough, lv[3], True)
                for adj in b.adjacent(t):
                    self._hit(act, adj, lv[1], float(r["toughness"][2]), lv[3], False)
            for e in b.alive_enemies():
                self._hit(act, e, lv[2], float(recs[2]["toughness"][1]), lv[3], e is target)
            self._talent_break()
        if self.e(6):
            self.add_charge(int(self.ep(6, 0)))
        self.ink -= 1
        if self.ink <= 0:
            self._exit_seal()

    def _talent_break(self) -> None:
        """Talent: the 3rd hit additionally deals Break DMG to all enemies, consuming all Charge."""
        n = self.charge
        self.charge = 0
        mult = self.p("talent", 2) + self.p("talent", 4) * n
        # approximation: Weakness Break Efficiency also scales this Toughness reduction
        tough = (self.p("talent", 3) + self.p("talent", 5) * n) * (1.0 + self.char.stat(S.BREAK_EFF))
        for e in self.battle.alive_enemies():
            self.battle.reduce_toughness(e, self.char, tough, Element.IMAGINARY)
            if e.alive:
                self.battle.break_damage(
                    self.char, e, Element.IMAGINARY, mult=mult, label="Ninja Tech: Endurance Gauge"
                )

    def skill(self, target: Enemy | None) -> None:
        with self.action(ActionKind.SKILL, "skill", target) as act:
            act.aoe(self.p("skill", 0), toughness=self.toughness("skill", 1), main_target=target, splits="data")

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult"):
            stats = {S.BREAK_EFF: self.p("ult", 0), S.BREAK_EFFECT: self.p("ult", 1)}
            if self.e(1):
                stats[S.DEF_IGNORE] = self.ep(1, 0)
            self.seal = [self.buff_self(hidden("Sealform", stats))]
            if self.e(4):
                self.seal.append(
                    self.buff_self(hidden("Sealform (E4)", {S.SPD_PCT: self.ep(4, 0)}, scope=self.ally_scope))
                )
            self.ink = int(self.p("ult", 2))
        self.battle.queue_extra_turn(self.char)
