"""Mortenax Blade (千冶•刃) — Nihility / Fire (Max HP scaling). "Balefire Bind" (DEF shred + vulnerability),
"Infinite Fury" Zone with its own countdown (SPD 70): free AoE Skill, new Ultimate, Charge-based follow-up Skills.

Policy: outside Infinite Fury, Basic ATK (the Skill is locked); in Infinite Fury, Skill while HP > 1, else the
Enhanced Basic ATK. Ultimates are cast when ready.
"""

from __future__ import annotations

from typing import Any

from .. import events as E
from .. import stats as S
from ..control import MenuItem
from ..entities import Character, Enemy, Summon
from ..enums import ActionKind, DmgTag, Path, Side
from ..modifiers import Modifier, ModKind, hidden
from . import register
from .base import Kit

ENH_BASIC_ID = "150708"
FUA_SKILL_ID = "150709"  # the Talent's extra Skill use (a Follow-Up ATK)
TENAX_ID = "150714"  # Ultimate while in Infinite Fury
BALEFIRE = "Balefire Bind"


@register
class MortenaxBlade(Kit):
    char_id = "1507"

    def setup(self) -> None:
        self.fury: Modifier | None = None
        self.countdown: Summon | None = None
        self.charge = 0
        self.base_max = self.char.max_energy
        self.overflow = 0.0
        self.e6_ready = True
        self.nihility_mates = sum(1 for c in self.battle.team if c is not self.char and c.path == Path.NIHILITY)
        if self.trace(1):
            self.on(E.ENERGY_OVERFLOW, self._energy_overflow)
        self.on(E.ATTACK_END, self._talent)
        self.on(E.ALLY_ATTACKED, self._a4)
        self.on(E.HP_CHANGED, self._on_hp)
        if self.trace(3):
            bonus = self.tp(3, 0) + (self.ep(4, 0) if self.e(4) else 0.0)
            self.passive(
                "Heart, Refined ad Infinitum",
                {},
                scope=self.ally_scope,
                dyn=lambda m, k, e: bonus if self.in_fury else 0.0,
                dyn_keys={S.DMG_PCT},
            )
            if self.nihility_mates:
                self.passive(
                    "Heart, Refined ad Infinitum (Ultimate)",
                    {},
                    scope=self.ally_scope,
                    dyn=lambda m, k, e: self.tp(3, 1) if self.in_fury else 0.0,
                    dyn_keys={f"{S.DMG_PCT}:{DmgTag.ULT}"},
                )
            else:
                self.passive(
                    "Heart, Refined ad Infinitum (self)",
                    {},
                    dyn=lambda m, k, e: self.tp(3, 2) if self.in_fury else 0.0,
                    dyn_keys={S.DMG_PCT},
                )
        if self.e(1):
            self.passive(
                "Ere My Death, I Stood Unmade",
                {},
                scope=self.enemy_scope,
                dyn=lambda m, k, e: self.ep(1, 0) if self.in_fury else 0.0,
                dyn_keys={S.RES_REDUCTION},
            )
        if self.e(2):
            self.passive("Ash Was My Heart", {f"{S.DMG_PCT}:{DmgTag.FUA}": self.ep(2, 0)}, scope=self.ally_scope)
            self.on(E.BEFORE_HIT, self._e2_ult_is_fua)
        if self.e(6):
            self.on(E.TURN_END, lambda ev: setattr(self, "e6_ready", True))

    def on_battle_start(self) -> None:
        self._energy_floor()

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        # not modelled: Taunt on all enemies
        self.buff_self(Modifier("Blade's Reach Spares None", stats={S.MITIGATION: p[0]}, duration=int(p[1])))

    # ------------------------------------------------------------ Energy
    def _energy_overflow(self, ev: E.Ev) -> None:
        if ev.entity is self.char:
            self._on_overflow(ev.amount)

    def _on_overflow(self, amount: float) -> None:
        self.overflow = min(self.tp(1, 1), self.overflow + amount)

    def _energy_floor(self) -> None:
        # not modelled: "When Energy is regenerated to its maximum, dispels all debuffs from this unit"
        if self.trace(1):
            floor = self.tp(1, 0) * self.char.max_energy
            if self.char.energy < floor:
                self.char.energy = floor

    # --------------------------------------------------------- the Zone
    @property
    def in_fury(self) -> bool:
        return self.fury is not None and not self.fury.removed

    def _enter_fury(self) -> None:
        stats = {S.CRIT_RATE: self.p("ult", 1), S.CRIT_DMG: self.p("ult", 2)}
        if self.trace(2):
            stats.update({S.MITIGATION: self.tp(2, 1), S.HEAL_TAKEN: self.tp(2, 2), S.AGGRO_PCT: self.tp(2, 0)})
        self.fury = self.buff_self(hidden("Infinite Fury", stats))
        if self.countdown is None:
            self.countdown = self.battle.add_unit(
                Summon(
                    "Infinite Fury Countdown", self.char, spd=self.p("ult", 4), on_turn=lambda u, b: self._end_fury()
                )
            )

    def _end_fury(self) -> None:
        if self.fury is not None:
            self.battle.remove_modifier(self.fury)
        self.fury = None
        if self.countdown is not None:
            self.battle.remove_unit(self.countdown)
            self.countdown = None
        self._energy_floor()

    def balefire(self, e: Enemy) -> None:
        if not e.alive:
            return
        self.battle.try_debuff(
            Modifier(
                BALEFIRE,
                stats={S.DEF_REDUCTION: self.p("ult", 6), S.VULN: self.p("ult", 3)},
                duration=int(self.p("ult", 7)),
                kind=ModKind.DEBUFF,
                key="Balefire Bind",
            ),
            e,
            self.char,
            1.0,
        )

    def consume_hp(self, ratio: float) -> None:
        """Consume ``ratio`` of Max HP; "if the current HP is insufficient, it is reduced to 1"."""
        self.battle.lose_hp(self.char, min(ratio * self.char.max_hp, max(0.0, self.char.hp - 1.0)), self.char)

    # ----------------------------------------------------------- Charge
    def charge_cap(self) -> int:
        return int(self.ep(2, 1)) if self.e(2) else int(self.p("talent", 0))

    def add_charge(self, n: int = 1) -> None:
        if not self.in_fury:
            return
        self.charge = min(self.charge_cap(), self.charge + n)
        if self.charge >= self.charge_cap() and self.char.hp > 1:
            self.charge -= self.charge_cap()
            self.battle.gain_energy(self.char, self.p("talent", 1))
            self.battle.queue_action(self._extra_skill, self.char, "All Karma Comes Due")

    def _talent(self, ev: E.Ev) -> None:
        act = ev.attack
        owner = act.owner
        if not self.in_fury or getattr(owner, "side", None) != Side.ALLY or not act.attacked:
            return
        for e in act.attacked:
            self.balefire(e)
        self.add_charge(1)

    def _a4(self, ev: E.Ev) -> None:
        if not self.trace(2) or not self.in_fury or self.char not in ev.targets:
            return
        if isinstance(ev.attacker, Enemy):
            self.balefire(ev.attacker)
        self.add_charge(1)

    def _on_hp(self, ev: E.Ev) -> None:
        if ev.entity is not self.char or ev.delta >= 0 or not self.in_fury:
            return
        if self.e(6) and self.e6_ready:
            self.e6_ready = False
            self.add_charge(1)
        # Allies cannot be knocked down in the simulator: an enemy hit that leaves 1 HP counts as the killing blow.
        if isinstance(ev.source, Enemy) and self.char.hp <= 1.0:
            self._end_fury()
            self.battle.heal(self.char, self.p("ult", 5) * self.char.max_hp, self.char)

    def _e2_ult_is_fua(self, ev: E.Ev) -> None:
        h = ev.hit
        if DmgTag.ULT in h.tags and isinstance(h.credited, Character) and DmgTag.FUA not in h.tags:
            h.tags = h.tags | {DmgTag.FUA}

    # ----------------------------------------------------------- policy
    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        if self.in_fury and self.char.hp > 1 and self.opts.get("rotation", "skill") == "skill":
            self.skill(target)
        else:
            self.basic(target)

    def menu(self) -> list[MenuItem]:
        """The Skill (no SP, costs HP) is only usable in Infinite Fury with more than 1 HP; the Basic ATK is enhanced
        in Infinite Fury."""
        if not self.in_fury:
            return [self.basic_item(), self.skill_item(enabled=False, note="未处于【无量忿怒】状态")]
        ok = self.char.hp > 1
        skill = self.skill_item(enabled=ok, note="" if ok else "当前生命值不足")
        return [self.basic_item(self.sk(ENH_BASIC_ID)), skill]

    # ---------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        rec = self.sk(ENH_BASIC_ID) if self.in_fury else self.sk("basic")
        lv = rec["params"][self.level_of(rec) - 1]
        with self.action(ActionKind.BASIC, rec, target) as act:
            act.hit(target, lv[0], stat="hp", toughness=rec["toughness"][0])
            # not modelled: Taunt

    def _rain(self, rec: dict[str, Any], kind: ActionKind, tags: tuple[str, ...], target: Enemy | None) -> None:
        sk = self.sk("skill")
        lv = sk["params"][self.level_of(sk) - 1]
        self.consume_hp(lv[3])
        with self.action(kind, rec, target, tags=tags) as act:
            act.aoe(lv[0], stat="hp", toughness=self.toughness("skill", 1), main_target=target)
            act.bounce(None, int(lv[1]), lv[2], stat="hp", toughness=self.toughness("skill", 0))

    def skill(self, target: Enemy | None) -> None:
        if not self.in_fury or self.char.hp <= 1:
            self.basic(target)
            return
        self._rain(self.sk("skill"), ActionKind.SKILL, (DmgTag.SKILL,), target)

    def _extra_skill(self) -> None:
        if not self.in_fury or self.char.hp <= 1:
            return
        self._rain(self.sk(FUA_SKILL_ID), ActionKind.FUA, (DmgTag.SKILL, DmgTag.FUA), self.pick_target())
        if self.e(1) and self.countdown is not None:
            self.battle.delay(self.countdown, self.ep(1, 1))

    def ult(self, target: Enemy | None) -> None:
        refund = self.overflow
        self.overflow = 0.0
        if self.in_fury:
            rec = self.sk(TENAX_ID)
            lv = rec["params"][self.level_of(rec) - 1]
            mult = lv[0] * (self.ep(6, 0) if self.e(6) else 1.0)
            with self.action(ActionKind.ULT, rec, target) as act:
                act.aoe(mult, stat="hp", toughness=rec["toughness"][1], main_target=target)
        else:
            with self.action(ActionKind.ULT, "ult", target):
                for e in self.enemies():
                    self.balefire(e)
                self.consume_hp(self.p("ult", 0))
                self._enter_fury()
        if refund > 0:
            self.battle.gain_energy(self.char, refund, fixed=True)
