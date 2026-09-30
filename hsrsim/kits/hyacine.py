"""Hyacine (风堇) — Remembrance / Wind. Max HP healer; memosprite Little Ica (0 SPD, never on the Action Order)
heals allies whose HP dropped and, while Hyacine is in "After Rain" (Ultimate), takes an extra turn after each of
Hyacine's abilities to deal AoE DMG equal to a share of the battle's healing tally.

Options (``default_opts``):
  * ``rotation``: ``"skill"`` (Skill whenever SP allows, default), ``"auto"`` (Skill only to summon Little Ica)
    or ``"basic"``.

# approximation: the healing tally counts the full heal amount (overhealing included).
# approximation: Little Ica's Talent heal consumes its HP once per trigger moment and heals every ally whose HP
#   dropped since the previous trigger in one go.
# not modelled: Little Ica's debuff immunity; the current-HP conversion when "After Rain" raises Max HP.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .. import events as E
from .. import stats as S
from ..entities import Enemy, Entity, Summon
from ..enums import ActionKind, Side
from ..modifiers import Modifier, Stacking, Tick, hidden
from . import register
from .base import Kit

if TYPE_CHECKING:
    from ..battle import Battle

ICA = "Little Ica"
AFTER_RAIN = "After Rain"
TALENT_BUFF = "First Light Heals the World"
MEMO_SKILL = "1140901"
MEMO_TALENT = "1140903"
MEMO_SUMMON = "1140905"
MEMO_LEAVE = "1140906"
ABILITY_KINDS = (ActionKind.BASIC, ActionKind.SKILL, ActionKind.ULT)


@register
class Hyacine(Kit):
    char_id = "1409"
    default_opts = {"rotation": "skill"}

    def setup(self) -> None:
        self.tally = 0.0  # healing done by Hyacine and Little Ica in this battle
        self.summoned_once = False
        self.pending: dict[int, Entity] = {}  # allies whose HP dropped (Little Ica's Talent)
        self._healing_guard = False
        self.on(E.HEALED, self._on_healed)
        self.on(E.HP_CHANGED, self._on_hp_changed)
        self.on(E.TURN_START, lambda ev: self._ica_talent())
        self.on(E.ACTION_END, self._on_action_end)
        if self.trace(1):
            self.passive("Gloomy Grin", {S.CRIT_RATE: self.tp(1, 0)})  # Little Ica syncs it from Hyacine
        if self.trace(2):
            self.passive("Stormy Caress", {S.EFFECT_RES: self.tp(2, 0)})
        if self.trace(3):
            keys = {S.HP_PCT, S.HEAL_PCT} | ({S.CRIT_DMG} if self.e(4) else set())
            self.passive("Tempestuous Halt", {}, dyn=self._a6, dyn_keys=keys)
        if self.e(1):
            self.on(E.ATTACK_END, self._e1)

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        for a in self.battle.allies(include_summons=True):
            self._heal(a, p[0], p[1])
            self.buff(a, Modifier("Day So Right, Life So Fine!", stats={S.HP_PCT: p[2]}, duration=int(p[3])))

    # ------------------------------------------------------------ helpers
    def _lv(self, sid: str) -> list[Any]:
        rec = self.sk(sid)
        return list(rec["params"][self.level_of(rec) - 1])

    def ica(self) -> Summon | None:
        return self.memosprite()

    def after_rain(self) -> bool:
        return self.char.has_mod(AFTER_RAIN)

    def _excess_spd(self) -> float:
        over = int(self.char.spd - self.tp(3, 0) + 1e-9)
        return float(min(max(0, over), int(self.tp(3, 4))))

    def _a6(self, mod: Modifier, key: str, ent: Entity) -> float:
        """Tempestuous Halt: Max HP above #1 SPD, Outgoing Healing (E4: CRIT DMG) per excess SPD."""
        if key == S.HP_PCT:
            return self.tp(3, 1) if self.char.spd > self.tp(3, 0) else 0.0
        steps = self._excess_spd() / self.tp(3, 2)
        if key == S.HEAL_PCT:
            return steps * self.tp(3, 3)
        return (self._excess_spd() / self.ep(4, 0)) * self.ep(4, 1)  # E4 CRIT DMG

    def _heal(self, target: Entity, ratio: float, flat: float, healer: Entity | None = None) -> None:
        """Healing = (#% of Hyacine's Max HP + flat) x (1 + Outgoing Healing + target's Incoming Healing)."""
        healer = healer or self.char
        bonus = healer.stat(S.HEAL_PCT) + target.stat(S.HEAL_TAKEN)
        if self.trace(1) and target.hp_ratio <= self.tp(1, 1):
            bonus += self.tp(1, 2)  # Gloomy Grin: healing an ally at or below #2% HP
        self.battle.heal(target, (ratio * self.char.max_hp + flat) * (1.0 + bonus), healer)

    def _heal_team(self, ratio: float, flat: float, ica_ratio: float, ica_flat: float) -> None:
        ica = self.ica()
        for a in self.battle.allies(include_summons=True):
            if a is not ica:
                self._heal(a, ratio, flat)
        if ica is not None:
            self._heal(ica, ica_ratio, ica_flat)

    def _dispel_team(self) -> None:
        if not self.trace(2):
            return
        for a in self.battle.allies(include_summons=True):
            for m in [m for m in a.debuffs if m.dispellable][: int(self.tp(2, 1))]:
                self.battle.remove_modifier(m)

    # ----------------------------------------------------------- Little Ica
    def summon_ica(self) -> Summon:
        ica = self.ica()
        if ica is not None:
            return ica
        ica = self.summon_memosprite(ICA, on_turn=self._ica_turn)
        ica.on_timeline = False  # "maintains 0 SPD ... will not appear in the Action Order"
        if self.trace(3):
            self.battle.apply(
                hidden("Tempestuous Halt (Little Ica)", {}, dyn=self._a6, dyn_keys={S.HP_PCT}), ica, self.char
            )
        if self.e(6):
            self.battle.apply(
                Modifier(
                    "O Sky, Heed My Plea",
                    stats={S.RES_PEN: self.ep(6, 1)},
                    tick=Tick.NONE,
                    scope=self.ally_scope,
                    dispellable=False,
                    key="Hyacine E6",
                ),
                ica,
                self.char,
            )
        energy = self._lv(MEMO_SUMMON)
        self.battle.gain_energy(self.char, energy[0] + (0.0 if self.summoned_once else energy[1]))
        self.summoned_once = True
        return ica

    def _ica_leaves(self, ica: Summon) -> None:
        self.battle.remove_unit(ica)
        self.battle.advance(self.char, self._lv(MEMO_LEAVE)[0])

    def _ica_turn(self, ica: Summon, battle: Battle) -> None:
        """Rainclouds, Time to Go!: AoE DMG = #1% of the healing tally, then clears #2% of the tally."""
        target = self.pick_target()
        if target is None:
            return
        rec = self.sk(MEMO_SKILL)
        lv = rec["params"][self.level_of(rec) - 1]
        base = lv[0] * self.tally
        with self.battle.action(ica, ActionKind.MEMOSPRITE, skill=rec, target=target) as act:
            act.aoe(0.0, stat="hp", flat=base, toughness=float(rec["toughness"][1]), main_target=target)
        clear = self.ep(6, 0) if self.e(6) else lv[1]
        self.tally = max(0.0, self.tally - clear * self.tally)

    def _ica_talent(self) -> None:
        """Take Sky in Hand: heal allies whose HP was reduced (at any turn start / after any action)."""
        ica = self.ica()
        if ica is None or not self.pending or self._healing_guard:
            return
        lv = self._lv(MEMO_TALENT)
        targets = [a for a in self.pending.values() if a.alive]
        self.pending.clear()
        self._healing_guard = True
        try:
            self.battle.lose_hp(ica, lv[0] * ica.max_hp, ica)
            for a in targets:
                self._heal(a, lv[1], lv[2], healer=ica)
            if self.after_rain():
                for a in self.battle.allies(include_summons=True):
                    self._heal(a, lv[3], lv[4], healer=ica)
        finally:
            self._healing_guard = False
        if ica.hp <= 0:
            self._ica_leaves(ica)

    # ------------------------------------------------------------ listeners
    def _on_healed(self, ev: E.Ev) -> None:
        src = ev.source
        ica = self.ica()
        if src is not self.char and (ica is None or src is not ica):
            return
        self.tally += ev.amount
        if ica is not None:  # Talent: Little Ica's DMG dealt (stacks per healing instance)
            self.battle.apply(
                Modifier(
                    TALENT_BUFF,
                    stats={S.DMG_PCT: self.p("talent", 2)},
                    duration=int(self.p("talent", 3)),
                    stacking=Stacking.STACK,
                    max_stacks=int(self.p("talent", 4)),
                ),
                ica,
                self.char,
            )

    def _on_hp_changed(self, ev: E.Ev) -> None:
        ent = ev.entity
        if ev.delta >= 0 or ent.side != Side.ALLY or not ent.targetable or ent is self.ica():
            return
        self.pending[ent.uid] = ent
        if self.e(2):
            self.buff(
                ent, Modifier("Come Sit in My Courtyard", stats={S.SPD_PCT: self.ep(2, 0)}, duration=int(self.ep(2, 1)))
            )

    def _on_action_end(self, ev: E.Ev) -> None:
        act = ev.action
        ica = self.ica()
        if act.actor is self.char and act.kind in ABILITY_KINDS and ica is not None and self.after_rain():
            # "gains 1 extra turn and automatically casts Rainclouds, Time to Go! immediately after Hyacine uses
            # an ability" (the extra turn also counts down Little Ica's Continuous Effects)
            self.battle.queue_action(lambda: self.battle.take_turn(ica, extra_turn=True), ica, "Little Ica")
        self._ica_talent()

    def _e1(self, ev: E.Ev) -> None:
        """E1: while "After Rain" is active, allies restore HP after attacking."""
        act = ev.attack
        actor = act.actor
        if not self.after_rain() or actor.side != Side.ALLY or not actor.targetable:
            return
        self._heal(actor, self.ep(1, 1), 0.0)

    # --------------------------------------------------------------- policy
    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        policy = self.opts.get("rotation", "skill")
        if policy == "basic" or not self.can_skill() or (policy == "auto" and self.ica() is not None):
            self.basic(target)
        else:
            self.skill(target)

    # -------------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.BASIC, "basic", target) as act:
            act.hit(target, self.p("basic", 0), stat="hp", toughness=self.toughness("basic"), splits="data")

    def skill(self, target: Enemy | None) -> None:
        with self.action(ActionKind.SKILL, "skill"):
            self.summon_ica()
            self._dispel_team()
            self._heal_team(self.p("skill", 0), self.p("skill", 1), self.p("skill", 2), self.p("skill", 3))

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult"):
            self.summon_ica()
            self._dispel_team()
            self._heal_team(self.p("ult", 0), self.p("ult", 1), self.p("ult", 5), self.p("ult", 6))
            hp_pct = self.p("ult", 2) + (self.ep(1, 0) if self.e(1) else 0.0)
            self.buff_self(
                Modifier(
                    AFTER_RAIN,
                    stats={S.HP_PCT: hp_pct, S.HP_FLAT: self.p("ult", 3)},
                    duration=int(self.p("ult", 4)),
                    tick=Tick.HOLDER_TURN_START,
                    scope=self.ally_scope,
                    dispellable=False,
                )
            )
