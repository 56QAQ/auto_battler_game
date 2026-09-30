"""Misha (米沙) — Destruction / Ice. Ultimate hit count grows with the team's Skill Point consumption; Freeze.

Options (``default_opts``):
* ``rotation``: ``"skill"`` (default: Skill whenever SP allows) or ``"basic"``.

Also hosts :class:`CharFreeze`, the Frozen state applied by character abilities (used by Jingliu's Technique).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .. import events as E
from .. import formulas as F
from .. import stats as S
from ..entities import Enemy
from ..enums import ActionKind, Element
from ..modifiers import DotModifier, Modifier, ModKind, hidden
from . import register
from .base import Kit

if TYPE_CHECKING:
    from ..battle import Battle
    from ..entities import Character

FREEZE_TURNS = 1  # Ultimate text: "chance to Freeze the target, lasting for 1 turn"
BOUNCE_TOUGHNESS_RATIO = 0.5  # ability config: the first hit uses StanceRatio 1, every later hit 0.5


class CharFreeze(DotModifier):
    """Frozen from a character ability (``MCommon_CTRL_Frozen``): the holder skips its turn and takes
    Ice Additional DMG (``mult`` x the source's ``stat``, ATK by default) at the start of it."""

    def __init__(
        self, source: Character, mult: float, duration: int = 1, label: str = "Frozen", stat: str = "atk"
    ) -> None:
        def dmg(mod: DotModifier, b: Battle, ratio: float) -> float:
            holder = mod.holder
            if not isinstance(holder, Enemy) or not holder.alive:
                return 0.0
            hit = b.additional_damage(
                source, holder, mult * ratio, stat=stat, element=Element.ICE, label=label, credited=source
            )
            return hit.damage

        super().__init__(
            "Frozen",
            dot_type="freeze",
            damage_fn=dmg,
            duration=duration,
            is_dot=False,
            skip_turn=True,
            tags={"cc"},
            key=f"Frozen (ability)#{source.uid}",
        )

    def on_remove(self, battle: Battle) -> None:
        # approximation: the thawed enemy's next action is advanced like after the Ice Weakness Break Freeze
        # (the common Frozen modifier sets the skipped turn's delay cost; its value is not in the data)
        if self.holder is not None and self.holder.alive:
            battle.advance(self.holder, F.FREEZE_THAW_ADVANCE)


@register
class Misha(Kit):
    char_id = "1312"
    default_opts = {"rotation": "skill"}

    def setup(self) -> None:
        self.hits = int(self.p("ult", 0))
        self.e6_sp_pending = False
        self.e6_buff: Modifier | None = None
        self.on(E.SP_CHANGED, self._on_sp)
        if self.trace(3):
            self.on(E.BEFORE_HIT, self._a6)
        if self.e(6):
            self.on(E.TURN_END, self._end_e6)

    def technique(self) -> None:
        # not modelled: Dream Prison in the overworld; only the extra Ultimate hits are applied
        self.add_hits(int(self.sk("technique")["params"][0][1]))

    # ------------------------------------------------------------- talent
    def add_hits(self, n: int) -> None:
        self.hits = min(int(self.p("ult", 4)), self.hits + n)

    def _on_sp(self, ev: E.Ev) -> None:
        if ev.delta >= 0:
            return
        n = -int(ev.delta)
        self.add_hits(n * int(self.p("talent", 1)))
        self.battle.gain_energy(self.char, n * self.p("talent", 0))

    def _a6(self, ev: E.Ev) -> None:
        hit = ev.hit
        if hit.attacker is self.char and hit.target.has_tag("freeze"):
            hit.add(S.CRIT_DMG, self.tp(3, 0))

    def _end_e6(self, ev: E.Ev) -> None:
        # E6 "increases own DMG by 30%, lasting until the end of the turn"
        if self.e6_buff is not None:
            self.battle.remove_modifier(self.e6_buff)
            self.e6_buff = None

    def freeze(self, target: Enemy, chance: float) -> None:
        self.battle.try_debuff(
            CharFreeze(self.char, self.p("ult", 3), FREEZE_TURNS), target, self.char, chance, debuff_type="freeze"
        )

    # ------------------------------------------------------------ actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        self.simple_basic(target)

    def skill(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.SKILL, "skill", target) as act:
            self.add_hits(int(self.p("skill", 2)))
            act.blast(
                target,
                self.p("skill", 0),
                self.p("skill", 1),
                toughness=(self.toughness("skill", 0), self.toughness("skill", 2)),
            )
        if self.e6_sp_pending:
            self.e6_sp_pending = False
            self.battle.gain_sp(int(self.ep(6, 0)), self.char)

    def _bounce_target(self) -> Enemy | None:
        pool = [e for e in self.enemies() if e.hp > 0] or self.enemies()
        return self.battle.rng.choice(pool) if pool else None

    def ult(self, target: Enemy | None) -> None:
        if target is None:
            return
        n = self.hits
        if self.e(1):
            n += min(int(self.ep(1, 1)), int(self.ep(1, 0)) * len(self.enemies()))
        self.hits = int(self.p("ult", 0))
        if self.e(6):
            self.e6_buff = self.buff_self(hidden("Estrangement of Dream", {S.DMG_PCT: self.ep(6, 1)}))
            self.e6_sp_pending = True
        mult = self.p("ult", 1) + (self.ep(4, 0) if self.e(4) else 0.0)
        tough = self.toughness("ult")
        with self.action(ActionKind.ULT, "ult", target) as act:
            ehr = self.buff_self(hidden("Interlock", {S.EHR: self.tp(2, 0)})) if self.trace(2) else None
            for i in range(n):
                t = target if i == 0 and target.alive else self._bounce_target()
                if t is None:
                    break
                chance = self.p("ult", 2) + (self.tp(1, 0) if self.trace(1) and i == 0 else 0.0)
                if self.e(2):
                    self.battle.try_debuff(
                        Modifier(
                            "Yearning of Youth",
                            stats={S.DEF_REDUCTION: self.ep(2, 0)},
                            duration=int(self.ep(2, 1)),
                            kind=ModKind.DEBUFF,
                        ),
                        t,
                        self.char,
                        self.ep(2, 2),
                    )
                self.freeze(t, chance)  # "just before each hit lands"
                act.hit(t, mult, toughness=tough * (1.0 if i == 0 else BOUNCE_TOUGHNESS_RATIO))
            if ehr is not None:
                self.battle.remove_modifier(ehr)
