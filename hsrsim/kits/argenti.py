"""Argenti (银枝) — Erudition / Physical. Apotheosis CRIT stacks, 90/180 Energy ultimates.

Options:
  ult_mode: "enhanced" (default) waits for 180 Energy and casts "Merit Bestowed in 'My' Garden";
            "normal" casts the 90-Energy Ultimate as soon as possible.
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..entities import Enemy
from ..enums import ActionKind, DmgTag
from ..modifiers import Modifier, Stacking, Tick
from . import register
from .base import Kit

ENHANCED_ULT = "14"  # skill ID suffix of the 180-Energy Ultimate


@register
class Argenti(Kit):
    char_id = "1302"
    default_opts = {"ult_mode": "enhanced"}

    def setup(self) -> None:
        self.apo_max = int(self.p("talent", 2)) + (int(self.ep(4, 1)) if self.e(4) else 0)
        self.enhanced_ult = False
        self.on(E.ACTION_END, self._talent)
        if self.trace(1):
            self.on(E.TURN_START, lambda ev: ev.entity is self.char and self.gain_apotheosis(int(self.tp(1, 0))))
        if self.trace(2):
            self.on(E.ENEMY_SPAWNED, lambda ev: self.battle.gain_energy(self.char, self.tp(2, 0)))
        if self.trace(3):
            self.on(E.BEFORE_HIT, self._courage)
        if self.e(6):
            self.passive('"Your" Resplendence', {f"{S.DEF_IGNORE}:{DmgTag.ULT}": self.ep(6, 0)})

    def on_battle_start(self) -> None:
        if self.e(4):
            self.gain_apotheosis(int(self.ep(4, 0)))

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        with self.action(ActionKind.EXTRA, None, label="Manifesto of Purest Virtue (technique)", energy=0, sp=0) as act:
            act.aoe(p[1])
        self.battle.gain_energy(self.char, p[2])

    # ---------------------------------------------------------- talent
    def gain_apotheosis(self, n: int) -> None:
        n = min(n, self.apo_max)
        if n <= 0:
            return
        stats = {S.CRIT_RATE: self.p("talent", 1)}
        if self.e(1):
            stats[S.CRIT_DMG] = self.ep(1, 0)
        self.buff_self(
            Modifier(
                "Apotheosis",
                stats=stats,
                stacks=n,
                max_stacks=self.apo_max,
                stacking=Stacking.STACK,
                tick=Tick.NONE,
                key="Apotheosis",
            )
        )

    @property
    def apotheosis(self) -> int:
        m = self.char.get_mod("Apotheosis")
        return m.stacks if m is not None else 0

    def _talent(self, ev: E.Ev) -> None:
        act = ev.action
        if act.owner is not self.char or act.kind not in (ActionKind.BASIC, ActionKind.SKILL, ActionKind.ULT):
            return
        n = len(act.attacked)
        if n:
            # approximation: granted once the action ends (in game per enemy as it is hit)
            self.battle.gain_energy(self.char, self.p("talent", 0) * n)
            self.gain_apotheosis(n)

    def _courage(self, ev: E.Ev) -> None:
        h = ev.hit
        if h.attacker is self.char and h.target.hp_ratio <= self.tp(3, 0):
            h.add(S.DMG_PCT, self.tp(3, 1))

    # ---------------------------------------------------------- ultimate
    def _enh_rec(self) -> dict:
        return self.sk(self.char.char_id + ENHANCED_ULT)

    def _costs(self) -> tuple[float, float]:
        rec = self._enh_rec()
        return self.p("ult", 1), float(rec["params"][self.level_of(rec) - 1][3])

    def ult_ready(self) -> bool:
        normal, enhanced = self._costs()
        need = normal if self.opts.get("ult_mode", "enhanced") == "normal" else enhanced
        return self.char.energy >= need - 1e-9

    def pay_ult_cost(self) -> None:
        normal, enhanced = self._costs()
        self.enhanced_ult = self.opts.get("ult_mode", "enhanced") != "normal" and self.char.energy >= enhanced - 1e-9
        self.char.energy = max(0.0, self.char.energy - (enhanced if self.enhanced_ult else normal))

    def ult(self, target: Enemy | None) -> None:
        if self.e(2) and len(self.enemies()) >= self.ep(2, 0):
            self.buff_self(Modifier("Agate's Humility", stats={S.ATK_PCT: self.ep(2, 1)}, duration=int(self.ep(2, 2))))
        if not self.enhanced_ult:
            with self.action(ActionKind.ULT, "ult", target) as act:
                act.aoe(self.p("ult", 0), toughness=self.toughness("ult", 1), main_target=target)
            return
        rec = self._enh_rec()
        lv = rec["params"][self.level_of(rec) - 1]
        tough = rec["toughness"]
        with self.action(ActionKind.ULT, rec, target) as act:
            act.aoe(lv[0], toughness=float(tough[1]), main_target=target)
            act.bounce(None, int(lv[1]), lv[2], toughness=float(tough[0]))

    # ----------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        self.simple_basic(target)

    def skill(self, target: Enemy | None) -> None:
        with self.action(ActionKind.SKILL, "skill", target) as act:
            act.aoe(self.p("skill", 0), toughness=self.toughness("skill", 1), main_target=target)
