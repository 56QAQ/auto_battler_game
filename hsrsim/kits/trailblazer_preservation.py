"""Trailblazer (Preservation) (开拓者·存护) — Preservation / Fire. Magma Will, team shields, ATK+DEF ultimate.

Options:
  rotation: "auto" (default: Skill when SP >= ``skill_sp``), "skill" whenever SP allows, "basic" never
  skill_sp: SP threshold of the "auto" rotation (default 3)
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..entities import Enemy
from ..enums import ActionKind
from ..modifiers import Modifier, Stacking, Tick, hidden
from . import register
from .base import Kit

ENHANCED_BASIC = "08"  # skill ID suffix of the enhanced Basic ATK
MAGMA_GAIN = 1  # Basic ATK / Skill / being hit: "gains 1 stack of Magma Will" (literal)
MAGMA_COST = 4  # 'When "Magma Will" has no fewer than 4 stacks' / "Consumes 4 stacks" (literal)


class _TrailblazerPreservation(Kit):
    default_opts = {"rotation": "auto", "skill_sp": 3}

    def setup(self) -> None:
        self.magma = 0
        self.free_enhanced = False
        self.on(E.ALLY_ATTACKED, lambda ev: self.char in ev.targets and self.add_magma(MAGMA_GAIN))
        if self.trace(3):
            self.on(E.TURN_START, self._a6_start)
            self.on(
                E.TURN_END,
                lambda ev: ev.entity is self.char and self.battle.remove_named(self.char, "Action Beats Overthinking"),
            )

    def on_battle_start(self) -> None:
        if self.e(4):
            self.add_magma(int(self.ep(4, 0)))

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        self.battle.add_shield(
            self.char, p[0] * self.char.defense + p[1], self.char, duration=int(p[2]), name="Call of the Guardian"
        )

    # ------------------------------------------------------------ helpers
    def add_magma(self, n: int) -> None:
        self.magma = min(int(self.p("talent", 2)), self.magma + n)

    def _team_shield(self) -> None:
        d = self.char.defense
        value = self.p("talent", 0) * d + self.p("talent", 3)
        if self.e(2):
            value += self.ep(2, 0) * d + self.ep(2, 1)
        for c in self.allies():
            self.battle.add_shield(
                c, value, self.char, duration=int(self.p("talent", 1)), name="Treasure of the Architects"
            )

    def _e6(self) -> None:
        if self.e(6):
            self.buff_self(
                Modifier(
                    "City-Forging Bulwarks",
                    stats={S.DEF_PCT: self.ep(6, 0)},
                    max_stacks=int(self.ep(6, 1)),
                    stacking=Stacking.STACK,
                    tick=Tick.NONE,
                    key="City-Forging Bulwarks",
                )
            )

    def _a6_start(self, ev: E.Ev) -> None:
        if ev.entity is self.char and self.battle.shield_value(self.char) > 0:
            self.buff_self(hidden("Action Beats Overthinking", {S.ATK_PCT: self.tp(3, 1)}))
            self.battle.gain_energy(self.char, self.tp(3, 0))

    @property
    def enhanced_ready(self) -> bool:
        return self.free_enhanced or self.magma >= MAGMA_COST

    # ------------------------------------------------------------- policy
    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        rot = self.opts.get("rotation", "auto")
        use_skill = rot == "skill" or (rot == "auto" and self.battle.sp >= int(self.opts.get("skill_sp", 3)))
        if not self.enhanced_ready and use_skill and self.can_skill():
            self.skill(target)
        else:
            self.basic(target)

    # ------------------------------------------------------------ actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        if self.enhanced_ready:
            self._enhanced_basic(target)
            return
        mult = {"atk": self.p("basic", 0)}
        if self.e(1):
            mult["def"] = self.ep(1, 0)
        with self.action(ActionKind.BASIC, "basic", target) as act:
            act.hit(target, mult, toughness=self.toughness("basic"))
            self.add_magma(MAGMA_GAIN)
            self._team_shield()

    def _enhanced_basic(self, target: Enemy) -> None:
        rec = self.sk(self.char.char_id + ENHANCED_BASIC)
        lv = rec["params"][self.level_of(rec) - 1]
        if self.free_enhanced:
            self.free_enhanced = False  # the Ultimate's enhancement does not cost Magma Will
        else:
            self.magma -= MAGMA_COST
        main = {"atk": lv[0]}
        if self.e(1):
            main["def"] = self.ep(1, 1)  # approximation: E1's extra DEF-scaled DMG on the main target only
        tough = rec["toughness"]
        with self.action(ActionKind.BASIC, rec, target) as act:
            act.blast(target, main, lv[1], toughness=(float(tough[0]), float(tough[2])))
            if self.trace(2):
                self.battle.heal(self.char, self.tp(2, 0) * self.char.max_hp, self.char)
            self._team_shield()
        self._e6()

    def skill(self, target: Enemy | None) -> None:
        with self.action(ActionKind.SKILL, "skill"):
            # approximation: the DMG Reduction lasts as long as the Taunt (1 turn); Taunt not modelled
            self.buff_self(
                Modifier(
                    "Ever-Burning Amber", stats={S.MITIGATION: self.p("skill", 0)}, duration=int(self.p("skill", 2))
                )
            )
            self.add_magma(MAGMA_GAIN)
            if self.trace(1):
                for c in self.allies():
                    self.buff(
                        c,
                        Modifier(
                            "The Strong Defend the Weak",
                            stats={S.MITIGATION: self.tp(1, 1)},
                            duration=int(self.tp(1, 2)),
                        ),
                    )
            self._team_shield()

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult", target) as act:
            act.aoe(
                {"atk": self.p("ult", 0), "def": self.p("ult", 1)},
                toughness=self.toughness("ult", 1),
                main_target=target,
            )
            self._team_shield()
        self.free_enhanced = True
        self._e6()


@register
class TrailblazerPreservation(_TrailblazerPreservation):
    char_id = "8003"


@register
class TrailblazerPreservationF(_TrailblazerPreservation):
    char_id = "8004"
