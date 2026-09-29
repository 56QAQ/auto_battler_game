"""Huohuo (藿藿) — Abundance / Wind. Team Energy + ATK ultimate, Divine Provision healing.

Base kit only (the enhanced kit is not implemented yet). Healing is modelled only
as far as it drives Energy (A6) and buffs (E1/E6).
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..entities import Character, Enemy
from ..enums import ActionKind
from ..modifiers import Modifier, Tick
from . import register, register_enhanced
from .base import Kit


@register
class Huohuo(Kit):
    char_id = "1217"
    ult_targets_ally = True

    def setup(self) -> None:
        self.triggers_left = 0
        self.on(E.TURN_START, self._on_turn_start)
        self.on(E.ULT_USED, self._on_ult)

    def on_battle_start(self) -> None:
        if self.trace(1):
            self._provision(int(self.tp(1, 0)))

    # --------------------------------------------------------- provision
    def _provision(self, turns: int) -> None:
        stats = {S.SPD_PCT: self.ep(1, 0)} if self.e(1) else {}
        self.buff_self(
            Modifier(
                "Divine Provision",
                stats=stats,
                duration=turns,
                tick=Tick.SOURCE_TURN_START,
                scope=self.ally_scope if self.e(1) else None,
            )
        )
        self.triggers_left = int(self.p("talent", 6))

    def _provision_active(self) -> bool:
        return self.char.has_mod("Divine Provision") and self.triggers_left > 0

    def _heal_trigger(self, ally: Character) -> None:
        if not self._provision_active():
            return
        self.triggers_left -= 1
        self.battle.heal(ally, self.p("talent", 2) * self.char.max_hp + self.p("talent", 4), self.char)
        if self.trace(3):
            self.battle.gain_energy(self.char, self.tp(3, 0))
        if self.e(6):
            self.buff(ally, Modifier("Woven Together", stats={S.DMG_PCT: self.ep(6, 0)}, duration=int(self.ep(6, 1))))

    def _on_turn_start(self, ev: E.Ev) -> None:
        if isinstance(ev.entity, Character) and not ev.extra:
            self._heal_trigger(ev.entity)

    def _on_ult(self, ev: E.Ev) -> None:
        if isinstance(ev.entity, Character):
            self._heal_trigger(ev.entity)

    # ------------------------------------------------------------ policy
    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        prov = self.char.get_mod("Divine Provision")
        if self.can_skill() and (prov is None or (prov.duration or 0) <= 1 or self.triggers_left <= 1):
            self.skill(target)
        else:
            self.basic(target)

    # ----------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.BASIC, "basic", target) as act:
            act.hit(target, self.p("basic", 0), stat="hp", toughness=self.toughness("basic"))

    def skill(self, target: Enemy | None) -> None:
        ally = self.main_dps()
        with self.action(ActionKind.SKILL, "skill", ally):
            self.battle.heal(ally, self.p("skill", 0) * self.char.max_hp + self.p("skill", 1), self.char)
            self._provision(int(self.p("talent", 0)) + (int(self.ep(1, 1)) if self.e(1) else 0))
            if self.e(6):
                self.buff(
                    ally, Modifier("Woven Together", stats={S.DMG_PCT: self.ep(6, 0)}, duration=int(self.ep(6, 1)))
                )

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult"):
            for c in self.teammates():
                self.battle.gain_energy(c, self.p("ult", 0) * c.max_energy, fixed=True)
                self.buff(
                    c,
                    Modifier(
                        "Spiritual Domination", stats={S.ATK_PCT: self.p("ult", 1)}, duration=int(self.p("ult", 2))
                    ),
                )


@register_enhanced
class HuohuoEnhanced(Huohuo):
    """Enhanced Huohuo: Divine Provision from Skill and Ultimate, extra ATK for high-Energy allies (A4)."""

    def setup(self) -> None:
        self.triggers_left = 0
        self.on(E.TURN_START, self._on_turn_start)
        self.on(E.ULT_USED, self._on_ult)

    def on_battle_start(self) -> None:
        if self.trace(1):
            self.battle.gain_energy(self.char, self.tp(1, 0), fixed=True)
            self._provision(int(self.tp(1, 1)))

    def _provision_turns(self) -> int:
        return int(self.p("talent", 0)) + (int(self.ep(1, 0)) if self.e(1) else 0)

    def skill(self, target: Enemy | None) -> None:
        ally = self.main_dps()
        with self.action(ActionKind.SKILL, "skill", ally):
            self.battle.heal(ally, self.p("skill", 0) * self.char.max_hp + self.p("skill", 1), self.char)
            self._provision(self._provision_turns())
            if self.e(6):
                self.buff(
                    ally, Modifier("Woven Together", stats={S.DMG_PCT: self.ep(6, 0)}, duration=int(self.ep(6, 1)))
                )

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult"):
            for c in self.teammates():
                self.battle.gain_energy(c, self.p("ult", 0) * c.max_energy, fixed=True)
                atk = self.p("ult", 1)
                if self.trace(2) and c.max_energy >= self.tp(2, 1):
                    atk += self.tp(2, 2)
                self.buff(c, Modifier("Spiritual Domination", stats={S.ATK_PCT: atk}, duration=int(self.p("ult", 2))))
            self._provision(self._provision_turns())
