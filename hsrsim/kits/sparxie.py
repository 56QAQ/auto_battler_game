"""Sparxie (火花) — Elation / Fire. Livestream: repeated Engagement Farming, Bloom enhanced Basic ATK, Thrill.

Policy options:
  ``farming``: max Engagement Farming triggers per livestream (default 20 = the game's cap)
  ``sp_reserve``: Skill Points to keep for teammates (default 1)
  ``straight_fire_chance``: probability of the "Straight Fire" gift (default 0.5; the real
      distribution is not in the data files)
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..elation import AHA_INSTANT_END
from ..entities import Enemy, Entity
from ..enums import ActionKind, Path
from ..modifiers import Modifier, Stacking
from . import register
from .base import Kit


@register
class Sparxie(Kit):
    char_id = "1501"
    has_elation_skill = True
    elation_skill_id = "150120"
    default_opts = {"farming": 20, "sp_reserve": 1, "straight_fire_chance": 0.5}

    def setup(self) -> None:
        self.thrill = 0
        if self.trace(1):
            self.passive("Punchline Signing", {}, dyn=self._a2, dyn_keys={S.ELATION_DMG_PCT})
        if self.trace(3):
            self.passive(
                "Palette of Truth and Lies",
                {},
                scope=self.ally_scope,
                key="Sparxie A6",
                dyn=lambda m, k, e: min(self.tp(3, 1), self.tp(3, 0) * self.battle.elation.punchline),
                dyn_keys={S.CRIT_DMG},
            )
        if self.e(1):
            self.passive(
                "#GoingViral",
                {},
                scope=self.ally_scope,
                key="Sparxie E1",
                dyn=lambda m, k, e: min(self.ep(1, 2), self.ep(1, 1) * self.battle.elation.punchline),
                dyn_keys={S.RES_PEN},
            )
        if self.e(6):
            self.passive("#BuiltDifferent", {S.RES_PEN: self.ep(6, 2)})
        self.on(AHA_INSTANT_END, self._after_aha)

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        self.battle.gain_sp(int(p[0]), self.char)
        with self.action(ActionKind.EXTRA, None, label="Sparxie Technique", energy=0, sp=0) as act:
            act.aoe(p[1])

    def _a2(self, mod: Modifier, key: str, ent: Entity) -> float:
        over = self.char.atk - self.tp(1, 0)
        return min(self.tp(1, 3), max(0, int(over / self.tp(1, 1))) * self.tp(1, 2)) if over > 0 else 0.0

    def _after_aha(self, ev: E.Ev) -> None:
        if self.char not in ev.participants:
            return
        if self.e(1):
            self.gain_punchline(int(self.ep(1, 0)))
        if self.e(2):
            self.thrill += int(self.ep(2, 0))
            self.battle.queue_extra_turn(self.char)

    # ----------------------------------------------------------- thrill / SP
    def _pay(self) -> bool:
        """Pay 1 Skill Point, using Thrill first (consuming Thrill counts as consuming SP)."""
        if self.thrill > 0:
            self.thrill -= 1
            self.battle.events.emit(E.SP_CHANGED, delta=-1, entity=self.char, thrill=True)
            if self.e(2):
                self.buff_self(
                    Modifier(
                        "#AudienceKnows",
                        stats={S.CRIT_DMG: self.ep(2, 1)},
                        duration=int(self.ep(2, 2)),
                        stacking=Stacking.STACK,
                        max_stacks=int(self.ep(2, 3)),
                    )
                )
            return True
        if self.battle.sp >= 1:
            self.battle.use_sp(1, self.char)
            return True
        return False

    def _can_pay(self, reserve: int) -> bool:
        return self.thrill > 0 or self.battle.sp > reserve

    # --------------------------------------------------------------- policy
    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        if self.opts.get("rotation", "skill") == "skill" and self._can_pay(0):
            self.livestream(target)
        else:
            self.basic(target)

    # -------------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        self.simple_basic(target)

    def livestream(self, target: Enemy) -> None:
        farm = self.sk("150109")
        lv = farm["params"][self.level_of(farm) - 1]
        n = 0
        with self.action(ActionKind.EXTRA, "skill", target, label="Livestream", sp=0, energy=0):
            self._pay()
            n += 1
            self._engagement(lv)
            limit = min(int(self.opts["farming"]), int(self.p("skill", 0)))
            while n < limit and self._can_pay(int(self.opts["sp_reserve"])):
                self._pay()
                n += 1
                self._engagement(lv)
        self.bloom(target, n, lv)

    def _engagement(self, lv: list[float]) -> None:
        # approximation: the gift is drawn with the "straight_fire_chance" option; the game's odds are not in the data
        # and its pity rule (a guaranteed "Straight Fire" after enough "Unreal Banger", Sparxie_Skill02_MinorPrizeGetNum
        # / MAvatar_Sparxie_00_Skill02_MustGrandPrize) is not modelled
        if self.battle.rng.random() < float(self.opts["straight_fire_chance"]):
            self.gain_punchline(int(lv[2]))
            self.battle.gain_sp(int(lv[0]), self.char)
        else:
            self.gain_punchline(int(lv[1]))

    def bloom(self, target: Enemy, n: int, farm_lv: list[float]) -> None:
        rec = self.sk("150108")
        lv = rec["params"][self.level_of(rec) - 1]
        main = lv[0] + farm_lv[3] * n
        adj = lv[1] + farm_lv[4] * n
        with self.action(ActionKind.BASIC, rec, target, label=rec["name"]) as act:
            act.blast(target, main, adj, toughness=(rec["toughness"][0], rec["toughness"][2]))
            p = self.banger()
            if p > 0:
                self.elation_hit(target, self.p("talent", 2), p, label="Sleight of Sparx Hand", action=act)
                for a in self.battle.adjacent(target):
                    self.elation_hit(a, self.p("talent", 3), p, label="Sleight of Sparx Hand", action=act)
                attacked = [t for t in act.attacked if t.alive]
                for _ in range(n):
                    if not attacked:
                        break
                    t = self.battle.rng.choice(attacked)
                    self.elation_hit(t, self.p("talent", 0), p, label="Sleight of Sparx Hand (farming)", action=act)

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult", target) as act:
            gain = int(self.p("ult", 0))
            if self.trace(2):
                n_el = sum(1 for c in self.battle.team if c.path == Path.ELATION)
                idx = min(max(n_el, 1), 3) - 1
                gain += int(self.tp(2, idx))
                self.thrill += int(self.tp(2, 3 + idx))
            if self.e(4):
                gain += int(self.ep(4, 0))
                self.buff_self(
                    Modifier("#LockedIn", stats={S.ELATION_DMG_PCT: self.ep(4, 1)}, duration=int(self.ep(4, 2)))
                )
            self.gain_punchline(gain)
            mult = self.p("ult", 2) * self.char.stat(S.ELATION_DMG_PCT) + self.p("ult", 1)
            act.aoe(mult, toughness=self.toughness("ult", 1), main_target=target)
            p = self.banger()
            if p > 0:
                for e in self.enemies():
                    self.elation_hit(e, self.p("talent", 1), p, label="Sleight of Sparx Hand (ult)", action=act)

    # ------------------------------------------------------- elation skill
    def elation_skill(self, punchline: float) -> None:
        rec = self.sk(self.elation_skill_id)
        lv = rec["params"][self.level_of(rec) - 1]
        tough = rec["toughness"]
        n = int(lv[2])
        if self.e(6):
            n = min(int(self.ep(6, 1)), n + int(punchline) * int(self.ep(6, 0)))
        with self.action(ActionKind.ELATION, rec, label=rec["name"]) as act:
            for e in self.enemies():
                self.elation_hit(
                    e,
                    lv[1],
                    punchline,
                    label="Signal Overflow (AoE)",
                    action=act,
                    tags=("elation_skill",),
                    toughness=tough[1],
                )
            for _ in range(n):
                pool = [e for e in self.enemies() if e.hp > 0] or self.enemies()
                if not pool:
                    break
                self.elation_hit(
                    self.battle.rng.choice(pool),
                    lv[0],
                    punchline,
                    label="Signal Overflow (bounce)",
                    action=act,
                    tags=("elation_skill",),
                    toughness=tough[0],
                )
        self.thrill += int(lv[3])
