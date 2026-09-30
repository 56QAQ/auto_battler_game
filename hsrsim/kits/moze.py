"""Moze (貊泽) — The Hunt / Lightning. Marks "Prey" and leaves the field (Departed) while allies hit it.

Options: ``rotation`` ("skill" default | "basic").

While Prey exists Moze is Departed: off the action order and untargetable (he can still use his
Ultimate). Every ally attack on Prey triggers Lightning Additional DMG and consumes 1 Charge; every
3 Charge consumed launch a Talent Follow-Up ATK. At 0 Charge Prey is dispelled and Moze returns.
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..battle import Action
from ..entities import Enemy
from ..enums import ActionKind, DmgTag, Element, Side
from ..modifiers import Modifier, ModKind, Tick
from . import register
from .base import Kit

PREY = "Prey"


@register
class Moze(Kit):
    char_id = "1223"

    def setup(self) -> None:
        self.prey: Enemy | None = None
        self.charge = 0
        self.consumed = 0  # Charge consumed towards the next Follow-Up ATK
        self.fua_action: Action | None = None
        self.pending_dispel = False
        self.a2_turn = -(10**9)
        self.departed = False
        self.on(E.ATTACK_END, self._talent)
        self.on(E.KILL, self._on_kill)
        if self.trace(2):
            self.on(E.WAVE_START, self._a4_wave)
        if self.e(2):
            self.on(E.BEFORE_HIT, self._e2)

    def _a4_wave(self, ev: E.Ev) -> None:
        self.battle.advance(self.char, self.tp(2, 1))  # while Departed the (frozen) gauge still moves forward

    def on_battle_start(self) -> None:
        if self.e(1):
            self.battle.gain_energy(self.char, self.ep(1, 1), fixed=True)

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        self.buff_self(Modifier("Bated Wings", stats={S.DMG_PCT: p[1]}, duration=int(p[2])))

    # --------------------------------------------------------------- Prey
    def _mark(self, target: Enemy) -> None:
        stats = {f"{S.VULN}:{DmgTag.FUA}": self.tp(3, 0)} if self.trace(3) else {}
        self.battle.apply(
            Modifier(PREY, stats=stats, kind=ModKind.DEBUFF, tick=Tick.NONE, dispellable=False, key="Moze Prey"),
            target,
            self.char,
        )
        self.prey = target
        if not self.departed:
            self.departed = True
            self.char.on_timeline = False  # off the Action Order, gauge frozen
            self.char.targetable = False

    def _dispel(self) -> None:
        if self.prey is not None:
            self.battle.remove_named(self.prey, PREY)
        self.prey = None
        self.charge = 0
        self.consumed = 0
        self.pending_dispel = False
        if self.departed:
            self.departed = False
            self.char.on_timeline = True
            self.char.targetable = True
            if self.trace(2):
                self.battle.advance(self.char, self.tp(2, 0))

    def _prey_alive(self) -> Enemy | None:
        p = self.prey
        return p if p is not None and p.alive and p.has_mod(PREY) else None

    def _on_kill(self, ev: E.Ev) -> None:
        if ev.target is self.prey:
            self._dispel()

    def _e2(self, ev: E.Ev) -> None:
        hit = ev.hit
        if hit.attacker.side == Side.ALLY and hit.target is self._prey_alive():
            hit.add(S.CRIT_DMG, self.ep(2, 0))

    # -------------------------------------------------------------- talent
    def _talent(self, ev: E.Ev) -> None:
        act = ev.attack
        prey = self._prey_alive()
        if prey is None or act.owner is None or act.owner.side != Side.ALLY or prey not in act.attacked:
            return
        self.battle.additional_damage(
            self.char, prey, self.p("talent", 0), element=Element.LIGHTNING, label="Cascading Featherblade"
        )
        if self.e(1):
            self.battle.gain_energy(self.char, self.ep(1, 0))
        if act is self.fua_action or self.pending_dispel:
            return  # the Talent's Follow-Up ATK does not consume Charge
        self.charge -= 1
        self.consumed += 1
        fua = self.consumed >= int(self.p("talent", 1))
        if fua:
            self.consumed = 0
        if self.charge <= 0:
            if fua:  # the last Follow-Up still hits Prey; Prey is dispelled after it (ability script order)
                self.pending_dispel = True
            else:
                self._dispel()
        if fua:
            self.battle.queue_action(lambda: self._fua(prey), self.char, "Moze follow-up")

    def _fua(self, target: Enemy) -> None:
        t = target if target.alive and target.hp > 0 else self._random_enemy()
        if t is not None:
            mult = self.p("talent", 2) + (self.ep(6, 0) if self.e(6) else 0.0)
            with self.action(ActionKind.FUA, "talent", t) as act:
                self.fua_action = act
                act.hit(t, mult, toughness=self.toughness("talent"))
            self.fua_action = None
            if self.trace(1) and self.battle.turns >= self.a2_turn + 1 + int(self.tp(1, 1)):
                # approximation: the 1-turn cooldown counts any unit's turn (Moze is off the action order)
                self.a2_turn = self.battle.turns
                self.battle.gain_sp(int(self.tp(1, 0)), self.char)
        if self.pending_dispel:
            self._dispel()

    def _random_enemy(self) -> Enemy | None:
        pool = [e for e in self.enemies() if e.hp > 0] or self.enemies()
        return self.battle.rng.choice(pool) if pool else None

    # -------------------------------------------------------------- policy
    def can_skill(self) -> bool:
        return super().can_skill() and bool(self.teammates()) and self._prey_alive() is None

    # ------------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        self.simple_basic(target)

    def skill(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.SKILL, "skill", target) as act:
            self._mark(target)
            act.hit(target, self.p("skill", 0), toughness=self.toughness("skill"), splits="data")
            self.charge += int(self.p("skill", 1))

    def ult(self, target: Enemy | None) -> None:
        prey = self._prey_alive()
        t = prey if prey is not None else target
        if t is None:
            return
        tags = (DmgTag.ULT, DmgTag.FUA) if self.trace(3) else (DmgTag.ULT,)
        with self.action(ActionKind.ULT, "ult", t, tags=tags) as act:
            if self.e(4):
                self.buff_self(Modifier("Heathprowler", stats={S.DMG_PCT: self.ep(4, 0)}, duration=int(self.ep(4, 1))))
            act.hit(t, self.p("ult", 0), toughness=self.toughness("ult"))
        self._fua(t)
