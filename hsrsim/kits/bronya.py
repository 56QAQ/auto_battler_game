"""Bronya (布洛妮娅) — Harmony / Wind. Full action advance + DMG buff; team ATK/CRIT DMG ultimate."""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..entities import Character, Enemy
from ..enums import ActionKind
from ..modifiers import Modifier, Tick
from . import register
from .base import Kit


@register
class Bronya(Kit):
    char_id = "1101"
    default_opts = {"target": None}

    def setup(self) -> None:
        self.e1_ready = True
        if self.trace(3):
            self.passive("Military Might", {S.DMG_PCT: self.tp(3, 0)}, scope=self.ally_scope)
        if self.e(4):
            self.state["e4_used_turn"] = -1
            self.on(E.ACTION_END, self._e4)
        self.on(E.TURN_START, self._turn_start)

    def on_battle_start(self) -> None:
        if self.trace(2):
            for c in self.allies():
                self.buff(c, Modifier("Battlefield", stats={S.DEF_PCT: self.tp(2, 1)}, duration=int(self.tp(2, 0))))

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        for c in self.allies():
            self.buff(c, Modifier("Bronya Technique", stats={S.ATK_PCT: p[0]}, duration=int(p[1])))

    def _turn_start(self, ev: E.Ev) -> None:
        if ev.entity is self.char:
            self.e1_ready = True

    # ---------------------------------------------------------- policy
    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        if self.opts.get("rotation", "skill") == "skill" and self.can_skill():
            self.skill(target)
        else:
            self.basic(target)

    # ---------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.BASIC, "basic", target) as act:
            extra = {S.CRIT_RATE: 1.0} if self.trace(1) else None
            act.hit(target, self.p("basic", 0), toughness=self.toughness("basic"), extra=extra)
        self.battle.advance(self.char, self.p("talent", 0))

    def skill(self, target: Enemy | None) -> None:
        ally = self.main_dps()
        with self.action(ActionKind.SKILL, "skill", ally):
            # dispel one debuff
            for m in ally.debuffs[:1]:
                if m.dispellable:
                    self.battle.remove_modifier(m)
            dur = int(self.p("skill", 2)) + (int(self.ep(6, 0)) if self.e(6) else 0)
            self.buff(ally, Modifier("Combat Redeployment", stats={S.DMG_PCT: self.p("skill", 0)}, duration=dur))
            if self.e(1) and self.e1_ready and self.battle.rng.random() < self.ep(1, 0):
                self.e1_ready = False
                self.battle.gain_sp(1, self.char)
            if self.e(2) and ally is not self.char:
                self._e2(ally)
        if ally is not self.char:
            self.battle.advance(ally, 1.0)

    def _e2(self, ally: Character) -> None:
        def after_action(ev: E.Ev) -> None:
            if ev.action.actor is ally:
                self.buff(ally, Modifier("Quick March", stats={S.SPD_PCT: self.ep(2, 0)}, duration=1))
                self.battle.events.off_owner(token)

        token = Modifier("Quick March (pending)")
        self.battle.events.on(E.ACTION_END, after_action, owner=token)

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult"):
            cd = self.p("ult", 1) * self.char.stat(S.CRIT_DMG) + self.p("ult", 2)  # snapshot at cast
            for c in self.allies():
                self.buff(
                    c,
                    Modifier(
                        "Belobog March",
                        stats={S.ATK_PCT: self.p("ult", 0), S.CRIT_DMG: cd},
                        duration=int(self.p("ult", 3)),
                        tick=Tick.HOLDER_TURN_END,
                        skip_first_tick=False,  # LifeStepImmediately: the current turn counts
                    ),
                )

    def _e4(self, ev: E.Ev) -> None:
        act = ev.action
        if act.kind != ActionKind.BASIC or act.owner is self.char or not isinstance(act.owner, Character):
            return
        targets = [t for t in act.attacked if t.alive and t.is_weak_to(self.char.element)]
        if not targets or self.state["e4_used_turn"] == self.battle.turns:
            return
        self.state["e4_used_turn"] = self.battle.turns
        t = targets[0]

        def fua() -> None:
            if not t.alive:
                return
            with self.action(ActionKind.FUA, "basic", t, label="E4 Follow-up", energy=0, sp=0) as a:
                a.hit(t, self.p("basic", 0) * self.ep(4, 0), toughness=self.toughness("basic"))

        self.battle.queue_action(fua, self.char, "Bronya E4")
