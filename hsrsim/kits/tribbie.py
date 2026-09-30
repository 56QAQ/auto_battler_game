"""Tribbie (缇宝) — Harmony / Quantum. Numinosity (team RES PEN), vulnerability Zone with Additional DMG,
follow-up attacks after allies' Ultimates. Max HP scaling.

Options (``default_opts``):
  * ``rotation``: ``"auto"`` (Skill only when Numinosity is missing, else Basic ATK), ``"skill"`` (Skill whenever
    SP allows) or ``"basic"``.
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..control import ALLIES, MenuItem
from ..entities import Character, Enemy, Entity
from ..enums import ActionKind, DmgTag, Element, Side
from ..modifiers import Modifier, Stacking, Tick
from . import register
from .base import Kit


@register
class Tribbie(Kit):
    char_id = "1403"
    default_opts = {"rotation": "auto"}

    def setup(self) -> None:
        self.zone: Modifier | None = None
        self.fua_used: set[int] = set()  # characters whose Ultimate already triggered the Talent
        self.on(E.ACTION_END, self._on_ult_end)
        self.on(E.ATTACK_END, self._on_attack_end)
        if self.trace(2):
            self.passive("Glass Ball with Wings!", {}, dyn=self._a4_hp, dyn_keys={S.HP_FLAT})

    def on_battle_start(self) -> None:
        if self.trace(3):
            self.battle.gain_energy(self.char, self.tp(3, 0))

    def technique(self) -> None:
        self._numinosity(int(self.sk("technique")["params"][0][0]))

    # ----------------------------------------------------------- states
    @property
    def zone_active(self) -> bool:
        return self.zone is not None and not self.zone.removed

    def _numinosity(self, turns: int) -> None:
        stats = {S.RES_PEN: self.p("skill", 0)}
        if self.e(4):
            stats[S.DEF_IGNORE] = self.ep(4, 0)
        self.buff_self(
            Modifier(
                "Numinosity",
                stats=stats,
                duration=turns,
                tick=Tick.SOURCE_TURN_START,
                scope=self.ally_scope,
                key="Numinosity",
            )
        )

    def _a4_hp(self, mod: Modifier, key: str, ent: Entity) -> float:
        if not self.zone_active:
            return 0.0
        return self.tp(2, 0) * sum(c.max_hp for c in self.battle.team if c.alive)

    # ----------------------------------------------------------- policy
    def menu(self) -> list[MenuItem]:
        """The Skill (Numinosity) buffs the whole team."""
        return [self.basic_item(), self.skill_item(target=ALLIES)]

    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        policy = self.opts.get("rotation", "auto")
        want = policy == "skill" or (policy == "auto" and not self.char.has_mod("Numinosity"))
        if want and self.can_skill():
            self.skill(target)
        else:
            self.basic(target)

    # ---------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.BASIC, "basic", target) as act:
            act.blast(
                target,
                self.p("basic", 0),
                self.p("basic", 1),
                stat="hp",
                toughness=(self.toughness("basic", 0), self.toughness("basic", 2)),
            )

    def skill(self, target: Enemy | None) -> None:
        with self.action(ActionKind.SKILL, "skill"):
            self._numinosity(int(self.p("skill", 1)))

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult", target) as act:
            self.zone = self.buff_self(
                Modifier(
                    "Tribbie Zone",
                    stats={S.VULN: self.p("ult", 1)},
                    duration=int(self.p("ult", 3)),
                    tick=Tick.SOURCE_TURN_START,
                    scope=self.enemy_scope,
                    key="Tribbie Zone",
                )
            )
            act.aoe(self.p("ult", 0), stat="hp", toughness=self.toughness("ult", 1), main_target=target)
        self.fua_used.clear()
        if self.e(6):
            self._queue_fua()

    # ----------------------------------------------------------- talent
    def _on_ult_end(self, ev: E.Ev) -> None:
        act = ev.action
        owner = act.owner
        if act.kind != ActionKind.ULT or owner is self.char or not isinstance(owner, Character):
            return
        if owner.side != Side.ALLY or owner.uid in self.fua_used:
            return
        self.fua_used.add(owner.uid)
        self._queue_fua()

    def _queue_fua(self) -> None:
        def fua() -> None:
            if not self.enemies():
                return
            extra = {S.DMG_PCT: self.ep(6, 0)} if self.e(6) else None
            with self.action(ActionKind.FUA, "talent", self.battle.default_target()) as act:
                act.aoe(self.p("talent", 0), stat="hp", toughness=self.toughness("talent", 1), extra=extra)
            if self.trace(1):
                self.buff_self(
                    Modifier(
                        "Lamb Outside the Wall...",
                        stats={S.DMG_PCT: self.tp(1, 0)},
                        duration=int(self.tp(1, 2)),
                        stacking=Stacking.STACK,
                        max_stacks=int(self.tp(1, 1)),
                    )
                )

        # "If the target was defeated before the Follow-Up ATK is launched, then launches the Follow-Up ATK
        # against new enemy targets entering the battlefield": the queued action survives wave changes
        self.battle.queue_action(fua, self.char, "Tribbie follow-up", needs_enemies=False)

    def _on_attack_end(self, ev: E.Ev) -> None:
        act = ev.attack
        owner = act.owner
        if owner is None or owner.side != Side.ALLY or not act.attacked:
            return
        n = len(act.attacked)
        if self.trace(3) and owner is not self.char:
            self.battle.gain_energy(self.char, self.tp(3, 1) * n)
        if not self.zone_active:
            return
        hit_targets = [t for t in act.attacked if t.alive]
        if not hit_targets:
            return
        target = max(hit_targets, key=lambda e: e.hp)
        mult = self.p("ult", 2) * (self.ep(2, 0) if self.e(2) else 1.0)
        per = 1 + (int(self.ep(2, 1)) if self.e(2) else 0)
        for _ in range(n * per):
            self.battle.additional_damage(
                self.char,
                target,
                mult,
                stat="hp",
                element=Element.QUANTUM,
                label="Tribbie Zone Additional DMG",
                tags=(DmgTag.ADDITIONAL,),
            )
        if self.e(1):
            total = sum(h.damage for h in act.hits)
            if total > 0:
                self.battle.true_damage(total, self.ep(1, 0), target, self.char, "Rite of Sugar Scoop (Tribbie E1)")
