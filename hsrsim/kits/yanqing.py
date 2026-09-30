"""Yanqing (彦卿) — Hunt / Ice. "Soulsteel Sync" (CRIT buffs, follow-up chance with Freeze) from the Skill,
lost when he takes DMG; CRIT Ultimate.

Options (``default_opts``):

* ``rotation``: ``"skill"`` (default, Skill whenever SP allows) or ``"basic"``.
* ``ult_with_sync``: only cast the Ultimate while Soulsteel Sync is active (default True).
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..battle import Action, Battle
from ..entities import Enemy
from ..enums import ActionKind, Element
from ..modifiers import DotModifier, Modifier
from . import register
from .base import Kit

SYNC = "Soulsteel Sync"
SYNC_TURNS = 1  # Skill: "activates Soulsteel Sync for 1 turn" (literal)
ULT_BUFF = "Amidst the Raining Bliss"
ULT_BUFF_TURNS = 1  # Ultimate: "This buff lasts for one turn" (literal)
FREEZE_TURNS = 1  # Talent: "Freeze the enemy for 1 turn" (literal)
E6_EXTEND = 1  # E6: "the duration of these buffs is extended by 1 turn" (literal)
TECHNIQUE_BUFF = "The One True Sword"


class YanqingFrozen(DotModifier):
    """Freeze from the Talent's follow-up: the target skips its turn and takes Ice Additional DMG at turn start."""

    def __init__(self, kit: Yanqing, target: Enemy) -> None:
        mult = kit.p("talent", 4)
        yanqing = kit.char

        def dmg(mod: DotModifier, b: Battle, ratio: float) -> float:
            hit = b.additional_damage(yanqing, target, mult * ratio, element=Element.ICE, label="Frozen (Yanqing)")
            return hit.damage

        super().__init__(
            "Frozen (Yanqing)",
            dot_type="freeze",
            damage_fn=dmg,
            duration=FREEZE_TURNS,
            is_dot=False,
            skip_turn=True,
            tags={"cc"},
        )


@register
class Yanqing(Kit):
    char_id = "1209"
    default_opts = {"rotation": "skill", "ult_with_sync": True}

    def setup(self) -> None:
        self.on(E.ATTACK_END, self._after_attack)
        self.on(E.HP_CHANGED, self._on_hp_changed)
        self.on(E.BEFORE_HIT, self._before_hit)
        if self.e(6):
            self.on(E.KILL, self._e6)

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]  # [HP ratio, DMG%, turns]
        self.buff_self(Modifier(TECHNIQUE_BUFF, duration=int(p[2])))

    # -------------------------------------------------------------- states
    def _sync(self) -> None:
        stats = {S.CRIT_RATE: self.p("talent", 0), S.CRIT_DMG: self.p("talent", 1)}
        if self.trace(2):
            stats[S.EFFECT_RES] = self.tp(2, 0)
        if self.e(2):
            stats[S.ERR] = self.ep(2, 0)
        # not modelled: Soulsteel Sync's lower chance of being attacked (no value in the data)
        self.buff_self(Modifier(SYNC, stats=stats, duration=SYNC_TURNS))

    def _on_hp_changed(self, ev: E.Ev) -> None:
        if ev.entity is self.char and ev.delta < 0 and isinstance(ev.source, Enemy):
            self.battle.remove_named(self.char, SYNC)

    def _before_hit(self, ev: E.Ev) -> None:
        hit = ev.hit
        if hit.attacker is not self.char:
            return
        if self.e(4) and self.char.hp_ratio >= self.ep(4, 0):
            hit.add(f"{S.RES_PEN}:{Element.ICE.value}", self.ep(4, 1))
        if self.char.has_mod(TECHNIQUE_BUFF):
            p = self.sk("technique")["params"][0]
            if hit.target.hp_ratio >= p[0]:
                hit.add(S.DMG_PCT, p[1])

    def _e6(self, ev: E.Ev) -> None:
        for name in (SYNC, ULT_BUFF):
            m = self.char.get_mod(name)
            if m is not None and m.duration is not None:
                m.duration += E6_EXTEND

    # -------------------------------------------------------------- policy
    def want_ult(self) -> bool:
        if not super().want_ult():
            return False
        return self.char.has_mod(SYNC) or not self.opts.get("ult_with_sync", True)

    # ------------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        self.simple_basic(target)

    def skill(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.SKILL, "skill", target) as act:
            # approximation: Soulsteel Sync is activated before the Skill's DMG (the Skill benefits from it)
            self._sync()
            act.hit(target, self.p("skill", 0), toughness=self.toughness("skill"), splits="data")

    def ult(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.ULT, "ult", target) as act:
            stats = {S.CRIT_RATE: self.p("ult", 0)}
            if self.char.has_mod(SYNC):
                stats[S.CRIT_DMG] = self.p("ult", 1)
            self.buff_self(Modifier(ULT_BUFF, stats=stats, duration=ULT_BUFF_TURNS))
            act.hit(target, self.p("ult", 2), toughness=self.toughness("ult"), splits="data")

    # -------------------------------------------------------------- talent
    def _crit_landed(self, act: Action) -> bool:
        if self.battle.cfg.crit_mode == "random":
            return any(h.crit for h in act.hits)
        # approximation (expected-CRIT mode): roll each hit's CRIT Rate once to decide whether a CRIT landed
        rng = self.battle.rng
        return any(rng.random() < h.attacker.stat_q(S.CRIT_RATE, h.quals, h.extra) for h in act.hits)

    def _after_attack(self, ev: E.Ev) -> None:
        act = ev.attack
        if act.owner is not self.char or not act.attacked:
            return
        target = act.target if isinstance(act.target, Enemy) and act.target in act.attacked else act.attacked[0]
        if self.trace(1):
            for t in act.attacked:
                if t.alive and t.is_weak_to(Element.ICE):
                    self.battle.additional_damage(
                        self.char, t, self.tp(1, 0), element=Element.ICE, label="Icing on the Kick"
                    )
        if self.e(1):
            for t in act.attacked:
                if t.alive and t.has_tag("freeze"):
                    self.battle.additional_damage(
                        self.char, t, self.ep(1, 0), element=Element.ICE, label="E1 Svelte Saber"
                    )
        if self.trace(3) and self._crit_landed(act):
            self.buff_self(Modifier("Gentle Blade", stats={S.SPD_PCT: self.tp(3, 0)}, duration=int(self.tp(3, 1))))
        can_fua = act.kind in (ActionKind.BASIC, ActionKind.SKILL, ActionKind.ULT) and self.char.has_mod(SYNC)
        if can_fua and self.battle.rng.random() < self.p("talent", 2):  # fixed chance
            self._queue_fua(target)

    def _queue_fua(self, target: Enemy) -> None:
        def fua() -> None:
            t = target if target.alive and target.hp > 0 else self.battle.default_target()
            if t is None:
                return
            with self.action(ActionKind.FUA, "talent", t, label="One With the Sword") as act:
                act.hit(t, self.p("talent", 3), toughness=self.toughness("talent"))
                if t.alive and t.hp > 0:
                    self.battle.try_debuff(
                        YanqingFrozen(self, t), t, self.char, self.p("talent", 5), debuff_type="freeze"
                    )

        self.battle.queue_action(fua, self.char, "Yanqing follow-up")
