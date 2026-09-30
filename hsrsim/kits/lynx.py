"""Lynx (玲可) — Abundance / Quantum. "Survival Response" (Max HP, aggro) on one ally, heals over time.

Healing is modelled with ``battle.heal`` (outgoing healing bonus and E1 applied).

Options (``default_opts``):

* ``rotation``: ``"auto"`` (default: Skill when the target's Survival Response is missing or about to
  expire, else Basic ATK), ``"skill"`` (Skill whenever SP allows) or ``"basic"``.
* ``target``: ally name that receives the Skill (default: the first other team slot).
"""

from __future__ import annotations

from collections.abc import Callable

from .. import events as E
from .. import stats as S
from ..battle import Battle
from ..entities import Character, Enemy, Entity
from ..enums import ActionKind, Path
from ..modifiers import Modifier, ModKind, Tick
from . import register
from .base import Kit

SURVIVAL = "Survival Response"
TANK_PATHS = (Path.DESTRUCTION, Path.PRESERVATION)


class HealOverTime(Modifier):
    """Continuous healing: ``heal_fn(holder)`` at the start of each of the holder's turns."""

    def __init__(self, name: str, heal_fn: Callable[[Entity], None], duration: int) -> None:
        super().__init__(name, duration=duration, tick=Tick.HOLDER_TURN_START, kind=ModKind.BUFF)
        self.heal_fn = heal_fn

    def on_apply(self, battle: Battle) -> None:
        self.listen(E.TURN_START, self._on_turn_start)

    def _on_turn_start(self, ev: E.Ev) -> None:
        if ev.entity is self.holder and not self.removed:
            self.heal_fn(ev.entity)


@register
class Lynx(Kit):
    char_id = "1110"
    ult_targets_ally = True
    default_opts = {"rotation": "auto", "target": None}

    def setup(self) -> None:
        if self.trace(2):
            self.passive("Exploration Techniques", {f"{S.DEBUFF_RES}:cc": self.tp(2, 0)})
        if self.trace(1):
            self.on(E.ALLY_ATTACKED, self._a2)

    def technique(self) -> None:
        turns = int(self.sk("technique")["params"][0][0])
        for c in self.allies():
            self._hot(c, turns)

    # ------------------------------------------------------------ healing
    def _heal(self, ally: Entity, amount: float) -> None:
        bonus = self.ep(1, 1) if self.e(1) and ally.hp_ratio <= self.ep(1, 0) else 0.0
        self.battle.heal(ally, amount, self.char, bonus=bonus)

    def _hot(self, ally: Entity, turns: int | None = None) -> None:
        """Talent: continuous healing (bigger on targets with Survival Response)."""
        if turns is None:
            turns = int(self.p("talent", 0)) + (int(self.tp(3, 0)) if self.trace(3) else 0)

        def tick(holder: Entity) -> None:
            hp = self.char.max_hp
            amount = self.p("talent", 1) * hp + self.p("talent", 2)
            if holder.has_mod(SURVIVAL):
                amount += self.p("talent", 3) * hp + self.p("talent", 4)
            self._heal(holder, amount)

        self.buff(ally, HealOverTime("Outdoor Survival Experience", tick, turns))

    # ------------------------------------------------------------- policy
    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        policy = self.opts.get("rotation", "auto")
        sr = self.main_dps().get_mod(SURVIVAL)
        expiring = sr is None or (sr.duration or 0) <= 1
        if self.can_skill() and (policy == "skill" or (policy == "auto" and expiring)):
            self.skill(target)
        else:
            self.basic(target)

    # ------------------------------------------------------------ actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.BASIC, "basic", target) as act:
            act.hit(target, self.p("basic", 0), stat="hp", toughness=self.toughness("basic"), splits="data")

    def _survival_response(self, ally: Character) -> None:
        hp = self.char.max_hp  # approximation: Lynx's Max HP is snapshotted at cast
        ratio = self.p("skill", 0) + (self.ep(6, 0) if self.e(6) else 0.0)
        stats = {S.HP_FLAT: ratio * hp + self.p("skill", 1)}
        if ally.path in TANK_PATHS:
            # approximation: "chance of being attacked greatly increases" = Aggro +param x 100%
            stats[S.AGGRO_PCT] = self.p("skill", 5)
        if self.e(6):
            stats[S.EFFECT_RES] = self.ep(6, 1)
        self.buff(ally, Modifier(SURVIVAL, stats=stats, duration=int(self.p("skill", 2))))
        if self.e(4):
            self.buff(
                ally,
                Modifier("Dusk of Warm Campfire", stats={S.ATK_FLAT: self.ep(4, 0) * hp}, duration=int(self.ep(4, 1))),
            )
        # not modelled: E2 (a target with Survival Response resists 1 debuff) - enemies do not inflict debuffs

    def skill(self, target: Enemy | None) -> None:
        ally = self.main_dps()
        with self.action(ActionKind.SKILL, "skill", ally):
            self._survival_response(ally)
            self._heal(ally, self.p("skill", 3) * self.char.max_hp + self.p("skill", 4))
            self._hot(ally)

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult"):
            for c in self.allies():
                for m in [m for m in c.debuffs if m.dispellable][: int(self.p("ult", 0))]:
                    self.battle.remove_modifier(m)
                self._heal(c, self.p("ult", 1) * self.char.max_hp + self.p("ult", 2))
                self._hot(c)

    # ------------------------------------------------------------ traces
    def _a2(self, ev: E.Ev) -> None:
        for t in ev.targets:
            if t.has_mod(SURVIVAL):
                self.battle.gain_energy(self.char, self.tp(1, 0))
