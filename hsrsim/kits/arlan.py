"""Arlan (阿兰) — Destruction / Lightning. HP-consuming Skill (no SP), DMG bonus from missing HP.

Options: ``rotation`` (``"skill"`` default: Skill every turn / ``"basic"``).
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..entities import Enemy, Entity
from ..enums import ActionKind, DmgTag
from ..modifiers import Modifier, ModKind
from . import register
from .base import Kit

# E1 / E6: "When HP percentage is lower than or equal to 50%" (literal in the text)
LOW_HP = 0.5
# A6 Repel: "nullify all DMG received"; the engine caps DMG reduction at 99%
REPEL_MITIGATION = 1.0


@register
class Arlan(Kit):
    char_id = "1008"

    def setup(self) -> None:
        self.passive("Pain and Anger", {}, dyn=self._talent, dyn_keys={S.DMG_PCT})
        self.on(E.BEFORE_HIT, self._before_hit)
        if self.trace(1):
            self.on(E.KILL, self._a2)
        if self.trace(2):
            # not modelled: enemies in the engine do not inflict DoTs (the stat is kept for completeness)
            self.passive("Endurance", {f"{S.DEBUFF_RES}:dot": self.tp(2, 0)})
        if self.e(4):
            self.on(E.HP_CHANGED, self._e4)

    def on_battle_start(self) -> None:
        if self.trace(3) and self.char.hp_ratio <= self.tp(3, 0):
            # approximation: "nullify all DMG except DoTs" = 100% DMG reduction (engine cap 99%)
            repel = self.buff_self(Modifier("Repel", stats={S.MITIGATION: REPEL_MITIGATION}, kind=ModKind.BUFF))
            self.on(
                E.ALLY_ATTACKED,
                lambda ev: self.char in ev.targets and self.battle.remove_modifier(repel),
            )
        if self.e(4):
            self.buff_self(Modifier("Turn the Tables", duration=int(self.ep(4, 1)), kind=ModKind.BUFF))

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        with self.action(ActionKind.EXTRA, None, label="Arlan Technique", energy=0, sp=0) as act:
            # not modelled: Toughness reduction of the overworld attack that starts the battle
            act.aoe(p[0])

    # ------------------------------------------------------------ passives
    def _talent(self, mod: Modifier, key: str, ent: Entity) -> float:
        return self.p("talent", 0) * max(0.0, 1.0 - self.char.hp_ratio)

    def _before_hit(self, ev: E.Ev) -> None:
        hit = ev.hit
        if hit.attacker is self.char and self.e(1) and DmgTag.SKILL in hit.tags and self.char.hp_ratio <= LOW_HP:
            hit.add(S.DMG_PCT, self.ep(1, 0))

    def _a2(self, ev: E.Ev) -> None:
        if ev.killer is self.char and self.char.hp_ratio <= self.tp(1, 0):
            self.battle.heal(self.char, self.tp(1, 1) * self.char.max_hp, self.char)

    def _e4(self, ev: E.Ev) -> None:
        mod = self.char.get_mod("Turn the Tables")
        if mod is None or ev.entity is not self.char or ev.delta >= 0 or not isinstance(ev.source, Enemy):
            return
        # approximation: allies do not die in the engine; a hit leaving Arlan at <= 1 HP counts as a killing blow
        if self.char.hp <= 1.0 + 1e-9:
            self.battle.remove_modifier(mod)
            self.battle.set_hp(self.char, self.ep(4, 0) * self.char.max_hp, self.char)

    def _cleanse(self) -> None:
        deb = next((m for m in self.char.debuffs if m.dispellable), None)
        if deb is not None:
            self.battle.remove_modifier(deb)

    # ----------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        self.simple_basic(target)

    def skill(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.SKILL, "skill", target) as act:
            cost = self.p("skill", 0) * self.char.max_hp
            self.battle.lose_hp(self.char, min(cost, max(0.0, self.char.hp - 1.0)), self.char)
            if self.e(2):
                self._cleanse()
            act.hit(target, self.p("skill", 1), toughness=self.toughness("skill"), splits="data")

    def ult(self, target: Enemy | None) -> None:
        assert target is not None
        low = self.e(6) and self.char.hp_ratio <= LOW_HP
        adj = self.p("ult", 0) if low else self.p("ult", 1)
        extra = {S.DMG_PCT: self.ep(6, 0)} if low else None
        with self.action(ActionKind.ULT, "ult", target) as act:
            if self.e(2):
                self._cleanse()
            act.blast(
                target,
                self.p("ult", 0),
                adj,
                toughness=(self.toughness("ult", 0), self.toughness("ult", 2)),
                splits="data",
                extra=extra,
            )
