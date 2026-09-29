"""Ruan Mei (阮•梅) — Harmony / Ice. Break support: SPD, DMG%, Break Efficiency, RES PEN, Rebloom."""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..entities import Enemy, Entity
from ..enums import ActionKind, Element
from ..modifiers import Modifier, ModKind, Tick
from . import register
from .base import Kit


@register
class RuanMei(Kit):
    char_id = "1303"

    def setup(self) -> None:
        self.zone: Modifier | None = None
        self.passive("Somatotypical Helix", {S.SPD_PCT: self.p("talent", 0)}, scope=self.teammate_scope)
        if self.trace(1):
            self.passive("Inert Respiration", {S.BREAK_EFFECT: self.tp(1, 0)}, scope=self.ally_scope)
        if self.e(2):
            self.on(E.BEFORE_HIT, self._e2)
        self.on(E.BREAK, self._on_break)
        self.on(E.TURN_START, self._turn_start)
        self.on(E.AFTER_HIT, self._apply_rebloom)
        self.on(E.PRE_TURN, self._rebloom)
        self.on(E.RECOVERED, lambda ev: ev.enemy.data_flags.pop("rebloom_used", None))

    def technique(self) -> None:
        self._overtone()

    def _turn_start(self, ev: E.Ev) -> None:
        if ev.entity is self.char and self.trace(2):
            self.battle.gain_energy(self.char, self.tp(2, 0))

    # ----------------------------------------------------------- policy
    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        overtone = self.char.get_mod("Overtone")
        if self.can_skill() and (overtone is None or (overtone.duration or 0) <= 1):
            self.skill(target)
        else:
            self.basic(target)

    # ---------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        self.simple_basic(target)

    def _a6_bonus(self, mod: Modifier, key: str, ent: Entity) -> float:
        if not self.trace(3):
            return 0.0
        over = self.char.stat(S.BREAK_EFFECT) - self.tp(3, 0)
        if over <= 0:
            return 0.0
        return min(self.tp(3, 3), int(over / self.tp(3, 1) + 1e-9) * self.tp(3, 2))

    def _overtone(self) -> None:
        self.buff_self(
            Modifier(
                "Overtone",
                stats={S.DMG_PCT: self.p("skill", 0), S.BREAK_EFF: self.p("skill", 1)},
                duration=int(self.p("skill", 2)),
                tick=Tick.SOURCE_TURN_START,
                scope=self.ally_scope,
                dyn=self._a6_bonus,
                dyn_keys={S.DMG_PCT},
            )
        )

    def skill(self, target: Enemy | None) -> None:
        with self.action(ActionKind.SKILL, "skill"):
            self._overtone()

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult"):
            stats = {S.RES_PEN: self.p("ult", 0)}
            if self.e(1):
                stats[S.DEF_IGNORE] = self.ep(1, 0)
            dur = int(self.p("ult", 1)) + (int(self.ep(6, 0)) if self.e(6) else 0)
            self.zone = self.buff_self(
                Modifier("Ruan Mei Zone", stats=stats, duration=dur, tick=Tick.SOURCE_TURN_START,
                         scope=self.ally_scope)
            )

    # ----------------------------------------------------------- talent
    def _on_break(self, ev: E.Ev) -> None:
        credited = ev.credited
        if credited is None or credited.side != self.char.side:
            return
        mult = self.p("talent", 1) + (self.ep(6, 1) if self.e(6) else 0.0)
        self.battle.break_damage(self.char, ev.target, Element.ICE, mult=mult, label="Ruan Mei Talent Break")
        if self.e(4):
            self.buff_self(Modifier("Chatoyant Eclat", stats={S.BREAK_EFFECT: self.ep(4, 0)},
                                    duration=int(self.ep(4, 1))))

    def _e2(self, ev: E.Ev) -> None:
        hit = ev.hit
        if hit.attacker.side == self.char.side and hit.target.broken:
            hit.add(S.ATK_PCT, self.ep(2, 0))

    def _apply_rebloom(self, ev: E.Ev) -> None:
        hit = ev.hit
        if self.zone is None or self.zone.removed or hit.action is None:
            return
        if hit.attacker.side != self.char.side:
            return
        t = hit.target
        if t.alive and not t.has_mod("Thanatoplum Rebloom") and not t.data_flags.get("rebloom_used"):
            self.battle.apply(Modifier("Thanatoplum Rebloom", kind=ModKind.DEBUFF, dispellable=False,
                                       tick=Tick.NONE), t, self.char)

    def _rebloom(self, ev: E.Ev) -> None:
        e = ev.entity
        if not isinstance(e, Enemy) or not e.broken:
            return
        mod = e.get_mod("Thanatoplum Rebloom")
        if mod is None:
            return
        self.battle.remove_modifier(mod)
        e.data_flags["rebloom_used"] = True
        ev.data["cancel"] = True
        self.battle.log(f"Thanatoplum Rebloom triggers on {e.name}")
        self.battle.break_damage(self.char, e, Element.ICE, mult=self.p("ult", 4), label="Thanatoplum Rebloom")
        e.gauge = 0.0
        self.battle.delay(e, self.p("ult", 2) * self.char.stat(S.BREAK_EFFECT) + self.p("ult", 3))
