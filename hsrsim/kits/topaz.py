"""Topaz & Numby (托帕&账账) — Hunt / Fire. Numby: a summon with its own SPD that launches Follow-Up ATKs
on the "Proof of Debt" target and is advanced by allies' Follow-Up ATKs; Windfall Bonanza! Ultimate.

Numby is a ``Summon`` in "owner" stat mode (its DMG uses Topaz's stats and is credited to her).

Options (``default_opts``):

* ``rotation``: ``"skill"`` (default, Skill whenever SP allows) or ``"basic"``.
* ``ult_in_windfall``: allow re-casting the Ultimate while Windfall Bonanza! is still active (default False).
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..entities import Character, Enemy, Summon
from ..enums import ActionKind, DmgTag, Element, Side
from ..modifiers import Modifier, ModKind, Stacking, Tick
from . import register
from .base import Kit

POD = "Proof of Debt"
DEBTOR = "Debtor"


@register
class Topaz(Kit):
    char_id = "1112"
    default_opts = {"rotation": "skill", "ult_in_windfall": False}

    def setup(self) -> None:
        self.numby: Summon | None = None
        self.windfall_left = 0
        self.technique_energy = 0.0
        self._debtor_action: object = None
        self.on(E.TURN_START, self._on_turn_start)
        self.on(E.ACTION_START, self._on_action_start)
        self.on(E.ATTACK_END, self._on_attack_end)
        self.on(E.MOD_REMOVED, self._on_mod_removed)
        if self.trace(2):
            self.on(E.BEFORE_HIT, self._a4)
        if self.e(1):
            self.on(E.BEFORE_HIT, self._e1_crit)
            self.on(E.AFTER_HIT, self._e1_debtor)

    def on_battle_start(self) -> None:
        self.numby = self.battle.add_unit(Summon("Numby", self.char, spd=self.p("talent", 0), on_turn=self._numby_turn))

    def technique(self) -> None:
        self.technique_energy = float(self.sk("technique")["params"][0][0])

    # ------------------------------------------------------ Proof of Debt
    def _pod_target(self) -> Enemy | None:
        return next((e for e in self.enemies() if e.hp > 0 and e.has_mod(POD)), None)

    def _set_pod(self, target: Enemy) -> None:
        for e in self.battle.enemies:
            if e is not target:
                self.battle.remove_named(e, POD)
        self.battle.apply(
            Modifier(
                POD,
                stats={f"{S.VULN}:{DmgTag.FUA}": self.p("skill", 1)},
                kind=ModKind.DEBUFF,
                tick=Tick.NONE,
                key=POD,
            ),
            target,
            self.char,
        )

    def _ensure_pod(self) -> Enemy | None:
        t = self._pod_target()
        if t is not None:
            return t
        cands = [e for e in self.enemies() if e.hp > 0]
        if not cands:
            return None
        t = self.battle.rng.choice(cands)
        self._set_pod(t)
        return t

    def _on_turn_start(self, ev: E.Ev) -> None:
        if isinstance(ev.entity, Character):
            self._ensure_pod()

    def _on_action_start(self, ev: E.Ev) -> None:
        owner = ev.action.owner
        if owner is not None and owner.side == Side.ALLY:
            self._ensure_pod()

    def _on_mod_removed(self, ev: E.Ev) -> None:
        if ev.mod.name == POD:
            self.battle.remove_named(ev.target, DEBTOR)

    # --------------------------------------------------------------- Numby
    @property
    def in_windfall(self) -> bool:
        return self.windfall_left > 0

    def _numby_extra(self, windfall: bool) -> dict[str, float]:
        extra: dict[str, float] = {}
        if windfall:
            extra[S.CRIT_DMG] = self.p("ult", 1)
        if self.e(6):
            extra[f"{S.RES_PEN}:{Element.FIRE.value}"] = self.ep(6, 1)
        return extra

    def _after_numby_attack(self, windfall: bool) -> None:
        if windfall:
            self.windfall_left -= 1
            if self.trace(3):
                self.battle.gain_energy(self.char, self.tp(3, 0))
        if self.technique_energy:
            self.battle.gain_energy(self.char, self.technique_energy, fixed=True)
            self.technique_energy = 0.0

    def _numby_turn(self, unit: Summon, battle: object) -> None:
        if self.e(4):
            self.battle.advance(self.char, self.ep(4, 0))
        t = self._ensure_pod()
        if t is None:
            return
        windfall = self.in_windfall
        mult = self.p("talent", 1) + (self.p("ult", 0) if windfall else 0.0)
        with self.battle.action(
            unit, ActionKind.FUA, skill=self.sk("talent"), target=t, label="Numby", energy=0, sp=0
        ) as act:
            act.hit(t, mult, toughness=self.toughness("talent"), extra=self._numby_extra(windfall))
        self._after_numby_attack(windfall)
        if self.e(2):
            self.battle.gain_energy(self.char, self.ep(2, 0))

    # ------------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        tags = (DmgTag.BASIC, DmgTag.FUA) if self.trace(1) else (DmgTag.BASIC,)
        with self.action(ActionKind.BASIC, "basic", target, tags=tags) as act:
            act.hit(target, self.p("basic", 0), toughness=self.toughness("basic"))

    def skill(self, target: Enemy | None) -> None:
        assert target is not None
        # approximation: during Windfall Bonanza! the Skill (dealt by Numby) is enhanced and uses up one of
        # Numby's Windfall attacks
        windfall = self.in_windfall
        mult = self.p("skill", 0) + (self.p("ult", 0) if windfall else 0.0)
        with self.action(ActionKind.SKILL, "skill", target, tags=(DmgTag.SKILL, DmgTag.FUA)) as act:
            self._set_pod(target)
            act.hit(target, mult, toughness=self.toughness("skill"), extra=self._numby_extra(windfall))
        self._after_numby_attack(windfall)

    def want_ult(self) -> bool:
        return super().want_ult() and (not self.in_windfall or bool(self.opts.get("ult_in_windfall")))

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult"):
            self.windfall_left = int(self.p("ult", 3)) + (int(self.ep(6, 0)) if self.e(6) else 0)

    # -------------------------------------------------------------- talent
    def _on_attack_end(self, ev: E.Ev) -> None:
        act = ev.attack
        numby = self.numby
        if numby is None or not numby.alive or act.owner is None or act.owner.side != Side.ALLY:
            return
        if self.battle.current_turn is numby:  # "cannot be triggered during Numby's own turn"
            return
        pod_hits = [h for h in act.hits if h.target.has_mod(POD)]
        if not pod_hits:
            return
        if any(DmgTag.FUA in h.tags for h in pod_hits):
            self.battle.advance(numby, self.p("talent", 2))
        if self.in_windfall and act.kind in (ActionKind.BASIC, ActionKind.SKILL, ActionKind.ULT):
            self.battle.advance(numby, self.p("ult", 2))

    def _a4(self, ev: E.Ev) -> None:
        hit = ev.hit
        if hit.credited is self.char and hit.target.is_weak_to(Element.FIRE):
            hit.add(S.DMG_PCT, self.tp(2, 0))

    def _e1_crit(self, ev: E.Ev) -> None:
        hit = ev.hit
        if DmgTag.FUA not in hit.tags:
            return
        debtor = hit.target.get_mod(DEBTOR)
        if debtor is not None:
            hit.add(S.CRIT_DMG, self.ep(1, 0) * debtor.stacks)

    def _e1_debtor(self, ev: E.Ev) -> None:
        # approximation: Debtor is applied after the first FUA hit on the Proof of Debt target, so it
        # benefits the following attacks
        hit = ev.hit
        act = hit.action
        if act is None or DmgTag.FUA not in hit.tags or not hit.target.has_mod(POD):
            return
        if act is self._debtor_action:  # "only once within a single attack"
            return
        self._debtor_action = act
        self.battle.apply(
            Modifier(
                DEBTOR,
                kind=ModKind.DEBUFF,
                tick=Tick.NONE,
                stacking=Stacking.STACK,
                max_stacks=int(self.ep(1, 1)),
                key=DEBTOR,
            ),
            hit.target,
            self.char,
        )
