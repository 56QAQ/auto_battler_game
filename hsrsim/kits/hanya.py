"""Hanya (寒鸦) — Harmony / Physical. Burden: SP recovery every 2 ally attacks and a DMG buff (Sanction);
Ultimate grants one ally SPD (from Hanya's SPD) and ATK.

Options (``default_opts``):
* ``rotation``: ``"skill"`` (default: Skill whenever SP allows) or ``"basic"``.
* ``target``: name of the ally receiving the Ultimate (default: the first other team slot).
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..entities import Character, Enemy
from ..enums import ActionKind, Side
from ..modifiers import Modifier, ModKind, Tick
from . import register
from .base import Kit

BURDEN = "Burden"
BURDEN_ATTACKS = 2  # Skill text "For every 2 Basic ATKs, Skills, or Ultimates allies use on an enemy with Burden"
BURDEN_SP = 1  # "... allies will immediately recover 1 Skill Point"
ULT_BUFF = "Ten-Lords' Decree, All Shall Obey"
TRIGGER_KINDS = (ActionKind.BASIC, ActionKind.SKILL, ActionKind.ULT)


@register
class Hanya(Kit):
    char_id = "1215"
    ult_targets_ally = True
    default_opts = {"rotation": "skill", "target": None}

    def setup(self) -> None:
        self.burden: Modifier | None = None
        self.e1_turn = -1
        self.on(E.ACTION_START, self._before_use)
        self.on(E.ACTION_END, self._after_use)
        if self.trace(2):
            self.on(E.KILL, self._a4)
        if self.e(1):
            self.on(E.KILL, self._e1)

    def technique(self) -> None:
        enemies = self.enemies()
        if enemies:
            self.apply_burden(self.battle.rng.choice(enemies))

    # ------------------------------------------------------------ Burden
    def burden_holder(self) -> Enemy | None:
        m = self.burden
        if m is None or m.removed or not isinstance(m.holder, Enemy) or not m.holder.alive:
            return None
        return m.holder

    def apply_burden(self, target: Enemy) -> None:
        for e in self.enemies():  # "Burden is only active on the latest target it is applied to"
            self.battle.remove_named(e, BURDEN)
        mod = Modifier(BURDEN, kind=ModKind.DEBUFF, tick=Tick.NONE, key=BURDEN)
        mod.data.update(count=0, triggers=0)
        self.burden = self.battle.apply(mod, target, self.char)

    def _sanction(self, act_owner: Character) -> None:
        dmg = self.p("talent", 0) + (self.ep(6, 0) if self.e(6) else 0.0)
        self.buff(act_owner, Modifier("Sanction", stats={S.DMG_PCT: dmg}, duration=int(self.p("talent", 1))))

    def _before_use(self, ev: E.Ev) -> None:
        act = ev.action
        if act.kind not in TRIGGER_KINDS or not isinstance(act.owner, Character):
            return
        holder = self.burden_holder()
        act.data["hanya_burden"] = holder
        if holder is not None and act.target is holder:
            act.data["hanya_sanction"] = True
            self._sanction(act.owner)

    def _after_use(self, ev: E.Ev) -> None:
        act = ev.action
        if act.kind not in TRIGGER_KINDS or not isinstance(act.owner, Character) or act.owner.side != Side.ALLY:
            return
        holder = self.burden_holder()
        if holder is None or (holder not in act.attacked and act.target is not holder):
            return
        if not act.data.get("hanya_sanction") and act.data.get("hanya_burden") is holder:
            # approximation: Burden holder hit as a secondary (blast/AoE) target; the game grants Sanction before
            # the attack, the engine only learns the attacked targets afterwards
            self._sanction(act.owner)
        m = self.burden
        assert m is not None
        m.data["count"] += 1
        if m.data["count"] < BURDEN_ATTACKS:
            return
        m.data["count"] = 0
        m.data["triggers"] += 1
        self.battle.gain_sp(BURDEN_SP, self.char)
        if self.trace(1):
            self.buff(act.owner, Modifier("Scrivener", stats={S.ATK_PCT: self.tp(1, 0)}, duration=int(self.tp(1, 1))))
        if self.trace(3):
            self.battle.gain_energy(self.char, self.tp(3, 0))
        if m.data["triggers"] >= int(self.p("skill", 1)):
            self.battle.remove_modifier(m)
            self.burden = None

    def _a4(self, ev: E.Ev) -> None:
        m = ev.target.get_mod(BURDEN)
        if m is not None and m.source is self.char and m.data.get("triggers", 0) <= self.tp(2, 0):
            self.battle.gain_sp(int(self.tp(2, 1)), self.char)

    def _e1(self, ev: E.Ev) -> None:
        killer = ev.killer
        if killer is None or self.e1_turn == self.battle.turns:
            return
        mod = killer.get_mod(ULT_BUFF)
        if mod is not None and mod.source is self.char:
            self.e1_turn = self.battle.turns
            self.battle.advance(self.char, self.ep(1, 0))

    # ----------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        self.simple_basic(target)

    def skill(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.SKILL, "skill", target) as act:
            act.hit(target, self.p("skill", 0), toughness=self.toughness("skill"))
            if target.alive and target.hp > 0:
                self.apply_burden(target)  # the Skill itself then counts as the first of the 2 uses
        if self.e(2):
            self.buff_self(Modifier("Two Views", stats={S.SPD_PCT: self.ep(2, 0)}, duration=int(self.ep(2, 1))))

    def ult(self, target: Enemy | None) -> None:
        ally = self.main_dps()
        with self.action(ActionKind.ULT, "ult", ally):
            dur = int(self.p("ult", 1)) + (int(self.ep(4, 0)) if self.e(4) else 0)
            self.buff(
                ally,
                Modifier(
                    ULT_BUFF,
                    stats={S.SPD_FLAT: self.p("ult", 2) * self.char.spd, S.ATK_PCT: self.p("ult", 0)},
                    duration=dur,
                    key=ULT_BUFF,  # "Replace": one instance regardless of the caster
                ),
            )
