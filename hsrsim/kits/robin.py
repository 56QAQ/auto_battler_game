"""Robin (知更鸟) — Harmony / Physical. Concerto: team-wide action advance, flat ATK, extra hits."""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..entities import Character, Enemy, Summon
from ..enums import ActionKind, DmgTag, Side
from ..modifiers import Modifier, Tick, hidden
from . import register
from .base import Kit


@register
class Robin(Kit):
    char_id = "1309"

    def setup(self) -> None:
        self.concerto: Modifier | None = None
        self.countdown: Summon | None = None
        self.e6_left = 0
        self.passive("Tonal Resonance", {S.CRIT_DMG: self.p("talent", 0)}, scope=self.ally_scope)
        self.on(E.ATTACK_END, self._on_ally_attack)

    def on_battle_start(self) -> None:
        if self.trace(1):
            self.battle.advance(self.char, self.tp(1, 0))

    def technique(self) -> None:
        self.battle.gain_energy(self.char, self.sk("technique")["params"][0][1], fixed=True)

    @property
    def in_concerto(self) -> bool:
        return self.concerto is not None

    def ult_ready(self) -> bool:
        return not self.in_concerto and super().ult_ready()

    # --------------------------------------------------------- actions
    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        skill_up = any(m.name == "Pinion's Aria" for m in self.char.modifiers)
        if self.opts.get("rotation", "skill") == "skill" and self.can_skill() and not skill_up:
            self.skill(target)
        else:
            self.basic(target)

    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        self.simple_basic(target)

    def skill(self, target: Enemy | None) -> None:
        with self.action(ActionKind.SKILL, "skill") as act:
            self.buff_self(
                Modifier(
                    "Pinion's Aria",
                    stats={S.DMG_PCT: self.p("skill", 0)},
                    duration=int(self.p("skill", 1)),
                    tick=Tick.SOURCE_TURN_START,
                    scope=self.ally_scope,
                )
            )
            if self.trace(3):
                act.energy += self.tp(3, 0)

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult"):
            atk = self.p("ult", 0) * self.char.atk + self.p("ult", 2)  # snapshot at cast
            stats = {S.ATK_FLAT: atk}
            if self.e(1):
                stats[S.RES_PEN] = self.ep(1, 0)
            if self.e(2):
                stats[S.SPD_PCT] = self.ep(2, 0)
            if self.e(4):
                stats[S.EFFECT_RES] = self.ep(4, 0)
            if self.trace(2):
                stats[f"{S.CRIT_DMG}:{DmgTag.FUA}"] = self.tp(2, 0)
            self.concerto = self.buff_self(hidden("Concerto", stats, scope=self.ally_scope))
            self.e6_left = int(self.ep(6, 0)) if self.e(6) else 0
            self.char.on_timeline = False
            self.countdown = self.battle.add_unit(
                Summon("Concerto Countdown", self.char, spd=self.p("ult", 1), on_turn=self._end_concerto)
            )
        for c in self.teammates():
            self.battle.advance(c, 1.0)
        for u in list(self.battle.units):
            if u.owner is not self.char and u.side == Side.ALLY and u.on_timeline and u.is_memosprite:
                self.battle.advance(u, 1.0)  # memosprites are teammates too

    def _end_concerto(self, unit: Summon, battle: object) -> None:
        if self.concerto is not None:
            self.battle.remove_modifier(self.concerto)
        self.concerto = None
        if self.countdown is not None:
            self.battle.remove_unit(self.countdown)
            self.countdown = None
        self.char.on_timeline = True
        # "exits the Concerto state and immediately takes action"
        self.battle.queue_action(lambda: self.battle.take_turn(self.char), self.char, "Robin after Concerto", priority=0)

    # ----------------------------------------------------------- talent
    def _on_ally_attack(self, ev: E.Ev) -> None:
        act = ev.attack
        if act.owner is None or act.owner.side != Side.ALLY or not act.attacked:
            return
        if not self.in_concerto:
            gain = self.p("talent", 1) + (self.ep(2, 1) if self.e(2) else 0)
            self.battle.gain_energy(self.char, gain)
            return
        target = act.attacked[0] if act.attacked[0].alive else self.battle.default_target()
        if target is None:
            return
        cd = self.p("ult", 5)
        if self.e6_left > 0:
            cd += self.ep(6, 1)
            self.e6_left -= 1
        self.battle.additional_damage(
            self.char,
            target,
            self.p("ult", 3),
            label="Concerto Additional DMG",
            crit_override=(self.p("ult", 4), cd),
            credited=self.char,
        )


def _is_char(e: object) -> bool:
    return isinstance(e, Character)
