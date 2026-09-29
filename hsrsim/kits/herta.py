"""Herta (黑塔) — Erudition / Ice. AoE follow-up whenever an ally's attack drops an enemy to <= 50% HP.

Options: ``rotation`` (``"skill"`` default / ``"basic"``).
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..entities import Enemy
from ..enums import ActionKind, DmgTag, Element, Side
from ..modifiers import Modifier, Stacking
from . import register
from .base import Kit


@register
class Herta(Kit):
    char_id = "1013"

    def setup(self) -> None:
        self._key = f"herta_above#{self.char.uid}"
        self.on(E.ATTACK_START, self._attack_start)
        self.on(E.ATTACK_END, self._attack_end)
        self.on(E.BEFORE_HIT, self._before_hit)
        if self.trace(2):
            self.passive("Puppet", {f"{S.DEBUFF_RES}:cc": self.tp(2, 0)})  # enemies rarely CC in the engine

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        self.buff_self(Modifier("It Can Still Be Optimized", stats={S.ATK_PCT: p[0]}, duration=int(p[1])))

    # ------------------------------------------------------------ talent
    def _attack_start(self, ev: E.Ev) -> None:
        act = ev.attack
        if act.owner is None or act.owner.side != Side.ALLY:
            return
        thr = self.p("talent", 0)
        act.data[self._key] = {e.uid for e in self.enemies() if e.hp_ratio > thr}

    def _attack_end(self, ev: E.Ev) -> None:
        act = ev.attack
        above = act.data.get(self._key)
        if not above:
            return
        thr = self.p("talent", 0)
        # approximation: enemies defeated by the attack do not trigger the Talent
        n = sum(1 for e in self.enemies() if e.uid in above and e.hp > 0 and e.hp_ratio <= thr)
        if n:
            self.battle.queue_action(lambda: self._fua(n), self.char, "Herta follow-up")

    def _fua(self, n: int) -> None:
        """One Follow-Up ATK with one AoE hit per enemy that crossed the threshold."""
        if not self.enemies():
            return
        if self.e(2):
            for _ in range(n):
                self.buff_self(
                    Modifier(
                        "Keep the Ball Rolling",
                        stats={S.CRIT_RATE: self.ep(2, 0)},
                        stacking=Stacking.STACK,
                        max_stacks=int(self.ep(2, 1)),
                    )
                )
        extra = {S.DMG_PCT: self.ep(4, 0)} if self.e(4) else None
        energy = float(self.sk("talent")["energy"]) * n
        with self.action(ActionKind.FUA, "talent", self.battle.default_target(), energy=energy) as act:
            for _ in range(n):
                if not any(e.hp > 0 for e in self.enemies()):
                    break
                act.aoe(self.p("talent", 1), toughness=self.toughness("talent", 1), main_target=act.target, extra=extra)

    def _before_hit(self, ev: E.Ev) -> None:
        hit = ev.hit
        if hit.attacker is not self.char:
            return
        if DmgTag.SKILL in hit.tags and hit.target.hp_ratio >= self.p("skill", 1):
            hit.add(S.DMG_PCT, self.p("skill", 2) + (self.tp(1, 0) if self.trace(1) else 0.0))
        if self.trace(3) and DmgTag.ULT in hit.tags and hit.target.has_tag("freeze"):
            hit.add(S.DMG_PCT, self.tp(3, 0))

    # ----------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.BASIC, "basic", target) as act:
            act.hit(target, self.p("basic", 0), toughness=self.toughness("basic"), splits="data")
            if self.e(1) and target.hp > 0 and target.hp_ratio <= self.ep(1, 0):
                self.battle.additional_damage(
                    self.char, target, self.ep(1, 1), element=Element.ICE, label="Kick You When You're Down"
                )

    def skill(self, target: Enemy | None) -> None:
        with self.action(ActionKind.SKILL, "skill", target) as act:
            act.aoe(self.p("skill", 0), toughness=self.toughness("skill", 1), main_target=target, splits="data")

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult", target) as act:
            act.aoe(self.p("ult", 0), toughness=self.toughness("ult", 1), main_target=target, splits="data")
        if self.e(6):
            self.buff_self(
                Modifier("No One Can Betray Me", stats={S.ATK_PCT: self.ep(6, 0)}, duration=int(self.ep(6, 1)))
            )
