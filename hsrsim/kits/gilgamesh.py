"""Gilgamesh — Destruction / Lightning. "Interest" (SPD per point) from allies taking action and Ultimates; auto
Basic ATK until "Interest Piqued!" (10 Interest for the first time), Skill only afterwards; "King's
Acknowledgement" DEF ignore; attack-tally Joint Follow-Up ATK with Saber.

Policy: fixed by the kit — Basic ATK before "Interest Piqued!", Skill afterwards. Ultimate whenever ready.
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..control import MenuItem
from ..entities import Character, Enemy, Entity
from ..enums import ActionKind, DmgTag, Side
from ..modifiers import Modifier
from . import register
from .base import Kit

JOINT_ID = "150905"  # Talent "I Grant You Permission To Strike" (Joint Follow-Up ATK with Saber)
SABER_ID = "1014"
SABER_ULT_BUFF = "I Grant You Permission To Strike (Saber Ultimate)"


@register
class Gilgamesh(Kit):
    char_id = "1509"

    def setup(self) -> None:
        self.interest = 0
        self.interest_gained = 0
        self.piqued = False
        self.tally = 0
        self.joint_pending = False
        self.joints = 0
        self.golden_rule = 0
        self.passive("Interest", {}, dyn=lambda m, k, e: self.p("talent", 3) * self.interest, dyn_keys={S.SPD_PCT})
        if self.trace(2):
            self.passive(
                "Hero's Hauteur",
                {},
                dyn=lambda m, k, e: self.tp(2, 0) * min(self.interest_gained, int(self.tp(2, 1))),
                dyn_keys={S.CRIT_DMG},
            )
        if self.trace(3):
            self.passive(
                "Hegemon's Strife",
                {},
                scope=self.ally_scope,
                key="Gilgamesh A6",
                dyn=self._a6,
                dyn_keys={S.ATK_PCT, S.CRIT_DMG},
            )
        if self.e(4):
            self.passive("King Who Bowed to None", {S.ERR: self.ep(4, 0)})
        if self.e(6):
            self.passive("Soul That Bore Friendship", {S.RES_PEN: self.ep(6, 1)}, scope=self.ally_scope, key="Gil E6")
        self.on(E.TURN_START, self._on_turn_start)
        self.on(E.ULT_USED, self._on_ult_used)
        self.on(E.ATTACK_END, self._on_attack_end)
        self.on(E.ACTION_END, self._on_action_end)

    def on_battle_start(self) -> None:
        if self.e(2):
            self.gain_interest(int(self.ep(2, 0)))

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        with self.action(ActionKind.EXTRA, None, label="Gilgamesh Technique", energy=0, sp=0) as act:
            act.aoe(p[1])
        self.gain_interest(int(p[2]))

    # ------------------------------------------------------------ helpers
    def _saber(self) -> Character | None:
        return next((c for c in self.battle.team if c.char_id == SABER_ID and c.alive), None)

    def _a6(self, mod: Modifier, key: str, ent: Entity) -> float:
        base = self.tp(3, 0) if key == S.ATK_PCT else self.tp(3, 1)
        max_energy = float(getattr(ent, "max_energy", 0.0) or 0.0)
        return base + min(self.tp(3, 4), max(0.0, max_energy - self.tp(3, 2)) * self.tp(3, 3))

    def gain_interest(self, n: int) -> None:
        if n <= 0:
            return
        self.interest += n
        self.interest_gained += n
        if not self.piqued and self.interest >= int(self.p("talent", 1)):
            self.piqued = True
            self.battle.log(f"{self.char.name}: Interest Piqued!")

    # ------------------------------------------------------------- talent
    def _on_turn_start(self, ev: E.Ev) -> None:
        ent = ev.entity
        if ent is not self.char and ent.side == Side.ALLY and ent.targetable:
            self.gain_interest(1)  # "when another ally target takes action, gains 1 point of Interest" (literal)

    def _on_ult_used(self, ev: E.Ev) -> None:
        who = ev.entity
        if not isinstance(who, Character) or who is self.char:
            return
        self.buff_self(
            Modifier(
                "King's Burden",
                stats={f"{S.DMG_PCT}:{DmgTag.ULT}": self.p("talent", 2)},
                duration=int(self.p("talent", 0)),
            )
        )
        if self.trace(1):
            self.gain_interest(int(self.tp(1, 0)))
            spent = float(getattr(ev, "energy", 0.0) or 0.0)
            if spent > 0:
                self.battle.gain_energy(self.char, spent * self.tp(1, 1), fixed=True)
        if self.e(6):
            self.golden_rule = min(int(self.ep(6, 2)), self.golden_rule + 1)  # "gains 1 point" (literal)

    def _on_attack_end(self, ev: E.Ev) -> None:
        act = ev.attack
        saber = self._saber()
        if not act.data.get("joint_with") and (act.owner is self.char or (saber is not None and act.owner is saber)):
            self.tally += 1  # "the attack tally increases by 1" (literal)
        if saber is None or self.joint_pending or not self.char.alive:
            return
        rec = self.sk(JOINT_ID)
        if self.tally >= int(rec["params"][self.level_of(rec) - 1][4]):
            self.joint_pending = True
            self.battle.queue_action(self.joint_follow_up, self.char, "Joint Follow-Up ATK (Gilgamesh & Saber)")

    def _on_action_end(self, ev: E.Ev) -> None:
        act = ev.action
        if act.kind == ActionKind.ULT and isinstance(act.owner, Character) and act.owner.has_mod(SABER_ULT_BUFF):
            self.battle.remove_named(act.owner, SABER_ULT_BUFF)

    def joint_follow_up(self) -> None:
        self.joint_pending = False
        saber = self._saber()
        if saber is None or not self.enemies():
            return
        rec = self.sk(JOINT_ID)
        lv = rec["params"][self.level_of(rec) - 1]
        target = self.pick_target()
        self.tally = 0
        self.joints += 1
        with self.action(ActionKind.FUA, rec, target) as act:
            act.data["joint_with"] = (self.char, saber)
            act.aoe(lv[0], toughness=rec["toughness"][1], main_target=target)
        if self.enemies():
            # approximation: Saber's share is her own Follow-Up action (no Energy/Toughness data for it)
            with self.battle.action(
                saber, ActionKind.FUA, target=target, label=f"{rec['name']} (Saber)", energy=0, sp=0
            ) as act2:
                act2.data["joint_with"] = (self.char, saber)
                act2.aoe(lv[1], main_target=target)
        self.gain_interest(int(lv[2]))
        self.battle.gain_energy(saber, lv[3], fixed=True)
        self.battle.apply(
            Modifier(SABER_ULT_BUFF, stats={f"{S.FINAL_DMG}:{DmgTag.ULT}": lv[5] - 1.0}, dispellable=False),
            saber,
            self.char,
        )

    # --------------------------------------------------------------- policy
    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        if self.piqued:
            self.skill(target)
        else:
            self.basic(target)  # "automatically uses Basic ATK at the start of this unit's turn"

    def menu(self) -> list[MenuItem]:
        """Basic ATK only (used automatically in the game) until "Interest Piqued!", Skill only afterwards."""
        if self.piqued:
            return [self.basic_item(enabled=False, note="【来兴致了！】状态下仅能施放战技"), self.skill_item()]
        return [self.basic_item(note="自动施放"), self.skill_item(enabled=False, note="尚未进入【来兴致了！】状态")]

    # -------------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        # not modelled: 150909 (a Skill-slot copy of Halfhearted Blow) is never used: the kit auto-uses Basic ATK
        self.simple_basic(target)

    def skill(self, target: Enemy | None) -> None:
        assert target is not None
        ka = {S.DEF_IGNORE: self.p("skill", 4)}
        if self.e(1):
            ka[S.ATK_PCT] = self.ep(1, 0)
        dur = int(self.p("skill", 5))
        main, adj = self.p("skill", 0), self.p("skill", 1)
        if self.e(2):
            main += self.ep(2, 2)
            adj += self.ep(2, 3)
        with self.action(ActionKind.SKILL, "skill", target) as act:
            self.buff_self(Modifier("King's Acknowledgement", stats=ka, duration=dur))
            if self.e(1):
                self.buff_self(
                    Modifier(
                        "King's Acknowledgement (team)",
                        stats={S.DEF_IGNORE: self.p("skill", 4)},
                        duration=dur,
                        scope=self.teammate_scope,
                    )
                )
            act.blast(
                target,
                main,
                adj,
                toughness=(self.toughness("skill", 0), self.toughness("skill", 2)),
                splits="data",
            )
        self.interest = 0  # "after using Skill, clears this unit's Interest"
        if self.e(1):
            self.battle.gain_energy(self.char, self.ep(1, 1), fixed=True)

    def ult(self, target: Enemy | None) -> None:
        gr = self.golden_rule if self.e(6) else 0
        self.golden_rule = 0
        extra = {S.CRIT_DMG: gr * self.ep(6, 3)} if gr else None
        bounce = self.p("ult", 1) + (self.ep(6, 0) if self.e(6) else 0.0)
        with self.action(ActionKind.ULT, "ult", target) as act:
            act.aoe(self.p("ult", 0), toughness=self.toughness("ult", 1), main_target=target, extra=extra)
            act.bounce(None, int(self.p("ult", 2)), bounce, toughness=self.toughness("ult", 0), extra=extra)
        if self.trace(1):
            self.gain_interest(int(self.tp(1, 2)))
        if self.e(2):
            self.gain_interest(int(self.ep(2, 1)))
