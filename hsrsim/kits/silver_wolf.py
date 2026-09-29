"""Silver Wolf (银狼) — Nihility / Quantum. Weakness implant, RES/DEF shred, random Bugs.

Base kit only (the enhanced kit is not implemented yet).
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..entities import Enemy
from ..enums import ActionKind, Element
from ..modifiers import Modifier, ModKind
from . import register
from .base import Kit

BUGS = ("ATK", "DEF", "SPD")


@register
class SilverWolf(Kit):
    char_id = "1006"
    default_opts = {"implant": None}  # element to implant (default: first ally element the target lacks)

    def setup(self) -> None:
        if self.char.enhanced:
            raise NotImplementedError("Silver Wolf enhanced kit is not implemented yet")
        self.on(E.ATTACK_END, self._talent)
        if self.trace(1):
            self.on(E.BREAK, self._a2)
        if self.e(2):
            self.on(
                E.ENEMY_SPAWNED,
                lambda ev: self.battle.apply(
                    Modifier(
                        "Zombie Network", stats={S.EFFECT_RES: -self.ep(2, 0)}, kind=ModKind.DEBUFF, dispellable=False
                    ),
                    ev.enemy,
                    self.char,
                ),
            )
        if self.e(6):
            self.on(E.BEFORE_HIT, self._e6)

    def on_battle_start(self) -> None:
        if self.e(2):
            for e in self.enemies():
                self.battle.apply(
                    Modifier(
                        "Zombie Network", stats={S.EFFECT_RES: -self.ep(2, 0)}, kind=ModKind.DEBUFF, dispellable=False
                    ),
                    e,
                    self.char,
                )

    # ------------------------------------------------------------ bugs
    def bug(self, target: Enemy, chance: float) -> None:
        kind = self.battle.rng.choice(BUGS)
        value = {"ATK": self.p("talent", 0), "DEF": self.p("talent", 1), "SPD": self.p("talent", 2)}[kind]
        key = {"ATK": S.ATK_PCT, "DEF": S.DEF_REDUCTION, "SPD": S.SPD_PCT}[kind]
        stat = value if key == S.DEF_REDUCTION else -value
        dur = int(self.p("talent", 4)) + (int(self.tp(1, 0)) if self.trace(1) else 0)
        self.battle.try_debuff(
            Modifier(f"Bug ({kind})", stats={key: stat}, duration=dur, kind=ModKind.DEBUFF), target, self.char, chance
        )

    def _talent(self, ev: E.Ev) -> None:
        act = ev.attack
        if act.owner is not self.char:
            return
        for t in act.attacked:
            if t.alive:
                self.bug(t, self.p("talent", 3))

    def _a2(self, ev: E.Ev) -> None:
        if ev.target.alive:
            self.bug(ev.target, self.tp(1, 1))

    def _e6(self, ev: E.Ev) -> None:
        hit = ev.hit
        if hit.attacker is self.char:
            hit.add(S.DMG_PCT, min(self.ep(6, 1), self.ep(6, 0) * len(hit.target.debuffs)))

    # --------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        self.simple_basic(target)

    def _implant_element(self, target: Enemy) -> Element | None:
        pref = self.opts.get("implant")
        if pref:
            return Element(pref) if not isinstance(pref, Element) else pref
        for c in self.battle.team:
            if c is not self.char and not target.is_weak_to(c.element):
                return c.element
        return None if target.is_weak_to(self.char.element) else self.char.element

    def skill(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.SKILL, "skill", target) as act:
            el = self._implant_element(target)
            if el is not None:
                self.battle.remove_named(target, "Implanted Weakness")
                dur = int(self.p("skill", 2)) + (int(self.tp(2, 0)) if self.trace(2) else 0)
                already = target.is_weak_to(el)
                stats = {} if already else {f"{S.RES_REDUCTION}:{el.value}": self.p("skill", 3)}
                self.battle.try_debuff(
                    Modifier(
                        "Implanted Weakness", stats=stats, duration=dur, kind=ModKind.DEBUFF, tags={f"weak:{el.value}"}
                    ),
                    target,
                    self.char,
                    self.p("skill", 1),
                )
            res = self.p("skill", 5)
            if self.trace(3) and len(target.debuffs) >= self.tp(3, 0):
                res += self.tp(3, 1)
            self.battle.try_debuff(
                Modifier(
                    "Allow Changes?",
                    stats={S.RES_REDUCTION: res},
                    duration=int(self.p("skill", 6)),
                    kind=ModKind.DEBUFF,
                ),
                target,
                self.char,
                self.p("skill", 4),
            )
            act.hit(target, self.p("skill", 0), toughness=self.toughness("skill"))

    def ult(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.ULT, "ult", target) as act:
            self.battle.try_debuff(
                Modifier(
                    "User Banned",
                    stats={S.DEF_REDUCTION: self.p("ult", 2)},
                    duration=int(self.p("ult", 3)),
                    kind=ModKind.DEBUFF,
                ),
                target,
                self.char,
                self.p("ult", 1),
            )
            act.hit(target, self.p("ult", 0), toughness=self.toughness("ult"))
            n = min(int(self.ep(1, 1)), len(target.debuffs)) if target.alive else 0
            if self.e(1) and n:
                act.energy += self.ep(1, 0) * n
            if self.e(4):
                for _ in range(min(int(self.ep(4, 1)), len(target.debuffs))):
                    self.battle.additional_damage(self.char, target, self.ep(4, 0), label="E4 Bounce Attack")
