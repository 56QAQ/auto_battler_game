"""Huohuo (藿藿) — Abundance / Wind. Team Energy + ATK ultimate, Divine Provision healing.

not modelled: E2 (revive; allies are immortal by default), E4 (healing bonus on low-HP allies) and dispels.
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
    def _provision_mod(self, turns: int) -> Modifier:
        stats = {S.SPD_PCT: self.ep(1, 0)} if self.e(1) else {}
        return Modifier(
            "Divine Provision",
            stats=stats,
            duration=turns,
            tick=Tick.SOURCE_TURN_START,
            scope=self.ally_scope if self.e(1) else None,
        )

    def _provision(self, turns: int) -> None:
        self.buff_self(self._provision_mod(turns))
        self.triggers_left = int(self.p("talent", 6))

    def _provision_active(self) -> bool:
        return self.char.has_mod("Divine Provision") and self.triggers_left > 0

    def _heal(self, ally: Character, base: float) -> None:
        """Any healing by Huohuo; E6 buffs every healed ally (MAvatar_Huohuo_Passive: OnBeforeDealHeal)."""
        self.battle.heal(ally, base, self.char)
        if self.e(6):
            self.buff(ally, Modifier("Woven Together", stats={S.DMG_PCT: self.ep(6, 0)}, duration=int(self.ep(6, 1))))

    def _talent_heal(self, ally: Character) -> None:
        self._heal(ally, self.p("talent", 2) * self.char.max_hp + self.p("talent", 4))
        if self.trace(3):  # A6: +Energy for every ally the Talent heals (ModifySPNew in each heal branch)
            self.battle.gain_energy(self.char, self.tp(3, 0))

    def _extra_heal_targets(self) -> list[Character]:
        """After healing the triggering ally: every ally at or below #6% HP (Passive_HealHP, SortByHP)."""
        return sorted((c for c in self.allies() if c.hp_ratio <= self.p("talent", 5)), key=lambda c: c.hp)

    def _heal_trigger(self, ally: Character) -> None:
        if not self._provision_active():
            return
        self.triggers_left -= 1
        self._talent_heal(ally)
        for c in self._extra_heal_targets():
            self._talent_heal(c)

    def _adjacent_allies(self, ally: Character) -> list[Character]:
        team = self.battle.team
        i = team.index(ally)
        return [c for j, c in enumerate(team) if abs(j - i) == 1 and c.alive]

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
        # Divine Provision ticks at the start of her turn (after that turn's heal trigger): recast once it expired
        prov = self.char.get_mod("Divine Provision")
        if self.can_skill() and (prov is None or self.triggers_left <= 1):
            self.skill(target)
        else:
            self.basic(target)

    # ----------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.BASIC, "basic", target) as act:
            act.hit(target, self.p("basic", 0), stat="hp", toughness=self.toughness("basic"), splits="data")

    def _skill_heals(self, ally: Character) -> None:
        """Skill: heal the target (#1% Max HP + #2) and the allies adjacent to it (#3% Max HP + #4)."""
        self._heal(ally, self.p("skill", 0) * self.char.max_hp + self.p("skill", 1))
        for c in self._adjacent_allies(ally):
            self._heal(c, self.p("skill", 2) * self.char.max_hp + self.p("skill", 3))

    def skill(self, target: Enemy | None) -> None:
        ally = self.main_dps()
        with self.action(ActionKind.SKILL, "skill", ally):
            self._skill_heals(ally)
            self._provision(int(self.p("talent", 0)) + (int(self.ep(1, 1)) if self.e(1) else 0))

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
        if self.trace(1):  # ModifySPNew AddValue: scaled by Energy Regeneration Rate
            self.battle.gain_energy(self.char, self.tp(1, 0))
            self._provision(int(self.tp(1, 1)))

    def _provision_turns(self) -> int:
        return int(self.p("talent", 0)) + (int(self.ep(1, 0)) if self.e(1) else 0)

    def _provision_mod(self, turns: int) -> Modifier:
        """Enhanced E1 params are [turns, Outgoing Healing, SPD]: all allies' SPD, Huohuo's Outgoing Healing."""
        if not self.e(1):
            return super()._provision_mod(turns)
        return Modifier(
            "Divine Provision",
            stats={S.SPD_PCT: self.ep(1, 2)},
            duration=turns,
            tick=Tick.SOURCE_TURN_START,
            scope=self.ally_scope,
            dyn=lambda m, k, e: self.ep(1, 1) if e is self.char else 0.0,
            dyn_keys={S.HEAL_PCT},
        )

    def _extra_heal_targets(self) -> list[Character]:
        """Enhanced Talent: also the ally with the lowest HP percentage, then every ally at or below #6% HP."""
        allies = self.allies()
        lowest = [min(allies, key=lambda c: c.hp_ratio)] if allies else []
        return lowest + super()._extra_heal_targets()

    def skill(self, target: Enemy | None) -> None:
        ally = self.main_dps()
        with self.action(ActionKind.SKILL, "skill", ally):
            self._skill_heals(ally)
            self._provision(self._provision_turns())

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult"):
            for c in self.teammates():
                self.battle.gain_energy(c, self.p("ult", 0) * c.max_energy, fixed=True)
                atk = self.p("ult", 1)
                if self.trace(2) and c.max_energy >= self.tp(2, 1):
                    atk += self.tp(2, 2)
                self.buff(c, Modifier("Spiritual Domination", stats={S.ATK_PCT: atk}, duration=int(self.p("ult", 2))))
            self._provision(self._provision_turns())
