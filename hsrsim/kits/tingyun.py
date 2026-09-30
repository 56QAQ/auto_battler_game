"""Tingyun (停云) — Harmony / Lightning. Benediction (ATK + additional DMG), 50 flat Energy ultimate.

approximation: Benediction / Talent Additional DMG hit the first attacked enemy; E4 raises only Benediction's
multiplier (the Talent's is not confirmed by the data tools).
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..entities import Character, Enemy, Entity
from ..enums import ActionKind, DmgTag, Element
from ..modifiers import Modifier, Tick
from . import register
from .base import Kit

# text-only durations (script: LifeTime=1, LifeStepMoment=ModifierPhase1End -> until the holder's next turn start)
A2_SPD_TURNS = 1  # A2 "SPD increases by #1% for 1 turn after using Skill"
E1_SPD_TURNS = 1  # E1 "gains a 20% increase in SPD for 1 turn"


@register
class Tingyun(Kit):
    char_id = "1202"
    ult_targets_ally = True

    def setup(self) -> None:
        self.blessed: Character | None = None
        self.e2_turn = -1
        if self.trace(2):
            self.passive("Knell Subdual", {f"{S.DMG_PCT}:{DmgTag.BASIC}": self.tp(2, 0)})
        self.on(E.ATTACK_END, self._on_attack_end)
        self.on(E.TURN_START, self._turn_start)
        if self.e(1):
            self.on(E.ULT_USED, self._e1)
        if self.e(2):
            self.on(E.KILL, self._e2)

    def technique(self) -> None:
        self.battle.gain_energy(self.char, self.sk("technique")["params"][0][0], fixed=True)

    def _turn_start(self, ev: E.Ev) -> None:
        if ev.entity is self.char and self.trace(3):
            # MAvatar_Tingyun_Tree03: ModifySPNew AddValue (scaled by Energy Regeneration Rate), unlike the
            # Ultimate's FixedAddValue
            self.battle.gain_energy(self.char, self.tp(3, 0))

    # ----------------------------------------------------------- policy
    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        ally = self.main_dps()
        bene = ally.get_mod("Benediction")
        if self.can_skill() and (bene is None or (bene.duration or 0) <= 1):
            self.skill(target)
        else:
            self.basic(target)

    def want_ult(self) -> bool:
        ally = self.main_dps()
        return super().want_ult() and (ally.max_energy <= 0 or ally.energy < ally.max_energy)

    # ---------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        self.simple_basic(target)

    def _atk_bonus(self, ally: Entity) -> float:
        """ATK +#2% (of the ally's base ATK), capped at #4% of Tingyun's current ATK; the Skill snapshots both at
        cast (SetDynamicValueByProperty MDF_Target_CurrentAttack / MDF_Tingyun_Attack)."""
        return min(self.p("skill", 1) * ally.raw(S.BASE_ATK), self.p("skill", 3) * self.char.atk)

    def skill(self, target: Enemy | None) -> None:
        ally = self.main_dps()
        with self.action(ActionKind.SKILL, "skill", ally):
            for c in self.allies():  # only the most recent receiver keeps Benediction
                if c is not ally:
                    self.battle.remove_named(c, "Benediction")
            self.buff(
                ally,
                Modifier(
                    "Benediction",
                    stats={S.ATK_FLAT: self._atk_bonus(ally)},
                    duration=int(self.p("skill", 2)),
                    key="Benediction",
                ),
            )
            self.blessed = ally
            if self.trace(1):
                self.buff_self(
                    Modifier(
                        "Nourished Joviality",
                        stats={S.SPD_PCT: self.tp(1, 0)},
                        duration=A2_SPD_TURNS,
                        tick=Tick.HOLDER_TURN_START,
                    )
                )

    def ult(self, target: Enemy | None) -> None:
        ally = self.main_dps()
        with self.action(ActionKind.ULT, "ult", ally):
            energy = self.p("ult", 0) + (self.ep(6, 0) if self.e(6) else 0.0)
            self.battle.gain_energy(ally, energy, fixed=True)
            self.buff(
                ally,
                Modifier(
                    "Rejoicing Clouds",
                    stats={S.DMG_PCT: self.p("ult", 2)},
                    duration=int(self.p("ult", 1)),
                    skip_first_tick=False,
                ),  # LifeStepImmediately
            )

    # ----------------------------------------------------------- talent
    def _blessed(self) -> Character | None:
        b = self.blessed
        return b if b is not None and b.alive and b.has_mod("Benediction") else None

    def _on_attack_end(self, ev: E.Ev) -> None:
        act = ev.attack
        b = self._blessed()
        if b is None or not act.attacked:
            return
        target = next((t for t in act.attacked if t.alive), None)
        if target is None:
            return
        if act.owner is b:
            mult = self.p("skill", 0) + (self.ep(4, 0) if self.e(4) else 0.0)
            self.battle.additional_damage(b, target, mult, element=Element.LIGHTNING, label="Benediction (Tingyun)")
        if act.owner is self.char:
            self.battle.additional_damage(
                b, target, self.p("talent", 0), element=Element.LIGHTNING, label="Violet Sparknado (Tingyun)"
            )

    def _e1(self, ev: E.Ev) -> None:
        b = self._blessed()
        if b is not None and ev.entity is b:
            self.buff(
                b,
                Modifier(
                    "Windfall of Lucky Springs",
                    stats={S.SPD_PCT: self.ep(1, 0)},
                    duration=E1_SPD_TURNS,
                    tick=Tick.HOLDER_TURN_START,
                ),
            )

    def _e2(self, ev: E.Ev) -> None:
        b = self._blessed()
        if b is not None and ev.killer is b and self.e2_turn != self.battle.turns:
            self.e2_turn = self.battle.turns
            self.battle.gain_energy(b, self.ep(2, 0))
