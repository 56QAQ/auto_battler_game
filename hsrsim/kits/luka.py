"""Luka (卢卡) — Nihility / Physical. Fighting Will stacks -> Enhanced Basic ATK that detonates Bleed.

Options: ``rotation``: ``"auto"`` (Enhanced Basic ATK whenever it is available, else Skill when SP
allows, else Basic ATK) or ``"basic"`` (never uses the Skill).
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..battle import Action, Battle
from ..entities import Enemy
from ..enums import ActionKind, DmgTag, Element
from ..modifiers import DotModifier, Modifier, ModKind, Stacking
from . import register
from .base import Kit

ENHANCED_BASIC = "111108"
BLEED = "Bleed (Luka)"
# Talent / Enhanced Basic ATK literals: "up to 4 stacks", "Consumes 2 stacks", "deal 3 hits",
# "At the start of battle, Luka will possess 1 stack"; Technique: "gains 1 additional stack"
MAX_FIGHTING_WILL = 4
ENHANCED_BASIC_COST = 2
DIRECT_PUNCH_HITS = 3
START_FIGHTING_WILL = 1
TECHNIQUE_FIGHTING_WILL = 1


@register
class Luka(Kit):
    char_id = "1111"
    default_opts = {"rotation": "auto"}

    def setup(self) -> None:
        self.fighting_will = 0
        if self.e(1):
            self.on(E.ACTION_START, self._e1)

    def on_battle_start(self) -> None:
        self.gain_fighting_will(START_FIGHTING_WILL)

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        alive = self.enemies()
        if alive:
            t = self.battle.rng.choice(alive)
            with self.action(ActionKind.EXTRA, None, t, label="Luka Technique", energy=0, sp=0) as act:
                # not modelled: Toughness reduction of the overworld attack that starts the battle
                act.hit(t, p[0])
                if t.hp > 0:
                    self.bleed(t, p[1])
        self.gain_fighting_will(TECHNIQUE_FIGHTING_WILL)

    # ------------------------------------------------------ Fighting Will
    def gain_fighting_will(self, n: int) -> None:
        gained = min(MAX_FIGHTING_WILL, self.fighting_will + n) - self.fighting_will
        if gained <= 0:
            return
        self.fighting_will += gained
        if self.trace(2):
            self.battle.gain_energy(self.char, self.tp(2, 0) * gained)
        if self.e(4):
            for _ in range(gained):
                self.buff_self(
                    Modifier(
                        "Never Turning Back",
                        stats={S.ATK_PCT: self.ep(4, 0)},
                        stacking=Stacking.STACK,
                        max_stacks=int(self.ep(4, 1)),
                    )
                )

    # -------------------------------------------------------------- bleed
    def bleed(self, target: Enemy, chance: float) -> None:
        luka = self.char

        def dmg(mod: DotModifier, b: Battle, ratio: float) -> float:
            # p2 x enemy Max HP, capped at p3 x Luka's ATK (expressed as an ATK multiplier)
            cap = self.p("skill", 3)
            atk = luka.atk
            mult = min(cap, self.p("skill", 2) * target.max_hp / atk) if atk > 0 else cap
            return b.dot_damage(
                luka, target, Element.PHYSICAL, mult, label=BLEED, tags=(DmgTag.DOT, "bleed"), ratio=ratio
            )

        self.battle.try_debuff(
            DotModifier(BLEED, dot_type="bleed", damage_fn=dmg, duration=int(self.p("skill", 4))), target, luka, chance
        )

    def _e1(self, ev: E.Ev) -> None:
        act = ev.action
        if act.owner is self.char and isinstance(act.target, Enemy) and act.target.has_tag("bleed"):
            self.buff_self(
                Modifier("Fighting Endlessly", stats={S.DMG_PCT: self.ep(1, 0)}, duration=int(self.ep(1, 1)))
            )

    # ------------------------------------------------------------ policy
    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        if self.fighting_will >= ENHANCED_BASIC_COST:
            self.basic(target)
        elif self.opts.get("rotation", "auto") != "basic" and self.can_skill():
            self.skill(target)
        else:
            self.basic(target)

    # ----------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        if self.fighting_will >= ENHANCED_BASIC_COST:
            self.enhanced_basic(target)
            return
        self.simple_basic(target)
        self.gain_fighting_will(int(self.p("talent", 0)))

    def enhanced_basic(self, target: Enemy) -> Action:
        rec = self.sk(ENHANCED_BASIC)
        lv = [float(x) for x in rec["params"][self.level_of(rec) - 1]]
        self.fighting_will -= ENHANCED_BASIC_COST
        tough = self.toughness(ENHANCED_BASIC)
        total = DIRECT_PUNCH_HITS * lv[0] + lv[1]
        with self.action(ActionKind.BASIC, rec, target) as act:
            punches = 0
            for _ in range(DIRECT_PUNCH_HITS):
                # approximation: the Toughness reduction is spread over the hits in proportion to their DMG
                act.hit(target, lv[0], toughness=tough * lv[0] / total)
                punches += 1
                if self.trace(3) and self.battle.rng.random() < self.tp(3, 0):  # fixed chance, not recursive
                    act.hit(target, lv[0])  # approximation: the extra punch reduces no Toughness
                    punches += 1
            act.hit(target, lv[1], toughness=tough * lv[1] / total, label="Rising Uppercut")
            if target.hp > 0 and target.has_tag("bleed"):
                # approximation: every Bleed on the target (incl. Break Bleed) is triggered
                self.battle.detonate(target, self.p("talent", 1), kinds=("bleed",))
                if self.e(6):
                    for _ in range(punches):
                        if target.hp <= 0:
                            break
                        self.battle.detonate(target, self.ep(6, 0), kinds=("bleed",))
        return act

    def skill(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.SKILL, "skill", target) as act:
            if self.trace(1):
                for m in [m for m in target.buffs if m.dispellable][: int(self.tp(1, 0))]:
                    self.battle.remove_modifier(m)
            act.hit(target, self.p("skill", 0), toughness=self.toughness("skill"), splits="data")
            if target.hp > 0:
                self.bleed(target, self.p("skill", 1))
        n = int(self.p("talent", 0))
        if self.e(2) and target.is_weak_to(Element.PHYSICAL):
            n += int(self.ep(2, 0))
        self.gain_fighting_will(n)

    def ult(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.ULT, "ult", target) as act:
            self.gain_fighting_will(int(self.p("ult", 4)))
            self.battle.try_debuff(
                Modifier(
                    "Coup de Grâce",
                    stats={S.VULN: self.p("ult", 2)},
                    duration=int(self.p("ult", 3)),
                    kind=ModKind.DEBUFF,
                ),
                target,
                self.char,
                self.p("ult", 1),
            )
            act.hit(target, self.p("ult", 0), toughness=self.toughness("ult"), splits="data")
