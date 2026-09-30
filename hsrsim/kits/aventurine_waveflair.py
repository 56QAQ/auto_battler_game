"""Aventurine • Waveflair (砂金•戏浪) — Elation / Quantum. Fervor: talent "Cheers!" outside the Aha Instant,
"All In!" enhanced Elation Skill, team CRIT DMG from teammates' attacks.

Policy: Skill when Skill Points allow, else Basic ATK (default rotation).
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..elation import AHA_INSTANT_END
from ..entities import Character, Enemy, Entity
from ..enums import ActionKind, DmgTag
from ..modifiers import Modifier
from . import register
from ._batch8_util import elation_count, grant_banger
from .base import Kit

CHEERS_ID = "151320"
ALL_IN_ID = "151321"


@register
class AventurineWaveflair(Kit):
    char_id = "1513"
    has_elation_skill = True
    elation_skill_id = CHEERS_ID

    def setup(self) -> None:
        self.fervor = 0
        self.all_in_next = False  # the next Elation Skill in an Aha Instant is "All In!"
        self.a6_left = int(self.tp(3, 4)) if self.trace(3) else 0
        self.elation_uses = 0
        self.solo = False
        self.aha_boost = 0.0
        if self.trace(1):
            self.passive("Party in Perfect Paradise", {}, dyn=self._a2, dyn_keys={S.ELATION_DMG_PCT})
        if self.trace(3):
            self.passive("Sift Through Gilded Dreams", {S.CRIT_DMG: self.tp(3, 0)})
        if self.e(1):
            self.passive("A Holiday on the Line", {S.RES_PEN: self.ep(1, 0)})
        if self.e(6):
            self.passive("The Past in Fast Lane", {S.MERRYMAKE_PCT: self.ep(6, 1)})
        self.on(E.ATTACK_END, self._teammate_attack)
        self.on(AHA_INSTANT_END, self._aha_end)

    def on_battle_start(self) -> None:
        self.solo = elation_count(self.battle) <= 1
        if self.trace(2) and not self.solo:
            self.passive("Revel in Raging Tides", {S.ELATION_DMG_PCT: self.tp(2, 4)}, scope=self.ally_scope)
            self.passive("Revel in Raging Tides (self)", {S.ELATION_DMG_PCT: self.tp(2, 0)})

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        with self.action(ActionKind.EXTRA, None, label="Aventurine • Waveflair Technique", energy=0, sp=0) as act:
            act.aoe(p[0], toughness=self.toughness("technique"))
        self.add_fervor(int(p[1]))
        grant_banger(self.battle, self.char, p[2], self.char)

    def banger_extra_turns(self) -> int:
        return 1  # Talent: the duration of Aventurine • Waveflair's Certified Banger increases by 1 turn

    def _a2(self, mod: Modifier, key: str, ent: Entity) -> float:
        spd = self.char.spd
        if spd < self.tp(1, 0):
            return 0.0
        excess = min(spd - self.tp(1, 0), self.tp(1, 4))
        return self.tp(1, 1) + int(excess / self.tp(1, 2)) * self.tp(1, 3)

    # --------------------------------------------------------------- Fervor
    def fervor_cap(self) -> int:
        return int(self.ep(2, 0)) if self.e(2) else int(self.p("talent", 3))

    def add_fervor(self, n: int) -> None:
        before = self.fervor
        self.fervor = min(self.fervor_cap(), self.fervor + n)
        step = int(self.p("talent", 0))
        thresholds = [step]
        if self.e(1):  # E1: every multiple of the base threshold up to the base cap (10/20/30)
            thresholds = [step * k for k in range(1, int(self.p("talent", 3)) // step + 1)]
        if self.e(2):  # E2: 40/50 also trigger
            thresholds += [step * k for k in range(int(self.p("talent", 3)) // step + 1, self.fervor_cap() // step + 1)]
        for th in thresholds:
            if before < th <= self.fervor:
                self.battle.queue_action(self._talent_cheers, self.char, "Cheers! To Summer's Blaze", priority=8)

    def _teammate_attack(self, ev: E.Ev) -> None:
        act = ev.attack
        owner = act.owner
        if not isinstance(owner, Character) or owner is self.char or not act.attacked:
            return
        self.gain_punchline(int(self.p("talent", 5)))
        fervor = int(self.p("talent", 6))
        if (
            self.trace(3)
            and self.a6_left > 0
            and act.kind
            in (
                ActionKind.BASIC,
                ActionKind.SKILL,
                ActionKind.FUA,
                ActionKind.ULT,
            )
        ):
            self.a6_left -= 1
            for c in self.allies():
                self.buff(
                    c,
                    Modifier(
                        "Sift Through Gilded Dreams", stats={S.CRIT_DMG: self.tp(3, 1)}, duration=int(self.tp(3, 2))
                    ),
                )
            fervor += int(self.tp(3, 3))
        if self.trace(2) and self.solo:
            grant_banger(self.battle, self.char, self.tp(2, 1), self.char)
            self.gain_punchline(int(self.tp(2, 3)))
            self._boost_aha(self.tp(2, 2))
        self.add_fervor(fervor)

    def _boost_aha(self, spd: float) -> None:
        # approximation: Aha's SPD is computed by the engine (no modifiers); a flat SPD boost is applied by
        # rescaling Aha's remaining action gauge as if its SPD had increased (until the end of the Aha Instant).
        aha = self.battle.elation.aha
        if not aha.on_timeline:
            return
        base = aha.spd
        aha.gauge *= (base + self.aha_boost) / (base + self.aha_boost + spd)
        self.aha_boost += spd

    def _aha_end(self, ev: E.Ev) -> None:
        self.aha_boost = 0.0

    # --------------------------------------------------------------- policy
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        self.simple_basic(target)

    def skill(self, target: Enemy | None) -> None:
        with self.action(ActionKind.SKILL, "skill", target) as act:
            act.aoe(self.p("skill", 0), toughness=self.toughness("skill", 1), main_target=target)
            p = self.banger()
            if p > 0:
                for e in self.enemies():
                    self.elation_hit(e, self.p("talent", 1), p, label="Ante Up (Skill)", action=act)
            if self.e(4):
                for c in self.allies():
                    self.buff(
                        c,
                        Modifier(
                            "Sunlight Runs No Tab", stats={S.DEF_IGNORE: self.ep(4, 0)}, duration=int(self.ep(4, 1))
                        ),
                    )
        if self.trace(3):
            self.a6_left = int(self.tp(3, 4))
        self.gain_punchline(int(self.p("skill", 1)))
        self.add_fervor(int(self.p("skill", 2)))

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult", target) as act:
            act.aoe(self.p("ult", 0), toughness=self.toughness("ult", 1), main_target=target)
            p = self.banger()
            if p > 0:
                for e in self.enemies():
                    self.elation_hit(e, self.p("talent", 2), p, label="Ante Up (Ultimate)", action=act)
            self.buff_self(Modifier("Grand Slam", stats={S.SPD_PCT: self.p("ult", 3)}, duration=int(self.p("ult", 4))))
        self.gain_punchline(int(self.p("ult", 2)))
        self.add_fervor(int(self.p("ult", 1)))

    # -------------------------------------------------------- elation skill
    def _use_all_in(self) -> bool:
        return self.e(6) and self.elation_uses >= int(self.ep(6, 0))

    def _tags(self) -> tuple[str, ...]:
        # A4 (only Elation character): Elation Skill DMG counts as a Follow-Up ATK
        return ("elation_skill", DmgTag.FUA) if (self.trace(2) and self.solo) else ("elation_skill",)

    def _talent_cheers(self) -> None:
        self._cast(self._use_all_in(), self.p("talent", 4))
        self.all_in_next = True

    def elation_skill(self, punchline: float) -> None:
        in_aha = self.battle.elation.current_p is not None
        all_in = (self.all_in_next and in_aha) or self._use_all_in()
        if in_aha:
            self.all_in_next = False
        self._cast(all_in, punchline)

    def _cast(self, all_in: bool, punchline: float) -> None:
        rec = self.sk(ALL_IN_ID if all_in else CHEERS_ID)
        lv = rec["params"][self.level_of(rec) - 1]
        tough = rec["toughness"]
        tags = self._tags()
        if all_in:
            aoe, extra, n, bounce = lv[0], lv[1], int(lv[2]), lv[3]
        else:
            aoe, extra, n, bounce = lv[0], 0.0, int(lv[1]), lv[2]
        with self.action(ActionKind.ELATION, rec, label=rec["name"]) as act:
            for e in self.enemies():
                self.elation_hit(
                    e, aoe, punchline, label=f"{rec['name']} (AoE)", action=act, tags=tags, toughness=tough[1]
                )
            spent = 0
            if all_in:
                spent = self.fervor
                # E6: "All In!" outside the Aha Instant no longer consumes Fervor
                if not (self.e(6) and self.battle.elation.current_p is None):
                    self.fervor = 0
            for i in range(n + spent):
                pool = [e for e in self.enemies() if e.hp > 0] or self.enemies()
                if not pool:
                    break
                self.elation_hit(
                    self.battle.rng.choice(pool),
                    bounce if i < n else extra,
                    punchline,
                    label=f"{rec['name']} (bounce)",
                    action=act,
                    tags=tags,
                    toughness=tough[0],
                )
        self.elation_uses += 1
        if self.e(2):
            self.add_fervor(int(self.ep(2, 1)))
