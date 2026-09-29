"""Sparkle (花火) — Harmony / Quantum. SP battery, CRIT DMG buff + 50% advance, DMG% per SP spent.

Base kit only (the enhanced kit is not implemented yet).
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..entities import Character, Enemy
from ..enums import ActionKind, Element
from ..modifiers import Modifier, Stacking, Tick
from . import register
from .base import Kit


@register
class Sparkle(Kit):
    char_id = "1306"
    ult_targets_ally = True
    default_opts = {"target": None}

    def setup(self) -> None:
        if self.char.enhanced:
            raise NotImplementedError("Sparkle enhanced kit is not implemented yet")
        extra = int(self.p("talent", 2)) + (1 if self.e(4) else 0)
        self.battle.max_sp += extra
        self.on(E.SP_CHANGED, self._on_sp)
        if self.trace(3):
            self.passive("Nocturne", {S.ATK_PCT: self.tp(3, 3)}, scope=self.ally_scope)
            n_q = sum(1 for c in self.battle.team if c.element == Element.QUANTUM)
            if n_q:
                self.passive(
                    "Nocturne (Quantum)",
                    {S.ATK_PCT: self.tp(3, min(n_q, 3) - 1)},
                    scope=lambda e: self.ally_scope(e) and getattr(e, "element", None) == Element.QUANTUM,
                )

    def technique(self) -> None:
        self.battle.gain_sp(int(self.sk("technique")["params"][0][0]), self.char)

    # ---------------------------------------------------------- talent
    def _on_sp(self, ev: E.Ev) -> None:
        if ev.delta >= 0:
            return
        for _ in range(-ev.delta):
            for c in self.allies():
                per = self.p("talent", 1)
                cipher = c.get_mod("Cipher")
                if cipher is not None:
                    per += self.p("ult", 2)
                stats = {S.DMG_PCT: per}
                if self.e(2):
                    stats[S.DEF_IGNORE] = self.ep(2, 0)
                self.buff(
                    c,
                    Modifier(
                        "Red Herring",
                        stats=stats,
                        duration=int(self.p("talent", 0)),
                        stacking=Stacking.STACK,
                        max_stacks=int(self.p("talent", 3)),
                    ),
                )

    # ---------------------------------------------------------- policy
    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        if self.opts.get("rotation", "skill") == "skill" and self.can_skill():
            self.skill(target)
        else:
            self.basic(target)

    # ---------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        extra = self.tp(1, 0) if self.trace(1) else 0.0
        with self.action(ActionKind.BASIC, "basic", target) as act:
            act.hit(target, self.p("basic", 0), toughness=self.toughness("basic"))
            act.energy += extra

    def _cd_buff_value(self) -> float:
        v = self.p("skill", 0) * self.char.stat(S.CRIT_DMG) + self.p("skill", 1)
        if self.e(6):
            v += self.ep(6, 0) * self.char.stat(S.CRIT_DMG)
        return v

    def _apply_cd_buff(self, ally: Character, value: float) -> None:
        if self.trace(2):  # extended until the start of the target's next turn
            mod = Modifier(
                "Dreamdiver",
                stats={S.CRIT_DMG: value},
                duration=int(self.p("skill", 2)) + 1,
                tick=Tick.HOLDER_TURN_START,
            )
            if ally is self.battle.current_turn:
                mod.duration = int(self.p("skill", 2))
        else:
            mod = Modifier("Dreamdiver", stats={S.CRIT_DMG: value}, duration=int(self.p("skill", 2)))
        self.buff(ally, mod)

    def skill(self, target: Enemy | None) -> None:
        ally = self.main_dps()
        with self.action(ActionKind.SKILL, "skill", ally):
            value = self._cd_buff_value()
            self._apply_cd_buff(ally, value)
            if self.e(6):
                for c in self.allies():
                    if c is not ally and c.has_mod("Cipher"):
                        self._apply_cd_buff(c, value)
        if ally is not self.char:
            self.battle.advance(ally, self.p("skill", 3))

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult"):
            self.battle.gain_sp(int(self.p("ult", 1)) + (1 if self.e(4) else 0), self.char)
            dur = int(self.p("ult", 3)) + (1 if self.e(1) else 0)
            for c in self.allies():
                stats = {S.ATK_PCT: self.ep(1, 0)} if self.e(1) else {}
                self.buff(c, Modifier("Cipher", stats=stats, duration=dur))
                herring = c.get_mod("Red Herring")
                if herring is not None:  # existing stacks get the Cipher bonus immediately
                    herring.stats[S.DMG_PCT] = self.p("talent", 1) + self.p("ult", 2)
            if self.e(6):
                holders = [c for c in self.allies() if c.has_mod("Dreamdiver")]
                if holders:
                    value = holders[0].get_mod("Dreamdiver").stats[S.CRIT_DMG]  # type: ignore[union-attr]
                    for c in self.allies():
                        if not c.has_mod("Dreamdiver"):
                            self._apply_cd_buff(c, value)
