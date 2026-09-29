"""Gepard (杰帕德) — Preservation / Ice. Freeze on Skill, team Shield Ultimate, once-per-battle revive.

Options (``default_opts``):

* ``rotation``: ``"basic"`` (default, saves SP for the team) or ``"skill"`` (Skill whenever SP allows).
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..battle import Battle
from ..entities import Enemy
from ..enums import ActionKind, Element
from ..modifiers import DotModifier, Modifier, ModKind, hidden
from . import register
from .base import Kit

# approximation: with ``allies_immortal`` HP is floored at 1, so reaching it counts as a killing blow
DOWNED_HP = 1.0


class GepardFrozen(DotModifier):
    """Freeze from Gepard's Skill: the target skips its turn and takes Ice Additional DMG at its turn start."""

    def __init__(self, kit: Gepard, target: Enemy, duration: int) -> None:
        mult = kit.p("skill", 3)
        gepard = kit.char

        def dmg(mod: DotModifier, b: Battle, ratio: float) -> float:
            hit = b.additional_damage(gepard, target, mult * ratio, element=Element.ICE, label="Frozen (Gepard)")
            return hit.damage

        super().__init__(
            "Frozen (Gepard)",
            dot_type="freeze",
            damage_fn=dmg,
            duration=duration,
            is_dot=False,
            skip_turn=True,
            tags={"cc"},
        )
        self.kit = kit

    def on_remove(self, battle: Battle) -> None:
        holder = self.holder
        kit = self.kit
        if not kit.e(2) or holder is None or not holder.alive or holder.hp <= 0:
            return
        battle.apply(
            Modifier(
                "Lingering Cold",
                stats={S.SPD_PCT: -kit.ep(2, 0)},
                duration=int(kit.ep(2, 1)),
                kind=ModKind.DEBUFF,
            ),
            holder,
            kit.char,
        )


@register
class Gepard(Kit):
    char_id = "1104"
    default_opts = {"rotation": "basic"}

    def setup(self) -> None:
        self.talent_used = False
        if self.trace(1):
            # approximation: "higher chance to be attacked" = Aggro +param x 100%
            self.passive("Integrity", {S.AGGRO_PCT: self.tp(1, 0)})
        if self.e(4):
            self.passive("Faith Moves Mountains", {S.EFFECT_RES: self.ep(4, 0)}, scope=self.ally_scope)
        self.on(E.HP_CHANGED, self._talent)
        if self.trace(3):
            self.on(E.TURN_START, self._grit_turn)

    def on_battle_start(self) -> None:
        if self.trace(3):
            self._grit()

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        self._team_shield(p[0], p[2], int(p[1]), "Comradery")

    # ------------------------------------------------------------ traces
    def _grit(self) -> None:
        # A6: ATK + x% of current DEF, re-snapshotted at the start of each of Gepard's turns
        self.buff_self(hidden("Grit", {S.ATK_FLAT: self.tp(3, 0) * self.char.defense}))

    def _grit_turn(self, ev: E.Ev) -> None:
        if ev.entity is self.char:
            self._grit()

    # ----------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        self.simple_basic(target)

    def skill(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.SKILL, "skill", target) as act:
            act.hit(target, self.p("skill", 0), toughness=self.toughness("skill"))
            if target.alive and target.hp > 0:
                chance = self.p("skill", 1) + (self.ep(1, 0) if self.e(1) else 0.0)
                frozen = GepardFrozen(self, target, int(self.p("skill", 2)))
                self.battle.try_debuff(frozen, target, self.char, chance, debuff_type="freeze")

    def _team_shield(self, def_ratio: float, flat: float, turns: int, name: str) -> None:
        value = def_ratio * self.char.defense + flat
        for c in self.allies():
            self.battle.add_shield(c, value, self.char, duration=turns, name=name)

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult"):
            self._team_shield(self.p("ult", 0), self.p("ult", 2), int(self.p("ult", 1)), "Enduring Bulwark")

    # ------------------------------------------------------------ talent
    def _talent(self, ev: E.Ev) -> None:
        c = self.char
        if ev.entity is not c or self.talent_used or ev.delta >= 0 or not isinstance(ev.source, Enemy):
            return
        if c.hp > DOWNED_HP + 1e-9:
            return
        self.talent_used = True
        restore = self.p("talent", 0) * c.max_hp
        if self.e(6):
            restore += self.ep(6, 0) * c.max_hp
        self.battle.heal(c, max(0.0, restore - c.hp), c)
        if self.trace(2):
            self.battle.gain_energy(c, c.max_energy, fixed=True)
        if self.e(6):
            self.battle.advance(c, 1.0)
