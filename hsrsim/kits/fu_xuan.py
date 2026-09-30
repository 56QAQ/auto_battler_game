"""Fu Xuan (符玄) — Preservation / Quantum. Matrix of Prescience (team CRIT Rate / Max HP, DMG distribution)
and Misfortune Avoidance (team DMG reduction).

Options (``default_opts``):
* ``rotation``: ``"skill"`` (default: re-cast the Skill when Matrix of Prescience is missing or in its last turn)
  or ``"basic"``.
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..control import ALLIES, MenuItem
from ..entities import Character, Enemy, Entity
from ..enums import ActionKind
from ..modifiers import Modifier
from . import register
from .base import Kit

HP_RESTORE_START = 1  # Talent text "This effect has 1 trigger count by default"
HP_RESTORE_MAX = 2  # "... and can hold up to a maximum of 2 trigger counts"
ULT_RESTORE_COUNT = 1  # Ultimate text "obtains 1 trigger count for the HP Restore effect"
MATRIX = "Matrix of Prescience"


@register
class FuXuan(Kit):
    char_id = "1208"
    default_opts = {"rotation": "skill"}

    def setup(self) -> None:
        self.triggers = HP_RESTORE_START
        self.matrix: Modifier | None = None
        self.e6_tally = 0.0
        self.e6_active = False
        # not modelled: Fu Xuan being knocked down (allies are immortal by default), so the aura is permanent
        self.passive("Misfortune Avoidance", {S.MITIGATION: self.p("talent", 0)}, scope=self.ally_scope)
        self.on(E.HP_CHANGED, self._on_hp)
        if self.e(4):
            self.on(E.ALLY_ATTACKED, self._e4)
        # not modelled: A6 (Crowd Control resistance) and E2 (knock-down prevention): enemy CC and ally deaths
        # are not simulated by default

    def technique(self) -> None:
        self._activate_matrix(int(self.sk("technique")["params"][0][1]))

    # ------------------------------------------------------------ matrix
    def matrix_active(self) -> bool:
        return self.matrix is not None and not self.matrix.removed

    def _knowledge_hp(self, mod: Modifier, key: str, ent: Entity) -> float:
        return self.p("skill", 3) * self.char.max_hp

    def _activate_matrix(self, turns: int) -> None:
        stats = {S.CRIT_RATE: self.p("skill", 4)}
        if self.e(1):
            stats[S.CRIT_DMG] = self.ep(1, 0)
        # Knowledge (Max HP + CRIT Rate for all allies) modelled as an aura held by Fu Xuan
        self.matrix = self.buff_self(
            Modifier(
                MATRIX,
                stats=stats,
                duration=turns,
                scope=self.ally_scope,
                dyn=self._knowledge_hp,
                dyn_keys={S.HP_FLAT},
                key=MATRIX,
            )
        )
        self.e6_active = True  # E6: the tally starts once Matrix of Prescience is activated

    # ------------------------------------------------------------ talent
    def _on_hp(self, ev: E.Ev) -> None:
        ent = ev.entity
        if ev.delta >= 0 or not isinstance(ent, Character):
            return
        lost = -ev.delta
        if (
            ent is not self.char
            and isinstance(ev.source, Enemy)
            and self.matrix_active()
            and ent.side == self.char.side
        ):
            # approximation: 65% of the HP an enemy attack took from a teammate is given back and taken from
            # Fu Xuan instead (the game splits the DMG before mitigation/shields; here it uses the final loss)
            share = lost * self.p("skill", 0)
            ent.hp += share
            lost -= share
            self.battle.lose_hp(self.char, share, ev.source)
        if self.e(6) and self.e6_active:
            self.e6_tally += lost
        if ent is self.char:
            self._try_restore()

    def _try_restore(self) -> None:
        """Talent HP Restore: at or below the HP threshold, spend 1 trigger count to heal missing HP."""
        if self.triggers > 0 and self.char.hp_ratio <= self.p("talent", 1):
            self.triggers -= 1
            self.battle.heal(self.char, self.p("talent", 2) * (self.char.max_hp - self.char.hp), self.char)

    def _e4(self, ev: E.Ev) -> None:
        if not self.matrix_active():
            return
        for t in ev.targets:
            if isinstance(t, Character) and t is not self.char:
                self.battle.gain_energy(self.char, self.ep(4, 0))

    # ------------------------------------------------------------ policy
    def menu(self) -> list[MenuItem]:
        """The Skill (Matrix of Prescience) covers the whole team."""
        return [self.basic_item(), self.skill_item(target=ALLIES)]

    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        m = self.matrix
        refresh = m is None or m.removed or (m.duration or 0) <= 1
        if self.opts.get("rotation", "skill") == "skill" and self.can_skill() and refresh:
            self.skill(target)
        else:
            self.basic(target)

    # ----------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.BASIC, "basic", target) as act:
            act.hit(target, self.p("basic", 0), stat="hp", toughness=self.toughness("basic"))

    def skill(self, target: Enemy | None) -> None:
        with self.action(ActionKind.SKILL, "skill", self.char) as act:
            if self.trace(1) and self.matrix_active():
                act.energy += self.tp(1, 0)
            self._activate_matrix(int(self.p("skill", 2)))

    def ult(self, target: Enemy | None) -> None:
        flat = 0.0
        if self.e(6):
            flat = self.ep(6, 0) * min(self.e6_tally, self.ep(6, 1) * self.char.max_hp)
        with self.action(ActionKind.ULT, "ult", target) as act:
            act.aoe(self.p("ult", 0), stat="hp", flat=flat, toughness=self.toughness("ult", 1), main_target=target)
            self.triggers = min(HP_RESTORE_MAX, self.triggers + ULT_RESTORE_COUNT)
            if self.trace(2):
                for c in self.teammates():
                    self.battle.heal(c, self.tp(2, 0) * self.char.max_hp + self.tp(2, 1), self.char)
        if self.e(6):
            self.e6_tally = 0.0
        # Avatar_FuXuan_00_Skill03_Phase02: after the Ultimate grants its trigger count, HP Restore fires at once
        # (TurnInsertAbility Avatar_FuXuan_00_Passive_Ability) if her HP is already at or below the threshold
        self._try_restore()
