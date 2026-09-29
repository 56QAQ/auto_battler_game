"""Sushang (素裳) — Hunt / Physical. Sword Stance additional DMG on Skill (guaranteed on broken enemies),
Ultimate: ATK up, extra Sword Stance chances and an immediate action.

Options (``default_opts``):

* ``rotation``: ``"skill"`` (default, Skill whenever SP allows) or ``"basic"``.
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..entities import Enemy, Entity
from ..enums import ActionKind, Element
from ..modifiers import Modifier, Stacking, hidden
from . import register
from .base import Kit

ULT_EXTRA_STANCE_CHANCES = 2  # "using her Skill has 2 extra chances to trigger Sword Stance" (literal)
E1_SP = 1  # E1: "regenerates 1 Skill Point" (literal)
E2_TURNS = 1  # E2: "DMG taken ... reduced by 20% for 1 turn" (literal)
E6_MAX_STACKS = 2  # E6: "Talent's SPD Boost ... can stack up to 2 times" (literal)
E6_START_STACKS = 1  # E6: "after entering battle, Sushang immediately gains 1 stack" (literal)
ULT_BUFF = "Shape of Taixu: Dawn Herald"


@register
class Sushang(Kit):
    char_id = "1206"
    default_opts = {"rotation": "skill"}

    def setup(self) -> None:
        self.riposte = 0
        if self.trace(1):
            self.buff_self(hidden("Guileless", dyn=self._guileless, dyn_keys={S.AGGRO_PCT}))
        if self.e(4):
            self.passive("Cleave With Heart", {S.BREAK_EFFECT: self.ep(4, 0)})
        self.on(E.BREAK, self._on_break)

    def on_battle_start(self) -> None:
        if self.e(6):
            for _ in range(E6_START_STACKS):
                self._dancing_blade()

    def technique(self) -> None:
        mult = self.sk("technique")["params"][0][0]
        with self.action(ActionKind.EXTRA, None, label="Cloudfencer Art: Warcry", energy=0, sp=0) as act:
            act.aoe(mult)

    def _guileless(self, mod: Modifier, key: str, ent: Entity) -> float:
        return -self.tp(1, 1) if self.char.hp_ratio <= self.tp(1, 0) else 0.0

    # ------------------------------------------------------------- talent
    def _dancing_blade(self) -> None:
        self.buff_self(
            Modifier(
                "Dancing Blade",
                stats={S.SPD_PCT: self.p("talent", 0)},
                duration=int(self.p("talent", 1)),
                stacking=Stacking.STACK if self.e(6) else Stacking.REFRESH,
                max_stacks=E6_MAX_STACKS if self.e(6) else 1,
            )
        )

    def _on_break(self, ev: E.Ev) -> None:
        self._dancing_blade()

    # ------------------------------------------------------------ actions
    def _vanquisher(self) -> None:
        if self.trace(3) and any(e.broken for e in self.enemies()):
            self.battle.advance(self.char, self.tp(3, 0))

    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        self.simple_basic(target)
        self._vanquisher()

    def _sword_stance(self, target: Enemy, ratio: float) -> None:
        if not target.alive:
            return
        if not target.broken and self.battle.rng.random() >= self.p("skill", 2):
            return
        extra = {S.DMG_PCT: self.riposte * self.tp(2, 0)} if self.trace(2) else None
        self.battle.additional_damage(
            self.char, target, self.p("skill", 1) * ratio, element=Element.PHYSICAL, label="Sword Stance", extra=extra
        )
        if self.trace(2):
            self.riposte = min(self.riposte + 1, int(self.tp(2, 1)))
        if self.e(2):
            self.buff_self(Modifier("Refine in Toil", stats={S.MITIGATION: self.ep(2, 0)}, duration=E2_TURNS))

    def skill(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.SKILL, "skill", target) as act:
            act.hit(target, self.p("skill", 0), toughness=self.toughness("skill"))
            self._sword_stance(target, 1.0)
            if self.char.has_mod(ULT_BUFF):
                for _ in range(ULT_EXTRA_STANCE_CHANCES):
                    self._sword_stance(target, self.p("ult", 2))
        if self.e(1) and target.broken:
            self.battle.gain_sp(E1_SP, self.char)
        self._vanquisher()

    def ult(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.ULT, "ult", target) as act:
            act.hit(target, self.p("ult", 0), toughness=self.toughness("ult"))
        self.buff_self(Modifier(ULT_BUFF, stats={S.ATK_PCT: self.p("ult", 3)}, duration=int(self.p("ult", 1))))
        self.battle.advance(self.char, 1.0)  # "she immediately takes action"
