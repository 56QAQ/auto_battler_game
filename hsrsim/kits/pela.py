"""Pela (佩拉) — Nihility / Ice. AoE DEF shred (Exposed), energy from debuffed targets."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .. import events as E
from .. import stats as S
from ..entities import Enemy
from ..enums import ActionKind, Element
from ..modifiers import Modifier, ModKind, Tick
from . import register
from .base import Kit

if TYPE_CHECKING:
    from ..battle import Battle


class _NextAttackBoost(Modifier):
    """A6 "Wipe Out": DMG% for Pela's next attack (MAvatar_Pela_SkillTree03_DamageAddedRatio, removed OnAfterAttack)."""

    def on_apply(self, battle: Battle) -> None:
        self.listen(E.ATTACK_END, self._consume)

    def _consume(self, ev: E.Ev) -> None:
        if ev.attack.owner is self.holder and self.battle is not None:
            self.battle.remove_modifier(self)


@register
class Pela(Kit):
    char_id = "1106"
    default_opts = {"rotation": "basic"}

    def setup(self) -> None:
        if self.trace(2):
            self.passive("The Secret Strategy", {S.EHR: self.tp(2, 0)}, scope=self.ally_scope)
        self.on(E.BEFORE_HIT, self._bash)
        self.on(E.ATTACK_END, self._after_attack)
        if self.e(1):
            self.on(E.KILL, lambda ev: self.battle.gain_energy(self.char, self.ep(1, 0)))

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        pool = self.enemies()
        if pool:  # "deals Ice DMG equal to #4% of her ATK to a random enemy"
            with self.action(ActionKind.EXTRA, "technique", label="Pela Technique", energy=0, sp=0) as act:
                act.hit(self.battle.rng.choice(pool), p[3], toughness=self.toughness("technique"))
        for e in self.enemies():
            self.battle.try_debuff(
                Modifier(
                    "Pela Technique",
                    stats={S.DEF_REDUCTION: p[1]},
                    duration=int(p[2]),
                    kind=ModKind.DEBUFF,
                    tick=Tick.HOLDER_TURN_START,  # MAvatar_Pela_00_MazeSkill_DefenceRatioDown: ModifierPhase1End
                ),
                e,
                self.char,
                p[0],
            )

    def _bash(self, ev: E.Ev) -> None:
        hit = ev.hit
        if self.trace(1) and hit.attacker is self.char and hit.target.debuffs:
            hit.add(S.DMG_PCT, self.tp(1, 0))

    def _after_attack(self, ev: E.Ev) -> None:
        act = ev.attack
        if act.owner is not self.char:
            return
        if any(t.debuffs for t in act.attacked):
            self.battle.gain_energy(self.char, self.p("talent", 0))
        if self.e(6):
            for t in act.attacked:
                if t.alive and t.debuffs:
                    self.battle.additional_damage(
                        self.char, t, self.ep(6, 0), element=Element.ICE, label="E6 Feeble Pursuit"
                    )

    # ---------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        self.simple_basic(target)

    def skill(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.SKILL, "skill", target) as act:
            dispelled = [m for m in target.buffs if m.dispellable][: int(self.p("skill", 1))]
            for m in dispelled:
                self.battle.remove_modifier(m)
            if self.e(4):  # applied before the DMG in the Skill's script, so this hit already benefits
                self.battle.try_debuff(
                    Modifier(
                        "Full Analysis",
                        stats={f"{S.RES_REDUCTION}:Ice": self.ep(4, 1)},
                        duration=int(self.ep(4, 2)),
                        kind=ModKind.DEBUFF,
                        tick=Tick.HOLDER_TURN_START,  # MAvatar_Pela_SkillRank04_IceResistanceDown: ModifierPhase1End
                    ),
                    target,
                    self.char,
                    self.ep(4, 0),
                )
            act.hit(target, self.p("skill", 0), toughness=self.toughness("skill"), splits="data")
        if dispelled:
            if self.trace(3):  # A6: the next attack deals more DMG (added after this Skill's DMG)
                self.buff_self(_NextAttackBoost("Wipe Out", stats={S.DMG_PCT: self.tp(3, 0)}))
            if self.e(2):
                self.buff_self(
                    Modifier("Adamant Charge", stats={S.SPD_PCT: self.ep(2, 0)}, duration=int(self.ep(2, 1)))
                )

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult", target) as act:
            for e in self.enemies():
                self.battle.try_debuff(
                    Modifier(
                        "Exposed",
                        stats={S.DEF_REDUCTION: self.p("ult", 1)},
                        duration=int(self.p("ult", 2)),
                        kind=ModKind.DEBUFF,
                    ),
                    e,
                    self.char,
                    self.p("ult", 0),
                )
            act.aoe(self.p("ult", 3), toughness=self.toughness("ult", 1), main_target=target, splits="data")
