"""Evanescia (绯英) — Elation / Physical. Energy <-> Certified Banger coupling, Master Fox follow-ups every
240 Energy accumulated, Certified Banger conversion from teammates.

Policy: Skill when Skill Points allow, else Basic ATK (default rotation).
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..entities import Character, Enemy, Entity
from ..enums import ActionKind
from ..modifiers import Modifier, ModKind
from . import register
from ._batch8_util import BANGER, elation_priority, grant_banger
from .base import Kit

BANGER_TO_ENERGY_CAP = 100  # "cannot exceed 100 points in a single instance" (literal in the Talent text)
E6_BANGER_CAP = 1000  # "Up to 1000 points of Certified Banger can be taken into account" (literal, E6)
E6_BANGER_STEP = 100  # "For every 100 points of Certified Banger held" (literal, E6)


@register
class Evanescia(Kit):
    char_id = "1505"
    has_elation_skill = True
    elation_skill_id = "150520"

    def setup(self) -> None:
        self.accum = 0.0  # Energy accumulated toward Master Fox
        self.ults = 0
        self._syncing = False
        self.passive("Youth: Halcyon Evermore", {}, dyn=self._talent_elation, dyn_keys={S.ELATION_DMG_PCT})
        if self.trace(1):
            self.passive("Watch All Revels", {S.CRIT_RATE: self.tp(1, 0)})
        if self.e(1):
            self.passive("Home: A Prayer in Dance", {S.RES_PEN: self.ep(1, 0)})
        if self.e(2):
            self.passive("Voyage: A Wish for Everbloom", {S.CRIT_DMG: self.ep(2, 0)})
        if self.e(4):
            self.passive("Meadow: A Ruin by Vice", {S.DEF_IGNORE: self.ep(4, 0)})
        if self.e(6):
            self.passive("Maiden: A Step into Dreams", {}, dyn=self._e6_merry, dyn_keys={S.MERRYMAKE_PCT})
        self.on(E.ENERGY_GAINED, self._on_energy)
        self.on(E.MOD_APPLIED, self._on_banger)
        if self.trace(3):
            self.on(E.MOD_REMOVED, self._on_banger_end)

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        with self.action(ActionKind.EXTRA, None, label="Evanescia Technique", energy=0, sp=0) as act:
            act.aoe(p[0], toughness=20)
        grant_banger(self.battle, self.char, p[1], self.char)

    def banger_extra_turns(self) -> int:
        return int(self.ep(6, 1)) if self.e(6) else 0

    def _talent_elation(self, mod: Modifier, key: str, ent: Entity) -> float:
        return self.p("talent", 4) * self.char.stat(S.CRIT_DMG)

    def _e6_merry(self, mod: Modifier, key: str, ent: Entity) -> float:
        held = min(self.banger(), E6_BANGER_CAP)
        return self.ep(6, 0) + int(held / E6_BANGER_STEP) * self.ep(6, 2)

    # ------------------------------------------------ Energy <-> Banger
    def _gain_banger(self, amount: float) -> None:
        """Gain Certified Banger (and the equal Energy)."""
        if amount > 0:
            grant_banger(self.battle, self.char, amount, self.char)

    def _on_energy(self, ev: E.Ev) -> None:
        if ev.entity is not self.char:
            return
        amount = float(ev.amount)
        if not self._syncing:
            self._syncing = True
            try:
                grant_banger(self.battle, self.char, amount, self.char, from_energy=True)
            finally:
                self._syncing = False
        limit = self.p("talent", 2)
        self.accum += min(amount, limit)
        while self.accum >= limit:
            self.accum -= limit
            self.battle.queue_action(self._master_fox, self.char, "Master Fox", priority=8)

    def _on_banger(self, ev: E.Ev) -> None:
        mod = ev.mod
        if mod.name != BANGER or ev.refreshed:
            return
        p = float(mod.data.get("punchline", 0))
        if ev.target is self.char:
            if not mod.data.get("from_energy") and not self._syncing and p > 0:
                self._syncing = True
                try:
                    self.battle.gain_energy(self.char, min(p, BANGER_TO_ENERGY_CAP), fixed=True)
                finally:
                    self._syncing = False
            return
        if (
            self.trace(1)
            and isinstance(ev.target, Character)
            and ev.target is not self.char
            and elation_priority(self.battle, ev.target) < elation_priority(self.battle, self.char)
        ):
            gain = self.tp(1, 4) * p
            if self.e(2):
                gain *= 1.0 + self.ep(2, 1)
            self._gain_banger(gain)

    def _on_banger_end(self, ev: E.Ev) -> None:
        mod = ev.mod
        if mod.name != BANGER or not isinstance(ev.target, Character) or ev.target is self.char:
            return
        if mod.duration is None or mod.duration > 0:
            return  # consumed / removed early, not ended
        gain = self.tp(3, 0) * float(mod.data.get("punchline", 0))
        if self.e(2):
            gain *= 1.0 + self.ep(2, 2)
        self._gain_banger(gain)

    # ------------------------------------------------------------ Master Fox
    def _master_fox(self) -> None:
        rec = self.sk("talent")
        with self.battle.action(self.char, ActionKind.FUA, skill=rec, label="Master Fox", energy=0, sp=0) as act:
            act.aoe(self.p("talent", 0), toughness=self.toughness("talent", 1))
            p = self.banger()
            if p > 0:
                for e in self.enemies():
                    self.elation_hit(e, self.p("talent", 1), p, label="Master Fox (Elation)", action=act)
            if self.trace(2):
                for e in list(act.attacked):
                    if e.alive:
                        self.battle.try_debuff(
                            Modifier(
                                "Weigh All Truths",
                                stats={S.VULN: self.tp(2, 0)},
                                duration=int(self.tp(2, 1)),
                                kind=ModKind.DEBUFF,
                            ),
                            e,
                            self.char,
                            1.0,
                        )
        self.battle.gain_energy(self.char, self.p("talent", 3))
        if self.e(1):
            p = self.battle.elation.punchline  # approximation: the extra Elation Skill counts the current Punchline
            self.battle.queue_action(lambda: self.elation_skill(p), self.char, "Evanescia E1 Elation Skill", priority=8)

    # --------------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        self.simple_basic(target)

    def skill(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.SKILL, "skill", target) as act:
            act.blast(
                target,
                self.p("skill", 1),
                self.p("skill", 2),
                toughness=(self.toughness("skill", 0), self.toughness("skill", 2)),
            )
            p = self.banger()
            if p > 0:
                for e in list(act.attacked):
                    self.elation_hit(e, self.p("talent", 6), p, label="Discipline (Elation)", action=act)
        self.gain_punchline(int(self.p("skill", 3)))

    def ult(self, target: Enemy | None) -> None:
        n = int(self.p("ult", 1))
        if self.trace(1):
            count = len(self.enemies())
            n += int(self.tp(1, 1) if count >= 3 else self.tp(1, 2) if count == 2 else self.tp(1, 3))
        with self.action(ActionKind.ULT, "ult", target) as act:
            act.aoe(self.p("ult", 0), toughness=self.toughness("ult", 1), main_target=target)
            has_banger = self.banger() > 0
            p = max(self.banger(), int(self.char.max_energy))  # at least Max Energy for the Ultimate
            if has_banger:
                for e in self.enemies():
                    self.elation_hit(e, self.p("talent", 5), p, label="Swordsong (Elation)", action=act)
            for _ in range(n):
                pool = [e for e in self.enemies() if e.hp > 0] or self.enemies()
                if not pool:
                    break
                t = self.battle.rng.choice(pool)
                act.hit(t, self.p("ult", 2), toughness=self.toughness("ult", 0), primary=False)
                if has_banger:
                    self.elation_hit(t, self.p("talent", 7), p, label="Swordsong (Elation bounce)", action=act)
        self.ults += 1
        if self.e(6) and (self.ults - 1) % int(self.ep(6, 4)) == 0:
            self.battle.gain_energy(self.char, self.ep(6, 3), fixed=True)

    # --------------------------------------------------------- elation skill
    def elation_skill(self, punchline: float) -> None:
        rec = self.sk(self.elation_skill_id)
        lv = rec["params"][self.level_of(rec) - 1]
        tough = rec["toughness"]
        with self.action(ActionKind.ELATION, rec, label=rec["name"]) as act:
            for e in self.enemies():
                self.elation_hit(
                    e, lv[1], punchline, label=rec["name"], action=act, tags=("elation_skill",), toughness=tough[1]
                )
        self._gain_banger(lv[0] + (self.ep(1, 1) if self.e(1) else 0.0))
