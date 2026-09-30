"""Jade (翡翠) — Erudition / Quantum. Debt Collector (SPD + additional DMG), Charge-based AoE follow-ups, Pawned Asset.

Options:
  target:   name of the ally made Debt Collector by the Skill (default: first other slot)
  rotation: "skill" (default) Skill whenever no Debt Collector exists and SP allows, "basic" never
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..entities import Character, Enemy, Entity
from ..enums import ActionKind, DmgTag, Element
from ..modifiers import Modifier, Stacking, Tick
from . import register
from .base import Kit

DEBT_COLLECTOR = "Debt Collector"


@register
class Jade(Kit):
    char_id = "1314"
    default_opts = {"target": None}

    def setup(self) -> None:
        self.charge = 0
        self.fua_queued = False
        self.enhanced_left = 0
        self.dc: Character | None = None
        self.on(E.ATTACK_END, self._after_attack)
        if self.trace(1):
            self.on(E.ENEMY_SPAWNED, lambda ev: self.pawn(int(self.tp(1, 1))))
            self.on(E.TURN_START, self._a2_turn_start)
        if self.e(1):
            self.passive("Altruism? Nevertheless Tradable", {f"{S.DMG_PCT}:{DmgTag.FUA}": self.ep(1, 0)})
        if self.e(2):
            self.passive("Morality? Herein Authenticated", {}, dyn=self._e2, dyn_keys={S.CRIT_RATE})
        if self.e(6):
            self.passive("Equity? Pending Sponsorship", {}, dyn=self._e6, dyn_keys={f"{S.RES_PEN}:Quantum"})

    def on_battle_start(self) -> None:
        if self.trace(2):
            self.battle.advance(self.char, self.tp(2, 0))

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        with self.action(ActionKind.EXTRA, None, label="Visionary Predation (technique)", energy=0, sp=0) as act:
            act.data["jade_no_charge"] = True
            act.aoe(p[1])
        self.pawn(int(p[2]))

    # ------------------------------------------------------ Pawned Asset
    def pawn(self, n: int) -> None:
        if n <= 0:
            return
        stats = {S.CRIT_DMG: self.p("talent", 0)}
        if self.trace(3):
            stats[S.ATK_PCT] = self.tp(3, 0)
        mx = int(self.p("talent", 1))
        self.buff_self(
            Modifier(
                "Pawned Asset",
                stats=stats,
                stacks=min(n, mx),
                max_stacks=mx,
                stacking=Stacking.STACK,
                tick=Tick.NONE,
                key="Pawned Asset",
            )
        )

    @property
    def pawned(self) -> int:
        m = self.char.get_mod("Pawned Asset")
        return m.stacks if m is not None else 0

    def _e2(self, mod: Modifier, key: str, ent: Entity) -> float:
        return self.ep(2, 1) if self.pawned >= self.ep(2, 0) else 0.0

    def _e6(self, mod: Modifier, key: str, ent: Entity) -> float:
        return self.ep(6, 0) if self.debt_collector() is not None else 0.0

    # ---------------------------------------------------- Debt Collector
    def debt_collector(self) -> Character | None:
        dc = self.dc
        if dc is not None and dc.alive and dc.has_mod(DEBT_COLLECTOR):
            return dc
        return None

    def _a2_turn_start(self, ev: E.Ev) -> None:
        dc = self.debt_collector()
        if dc is not None and ev.entity is dc:
            self.pawn(int(self.tp(1, 0)))

    def _after_attack(self, ev: E.Ev) -> None:
        act = ev.attack
        if not act.attacked:
            return
        dc = self.debt_collector()
        # approximation: only the Debt Collector character's own attacks count (not its summons')
        by_dc = dc is not None and act.actor is dc
        by_jade = act.actor is self.char
        if dc is not None and (by_dc or (by_jade and self.e(6))):
            for t in act.attacked:
                if t.alive and t.hp > 0:
                    self.battle.additional_damage(
                        self.char, t, self.p("skill", 2), element=Element.QUANTUM, label="Debt Collector (Jade)"
                    )
            if by_dc and dc is not self.char:
                self.battle.lose_hp(dc, self.p("skill", 1) * dc.max_hp, self.char)
        if act.data.get("jade_no_charge") or not (by_dc or by_jade):
            return
        n = len(act.attacked)
        if by_dc and dc is not self.char and self.e(1):
            # E1: 1 enemy hit -> +#3 Charge, 2 enemies hit -> +#2 Charge (the enemy counts are literal)
            n += {1: int(self.ep(1, 2)), 2: int(self.ep(1, 1))}.get(len(act.attacked), 0)
        self.add_charge(n)

    # ------------------------------------------------------------ talent
    def add_charge(self, n: int) -> None:
        self.charge += n
        if self.charge >= self.p("talent", 2) and not self.fua_queued:
            self.fua_queued = True
            self.battle.queue_action(self._fua, self.char, "Jade follow-up")

    def _fua(self) -> None:
        self.fua_queued = False
        need = int(self.p("talent", 2))
        if self.charge < need:
            return
        self.charge -= need
        self.pawn(int(self.p("talent", 3)))
        mult = self.p("talent", 4)
        if self.enhanced_left > 0:
            self.enhanced_left -= 1
            mult += self.p("ult", 0)
        target = self.battle.default_target()
        with self.action(ActionKind.FUA, "talent", target) as act:
            act.data["jade_no_charge"] = True  # "This Follow-Up ATK does not generate Charge"
            act.aoe(mult, toughness=self.toughness("talent", 1), main_target=target)
        if self.charge >= need:
            self.add_charge(0)

    # ------------------------------------------------------------- policy
    def can_skill(self) -> bool:
        return self.debt_collector() is None and super().can_skill()

    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        if self.opts.get("rotation", "skill") == "skill" and self.can_skill():
            self.skill(target)
        else:
            self.basic(target)

    # ------------------------------------------------------------ actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.BASIC, "basic", target) as act:
            act.blast(
                target,
                self.p("basic", 0),
                self.p("basic", 1),
                toughness=(self.toughness("basic", 0), self.toughness("basic", 2)),
            )

    def skill(self, target: Enemy | None) -> None:
        ally = self.main_dps()
        with self.action(ActionKind.SKILL, "skill", ally):
            stats = {} if ally is self.char else {S.SPD_FLAT: self.p("skill", 0)}
            self.buff(
                ally,
                Modifier(
                    DEBT_COLLECTOR,
                    stats=stats,
                    duration=int(self.p("skill", 3)),
                    tick=Tick.SOURCE_TURN_START,
                    key=DEBT_COLLECTOR,
                ),
            )
            self.dc = ally

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult", target) as act:
            act.aoe(self.p("ult", 2), toughness=self.toughness("ult", 1), main_target=target)
        self.enhanced_left = int(self.p("ult", 1))
        if self.e(4):
            self.buff_self(
                Modifier("Sincerity? Put Option Only", stats={S.DEF_IGNORE: self.ep(4, 0)}, duration=int(self.ep(4, 1)))
            )
