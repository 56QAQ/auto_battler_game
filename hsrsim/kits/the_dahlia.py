"""The Dahlia (大丽花) — Nihility / Fire. Dance Partners: Super Break conversion, follow-up bounces,
Wilt (DEF shred + Weakness implant) and a Break Efficiency zone.

Options: ``partner``: name of her Dance Partner (default: the teammate with the highest Break Effect
at battle start); ``rotation``: "skill" (default: Skill when the Zone is missing) | "basic".
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..battle import Action
from ..entities import Character, Enemy, Entity
from ..enums import ActionKind, Element, Side
from ..modifiers import Modifier, ModKind, Tick
from . import register
from .base import Kit

ZONE = "Lick... Enkindled Betrayal (Zone)"
WILT = "Wilt"
# A4 "Lament, Lost Soul": "recovers 1 Skill Point" (literal in the trace text, not a trace parameter)
A4_SP = 1


@register
class TheDahlia(Kit):
    char_id = "1321"
    default_opts = {"partner": None}

    def setup(self) -> None:
        self.zone: Modifier | None = None
        self.partner: Character | None = None
        self.fua_turn = -1
        self.fua_count = 0
        self.a2_turn = -1
        self.e1_done: set[int] = set()
        self.a6_spd_turn = -1
        self._pick_partner()
        self.on(E.ATTACK_END, self._on_attack_end)
        if self.trace(1):
            self.on(E.HEALED, self._a2_heal)
            self.on(E.MOD_APPLIED, self._a2_shield)
        if self.trace(3):
            self.on(E.MOD_APPLIED, self._a6_implant)
        if self.e(2):
            self.passive("Fresh, Ethereal, and Beloved", {S.RES_REDUCTION: self.ep(2, 0)}, scope=self.enemy_scope)
            self.on(E.ENEMY_SPAWNED, lambda ev: self._wilt(ev.enemy, int(self.ep(2, 1))))
        if self.e(6):
            self.passive(
                "And Yet, Always, Deathly Beautiful",
                {},
                scope=self.ally_scope,
                dyn=lambda m, k, e: self.ep(6, 0) if e in self.dance_partners() else 0.0,
                dyn_keys={S.BREAK_EFFECT},
            )

    def on_battle_start(self) -> None:
        self.battle.gain_energy(self.char, self.p("talent", 3), fixed=True)
        if self.trace(1):
            self._a2(int(self.tp(1, 1)))

    def technique(self) -> None:
        # not modelled: the combat-triggering Toughness Reduction converted into Super Break DMG
        self._deploy_zone()

    # -------------------------------------------------------- Dance Partners
    def _pick_partner(self) -> None:
        name = self.opts.get("partner")
        if name:
            self.partner = self.battle.character(name)
            return
        mates = self.teammates()
        self.partner = max(mates, key=lambda c: c.stat(S.BREAK_EFFECT)) if mates else None

    def dance_partners(self) -> list[Entity]:
        if self.partner is None or not self.partner.alive:
            self._pick_partner()
        out: list[Entity] = [self.char]
        if self.partner is not None and self.partner.alive:
            out.append(self.partner)
        return out

    # ---------------------------------------------------------------- Zone
    @property
    def zone_active(self) -> bool:
        return self.zone is not None and not self.zone.removed

    def _deploy_zone(self) -> None:
        self.zone = self.buff_self(
            Modifier(
                ZONE,
                stats={S.BREAK_EFF: self.p("skill", 2)},
                duration=int(self.p("skill", 1)),
                tick=Tick.SOURCE_TURN_START,
                scope=self.ally_scope,
                key=ZONE,
            )
        )

    def _convertible(self, act: Action, t: Enemy) -> float:
        """Toughness Reduction of ``act`` on ``t`` that can become Super Break DMG."""
        if self.zone_active:  # the Zone also converts Toughness Reduction taken while not Weakness Broken
            return sum(h.toughness_potential for h in act.hits if h.target is t)
        return self.battle.super_break_toughness(act, t)

    # ---------------------------------------------------------------- Wilt
    def _wilt(self, e: Enemy, turns: int) -> None:
        if not e.alive:
            return
        els = {self.char.element} | {getattr(p, "element", self.char.element) for p in self.dance_partners()}
        self.battle.apply(
            Modifier(
                WILT,
                stats={S.DEF_REDUCTION: self.p("ult", 2)},
                duration=turns,
                kind=ModKind.DEBUFF,
                tags={f"weak:{Element(el).value}" for el in els},
                key=WILT,
            ),
            e,
            self.char,
        )

    # ----------------------------------------------------------- listeners
    def _on_attack_end(self, ev: E.Ev) -> None:
        act = ev.attack
        owner = act.owner
        if not isinstance(owner, Character) or owner.side != Side.ALLY or not act.attacked:
            return
        dps = self.dance_partners()
        is_dp = owner in dps
        if is_dp or self.e(1):
            mult = self.p("talent", 4) + (self.ep(1, 3) if self.e(1) and is_dp else 0.0)
            for t in act.attacked:
                tough = self._convertible(act, t)
                if tough > 0 and t.alive:
                    self.battle.super_break(
                        act.actor, t, tough, mult, credited=owner, label="Super Break (Dance Partner)"
                    )
        if self.e(1) and is_dp:
            for t in act.attacked:
                if t.alive and not t.broken and t.uid not in self.e1_done:
                    self.e1_done.add(t.uid)
                    amount = min(self.ep(1, 2), max(self.ep(1, 1), self.ep(1, 0) * t.max_toughness))
                    # approximation: this fixed Toughness Reduction is not converted into Super Break DMG
                    self.battle.reduce_toughness(
                        t, act.actor, amount, Element(getattr(act.actor, "element", Element.FIRE))
                    )
        if self.trace(3) and owner.element == Element.FIRE:
            implanted: list[Enemy] = act.data.get("dahlia_implanted", [])
            for t in implanted:
                if t.alive:
                    self.battle.reduce_toughness(t, act.actor, self.tp(3, 4), Element.FIRE)
            if implanted:
                me = self.char
                cap = self.tp(3, 0) * me.max_energy  # Energy can be raised to at most 50% of Max Energy
                gain = min(self.tp(3, 1) * me.max_energy, max(0.0, cap - me.energy))
                if gain > 0:
                    self.battle.gain_energy(me, gain, fixed=True)
        partner = self.partner
        if owner is partner and owner is not self.char and self.fua_turn != self.battle.turns:
            self.fua_turn = self.battle.turns
            first = act.target if isinstance(act.target, Enemy) else act.attacked[0]
            self.battle.queue_action(lambda: self._fua(first), self.char, "The Dahlia follow-up")

    def _a6_implant(self, ev: E.Ev) -> None:
        mod, target = ev.mod, ev.target
        if not isinstance(target, Enemy) or mod.source is None or mod.source.side != Side.ALLY:
            return
        if not any(t.startswith("weak:") for t in mod.tags):
            return
        if self.a6_spd_turn != self.battle.turns:
            self.a6_spd_turn = self.battle.turns
            self.buff_self(
                Modifier(
                    "Outgrow the Old, Espouse the New",
                    stats={S.SPD_PCT: self.tp(3, 2)},
                    duration=int(self.tp(3, 3)),
                )
            )
        act = self.battle.current_action
        if act is not None:
            lst: list[Enemy] = act.data.setdefault("dahlia_implanted", [])
            if target not in lst:
                lst.append(target)

    def _a2(self, turns: int) -> None:
        for c in self.teammates():
            self.buff(
                c,
                Modifier(
                    "Yet Another Funeral",
                    duration=turns,
                    dyn=lambda m, k, e: self.tp(1, 0) * self.char.stat(S.BREAK_EFFECT) + self.tp(1, 2),
                    dyn_keys={S.BREAK_EFFECT},
                ),
            )

    def _a2_retrigger(self, source: Entity | None) -> None:
        if source is None or source is self.char or source.side != Side.ALLY:
            return
        if self.a2_turn == self.battle.turns:
            return
        self.a2_turn = self.battle.turns
        self._a2(int(self.tp(1, 3)))

    def _a2_heal(self, ev: E.Ev) -> None:
        if ev.entity is self.char:
            self._a2_retrigger(ev.source)

    def _a2_shield(self, ev: E.Ev) -> None:
        if ev.target is self.char and "shield" in ev.mod.tags:
            self._a2_retrigger(ev.mod.source)

    # -------------------------------------------------------------- talent
    def _random_enemy(self) -> Enemy | None:
        pool = [e for e in self.enemies() if e.hp > 0] or self.enemies()
        return self.battle.rng.choice(pool) if pool else None

    def _fua(self, first: Enemy | None) -> None:
        n = int(self.p("talent", 1)) + (int(self.ep(4, 2)) if self.e(4) else 0)
        with self.action(ActionKind.FUA, "talent", first) as act:
            if self.e(4):
                for e in self.enemies():
                    self.battle.apply(
                        Modifier(
                            "Pity Its Heart Gnawed by Worms",
                            stats={S.VULN: self.ep(4, 0)},
                            duration=int(self.ep(4, 1)),
                            kind=ModKind.DEBUFF,
                        ),
                        e,
                        self.char,
                    )
            for i in range(n):
                t = first if i == 0 and first is not None and first.alive and first.hp > 0 else self._random_enemy()
                if t is None:
                    break
                (h,) = act.hit(t, self.p("talent", 0), toughness=self.toughness("talent"), primary=i == 0)
                if (h.was_broken or self.zone_active) and h.toughness_potential > 0 and t.alive:
                    self.battle.super_break(
                        self.char, t, h.toughness_potential, self.p("talent", 2), label="Super Break (Dahlia FUA)"
                    )
        self.fua_count += 1
        if self.trace(2) and (self.fua_count - 1) % int(self.tp(2, 0)) == 0:
            self.battle.gain_sp(A4_SP, self.char)
        if self.e(6):
            for p in self.dance_partners():
                self.battle.advance(p, self.ep(6, 1))

    # -------------------------------------------------------------- policy
    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        # the Zone counts down at the start of her turns, so it covers every action until the turn it expires
        if self.opts.get("rotation", "skill") == "skill" and self.can_skill() and not self.zone_active:
            self.skill(target)
        else:
            self.basic(target)

    # ------------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        self.simple_basic(target)

    def skill(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.SKILL, "skill", target) as act:
            self._deploy_zone()
            act.blast(
                target,
                self.p("skill", 0),
                self.p("skill", 0),
                toughness=(self.toughness("skill", 0), self.toughness("skill", 2)),
            )

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult", target) as act:
            enemies = self.enemies()
            for e in enemies:
                self._wilt(e, int(self.p("ult", 1)))
            if enemies:
                # "distributed evenly across all enemies"
                act.aoe(self.p("ult", 0) / len(enemies), toughness=self.toughness("ult", 1), main_target=target)
