"""Jingliu (镜流) — Destruction / Ice. Syzygy stacks, Spectral Transmigration (enhanced Skill, CRIT Rate,
ATK from teammates' consumed HP).

Base kit only (the enhanced kit is not implemented yet).

Options (``default_opts``):
* ``rotation``: ``"skill"`` (default: Transcendent Flash whenever SP allows outside Spectral Transmigration)
  or ``"basic"``. In Spectral Transmigration only Moon On Glacial River can be used.
"""

from __future__ import annotations

from typing import Any

from .. import stats as S
from ..entities import Enemy
from ..enums import ActionKind
from ..modifiers import Modifier, ModKind, Tick, hidden
from . import register
from .base import Kit
from .misha import CharFreeze

SYZYGY_MAX = 3  # Talent text "Syzygy can stack up to 3 times"
ENHANCED_SKILL_ID = "121209"  # "Moon On Glacial River"
HP_FLOOR = 1.0  # Talent text "this cannot reduce teammates' HP to lower than 1"
TRANSMIGRATION = "Spectral Transmigration"


@register
class Jingliu(Kit):
    char_id = "1212"
    default_opts = {"rotation": "skill"}

    def setup(self) -> None:
        if self.char.enhanced:
            raise NotImplementedError("Jingliu enhanced kit is not implemented yet")
        self.syzygy = 0
        self.state_mod: Modifier | None = None
        self.e2_ready = False

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        self.battle.gain_energy(self.char, p[5], fixed=True)
        for e in self.enemies():
            self.battle.try_debuff(
                CharFreeze(self.char, p[4], int(p[3]), label="Frozen (Jingliu Technique)"),
                e,
                self.char,
                p[1],
                debuff_type="freeze",
            )
        self.gain_syzygy(int(p[0]))

    # ------------------------------------------------------------ Syzygy
    @property
    def in_transmigration(self) -> bool:
        return self.state_mod is not None

    def syzygy_cap(self) -> int:
        return SYZYGY_MAX + (int(self.ep(6, 0)) if self.e(6) and self.in_transmigration else 0)

    def gain_syzygy(self, n: int) -> None:
        self.syzygy = min(self.syzygy_cap(), self.syzygy + n)
        if not self.in_transmigration and self.syzygy >= self.p("talent", 4):
            self._enter()

    def _enter(self) -> None:
        stats = {S.CRIT_RATE: self.p("talent", 6)}
        if self.trace(1):
            stats[S.EFFECT_RES] = self.tp(1, 0)
        if self.trace(3):
            stats[f"{S.DMG_PCT}:ult"] = self.tp(3, 0)
        if self.e(6):
            stats[S.CRIT_DMG] = self.ep(6, 1)
        self.state_mod = self.buff_self(
            Modifier(TRANSMIGRATION, stats=stats, tick=Tick.NONE, kind=ModKind.OTHER, dispellable=False)
        )
        if self.e(6):
            self.syzygy = min(self.syzygy_cap(), self.syzygy + int(self.ep(6, 0)))
        self.battle.advance(self.char, self.p("talent", 5))

    def _exit(self) -> None:
        if self.state_mod is not None:
            self.battle.remove_modifier(self.state_mod)
        self.state_mod = None
        self.syzygy = min(self.syzygy, SYZYGY_MAX)

    def _consume_team(self) -> Modifier | None:
        """Attacks in Spectral Transmigration consume teammates' HP; ATK rises until the attack ends."""
        if not self.in_transmigration:
            return None
        total = 0.0
        for c in self.teammates():
            cost = min(self.p("talent", 1) * c.max_hp, max(0.0, c.hp - HP_FLOOR))
            if cost > 0:
                total += self.battle.lose_hp(c, cost, self.char)
        ratio = self.p("talent", 2) + (self.ep(4, 0) if self.e(4) else 0.0)
        cap = self.p("talent", 3) + (self.ep(4, 1) if self.e(4) else 0.0)
        atk = min(ratio * total, cap * self.char.raw(S.BASE_ATK))
        return self.buff_self(hidden("Moon On Glacial River (ATK)", {S.ATK_FLAT: atk}))

    def _e1_buff(self) -> None:
        if self.e(1):
            self.buff_self(
                Modifier("Moon Crashes Tianguan Gate", stats={S.CRIT_DMG: self.ep(1, 0)}, duration=int(self.ep(1, 1)))
            )

    # ------------------------------------------------------------ policy
    def can_skill(self) -> bool:
        return self.in_transmigration or super().can_skill()

    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        if self.in_transmigration or (self.opts.get("rotation", "skill") == "skill" and self.can_skill()):
            self.skill(target)
        else:
            self.basic(target)

    # ----------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        if self.in_transmigration:  # only the enhanced Skill is available in Spectral Transmigration
            self.skill(target)
            return
        self.simple_basic(target)

    def skill(self, target: Enemy | None) -> None:
        assert target is not None
        if self.in_transmigration:
            self.enhanced_skill(target)
            return
        with self.action(ActionKind.SKILL, "skill", target) as act:
            act.hit(target, self.p("skill", 0), toughness=self.toughness("skill"))
        if self.trace(2):
            self.battle.advance(self.char, self.tp(2, 0))
        self.gain_syzygy(int(self.p("skill", 1)))

    def _blast_with_e1(self, act: Any, target: Enemy, main: float, adj: float, tough: tuple[float, float], **kw: Any) -> None:
        single = not self.battle.adjacent(target)
        act.blast(target, main, adj, toughness=tough, **kw)
        if self.e(1) and single:  # "If only one enemy target is attacked" (part of the same attack)
            act.hit(target, self.ep(1, 2), label="E1 Moon Crashes Tianguan Gate", **kw)

    def enhanced_skill(self, target: Enemy) -> None:
        rec = self.sk(ENHANCED_SKILL_ID)
        lv = rec["params"][self.level_of(rec) - 1]
        extra = {S.DMG_PCT: self.ep(2, 0)} if self.e2_ready else None
        self.e2_ready = False
        with self.action(ActionKind.SKILL, rec, target, sp=0) as act:
            atk = self._consume_team()
            self._e1_buff()
            self._blast_with_e1(
                act,
                target,
                lv[0],
                lv[2],
                (self.toughness(ENHANCED_SKILL_ID, 0), self.toughness(ENHANCED_SKILL_ID, 2)),
                extra=extra,
            )
            self.syzygy = max(0, self.syzygy - int(lv[1]))
        if atk is not None:
            self.battle.remove_modifier(atk)
        if self.syzygy <= 0:
            self._exit()

    def ult(self, target: Enemy | None) -> None:
        if target is None:
            return
        with self.action(ActionKind.ULT, "ult", target) as act:
            atk = self._consume_team()
            self._e1_buff()
            self._blast_with_e1(
                act, target, self.p("ult", 0), self.p("ult", 2), (self.toughness("ult", 0), self.toughness("ult", 2))
            )
        if atk is not None:
            self.battle.remove_modifier(atk)
        if self.e(2):
            self.e2_ready = True
        self.gain_syzygy(int(self.p("ult", 1)))  # "Gains 1 stack of Syzygy after attack ends"
