"""Silver Wolf (银狼) — Nihility / Quantum. Weakness implant, RES/DEF shred, random Bugs."""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..entities import Enemy
from ..enums import ActionKind, Element, EnemyRank
from ..modifiers import Modifier, ModKind, Tick
from . import register, register_enhanced
from .base import Kit

BUGS = ("ATK", "DEF", "SPD")


@register
class SilverWolf(Kit):
    char_id = "1006"
    default_opts = {"implant": None}  # element to implant (default: first ally element the target lacks)

    def setup(self) -> None:
        self.on(E.ATTACK_END, self._talent)
        if self.trace(1):
            self.on(E.BREAK, self._a2)
        if self.e(2):
            self.on(
                E.ENEMY_SPAWNED,
                lambda ev: self.battle.apply(
                    Modifier(
                        "Zombie Network", stats={S.EFFECT_RES: -self.ep(2, 0)}, kind=ModKind.DEBUFF, dispellable=False
                    ),
                    ev.enemy,
                    self.char,
                ),
            )
        if self.e(6):
            self.on(E.BEFORE_HIT, self._e6)

    def on_battle_start(self) -> None:
        if self.e(2):
            for e in self.enemies():
                self.battle.apply(
                    Modifier(
                        "Zombie Network", stats={S.EFFECT_RES: -self.ep(2, 0)}, kind=ModKind.DEBUFF, dispellable=False
                    ),
                    e,
                    self.char,
                )

    def technique(self) -> None:
        """Quantum DMG (#1% ATK) to all enemies, reducing Toughness regardless of Weakness Types."""
        if self.enemies():
            with self.action(ActionKind.EXTRA, "technique", label="Silver Wolf Technique", energy=0, sp=0) as act:
                act.aoe(
                    self.sk("technique")["params"][0][0],
                    toughness=self.toughness("technique"),
                    ignore_weakness=True,
                )

    # ------------------------------------------------------------ bugs
    def bug(self, target: Enemy, chance: float) -> None:
        # PassiveSkill_RandomBug: a random Bug among the types the target does not have yet (any type if it has all)
        missing = [b for b in BUGS if target.get_mod(f"Bug ({b})") is None]
        kind = self.battle.rng.choice(missing or list(BUGS))
        value = {"ATK": self.p("talent", 0), "DEF": self.p("talent", 1), "SPD": self.p("talent", 2)}[kind]
        key = {"ATK": S.ATK_PCT, "DEF": S.DEF_REDUCTION, "SPD": S.SPD_PCT}[kind]
        stat = value if key == S.DEF_REDUCTION else -value
        dur = int(self.p("talent", 4)) + (int(self.tp(1, 0)) if self.trace(1) else 0)
        self.battle.try_debuff(
            Modifier(f"Bug ({kind})", stats={key: stat}, duration=dur, kind=ModKind.DEBUFF), target, self.char, chance
        )

    def _talent(self, ev: E.Ev) -> None:
        act = ev.attack
        if act.owner is not self.char:
            return
        for t in act.attacked:
            if t.alive:
                self.bug(t, self.p("talent", 3))

    def _a2(self, ev: E.Ev) -> None:
        if ev.target.alive:
            self.bug(ev.target, self.tp(1, 1))

    def _e6(self, ev: E.Ev) -> None:
        hit = ev.hit
        if hit.attacker is self.char:
            hit.add(S.DMG_PCT, min(self.ep(6, 1), self.ep(6, 0) * len(hit.target.debuffs)))

    # --------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        self.simple_basic(target)

    def _implant_element(self, target: Enemy) -> Element | None:
        pref = self.opts.get("implant")
        if pref:
            return Element(pref) if not isinstance(pref, Element) else pref
        for c in self.battle.team:
            if c is not self.char and not target.is_weak_to(c.element):
                return c.element
        return None if target.is_weak_to(self.char.element) else self.char.element

    def skill(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.SKILL, "skill", target) as act:
            # A6 counts the debuffs present when the Skill is used, before its own RES shred / implant
            res = self.p("skill", 5)
            if self.trace(3) and len(target.debuffs) >= self.tp(3, 0):
                res += self.tp(3, 1)
            self._res_down(target, res)
            el = self._implant_element(target)
            if el is not None:
                self.battle.remove_named(target, "Implanted Weakness")
                dur = int(self.p("skill", 2)) + (int(self.tp(2, 0)) if self.trace(2) else 0)
                already = target.is_weak_to(el)
                stats = {} if already else {f"{S.RES_REDUCTION}:{el.value}": self.p("skill", 3)}
                self.battle.try_debuff(
                    Modifier(
                        "Implanted Weakness", stats=stats, duration=dur, kind=ModKind.DEBUFF, tags={f"weak:{el.value}"}
                    ),
                    target,
                    self.char,
                    self.p("skill", 1),
                )
            act.hit(target, self.p("skill", 0), toughness=self.toughness("skill"), splits="data")

    def _res_down(self, target: Enemy, value: float) -> None:
        self.battle.try_debuff(
            Modifier(
                "Allow Changes?",
                stats={S.RES_REDUCTION: value},
                duration=int(self.p("skill", 6)),
                kind=ModKind.DEBUFF,
                tick=Tick.HOLDER_TURN_START,  # BPSkill_AllDamageTypeResistanceDown: ModifierPhase1End
            ),
            target,
            self.char,
            self.p("skill", 4),
        )

    def _def_down(self, target: Enemy) -> None:
        self.battle.try_debuff(
            Modifier(
                "User Banned",
                stats={S.DEF_REDUCTION: self.p("ult", 2)},
                duration=int(self.p("ult", 3)),
                kind=ModKind.DEBUFF,
                tick=Tick.HOLDER_TURN_START,  # Ultra_DefenceRatioDown: ModifierPhase1End
            ),
            target,
            self.char,
            self.p("ult", 1),
        )

    def ult(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.ULT, "ult", target) as act:
            self._def_down(target)
            act.hit(target, self.p("ult", 0), toughness=self.toughness("ult"), splits="data")
            n = min(int(self.ep(1, 1)), len(target.debuffs)) if target.alive else 0
            if self.e(1) and n:
                act.energy += self.ep(1, 0) * n
            if self.e(4):
                for _ in range(min(int(self.ep(4, 1)), len(target.debuffs))):
                    self.battle.additional_damage(self.char, target, self.ep(4, 0), label="E4 Bounce Attack")


@register_enhanced
class SilverWolfEnhanced(SilverWolf):
    """Enhanced Silver Wolf: AoE Ultimate, 100% Bug chance, EHR-to-ATK (A6), DMG taken on entry (E2)."""

    def setup(self) -> None:
        self.on(E.ATTACK_END, self._talent)
        self.on(E.KILL, self._transfer_implant)
        if self.trace(1):
            self.on(E.BREAK, self._a2)
        if self.trace(2):
            self.on(
                E.TURN_START, lambda ev: ev.entity is self.char and self.battle.gain_energy(self.char, self.tp(2, 1))
            )
        if self.trace(3):
            self.passive(
                "Side Note",
                {},
                dyn=lambda m, k, e: min(
                    self.tp(3, 2), int(self.char.stat(S.EHR) / self.tp(3, 0) + 1e-9) * self.tp(3, 1)
                ),
                dyn_keys={S.ATK_PCT},
            )
        if self.e(2):
            self.on(E.ENEMY_SPAWNED, lambda ev: self._e2_enter(ev.enemy))
            self.on(E.ATTACK_END, self._e2_bug)
        if self.e(6):
            self.on(E.BEFORE_HIT, self._e6)

    def on_battle_start(self) -> None:
        if self.trace(2):  # ModifySPNew AddValue: scaled by Energy Regeneration Rate
            self.battle.gain_energy(self.char, self.tp(2, 0))
        if self.e(2):
            for e in self.enemies():
                self._e2_enter(e)

    def _transfer_implant(self, ev: E.Ev) -> None:
        """Talent: a defeated enemy's implanted Weakness moves to a surviving enemy without one (Elite+ first)."""
        mod = next((m for m in ev.target.mods("Implanted Weakness") if m.source is self.char), None)
        if mod is None:
            return
        pool = [
            e
            for e in self.enemies()
            if e is not ev.target and e.hp > 0 and not any(m.source is self.char for m in e.mods("Implanted Weakness"))
        ]
        tag = next((t for t in mod.tags if t.startswith("weak:")), None)
        if not pool or tag is None:
            return
        target = min(pool, key=lambda e: e.rank == EnemyRank.NORMAL)
        el = Element(tag.split(":", 1)[1])
        stats = {} if target.is_weak_to(el) else {f"{S.RES_REDUCTION}:{el.value}": self.p("skill", 3)}
        self.battle.apply(
            Modifier("Implanted Weakness", stats=stats, duration=mod.duration, kind=ModKind.DEBUFF, tags={tag}),
            target,
            self.char,
        )

    def _e2_enter(self, e: Enemy) -> None:
        self.battle.apply(
            Modifier("Zombie Network", stats={S.VULN: self.ep(2, 0)}, kind=ModKind.DEBUFF, dispellable=False),
            e,
            self.char,
        )

    def _e2_bug(self, ev: E.Ev) -> None:
        act = ev.attack
        if act.owner is not None and act.owner.side == self.char.side and act.owner is not self.char:
            for t in act.attacked:
                if t.alive:
                    self.bug(t, self.ep(2, 1))

    def _implant_element(self, target: Enemy) -> Element | None:
        pref = self.opts.get("implant")
        if pref:
            return Element(pref)
        first = self.battle.team[0]  # "prioritizing the implant of a Weakness that matches the first character"
        if not target.is_weak_to(first.element):
            return first.element
        return super()._implant_element(target)

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult", target) as act:
            for e in self.enemies():
                self._def_down(e)
            act.aoe(self.p("ult", 0), toughness=self.toughness("ult", 1), main_target=target, splits="data")
            main = target if target is not None and target.alive else None
            if self.e(1) and main is not None:
                act.energy += self.ep(1, 0) * min(int(self.ep(1, 1)), len(main.debuffs))
            if self.e(4):
                for e in self.enemies():
                    for _ in range(min(int(self.ep(4, 1)), len(e.debuffs))):
                        self.battle.additional_damage(self.char, e, self.ep(4, 0), label="E4 Bounce Attack")

    def skill(self, target: Enemy | None) -> None:  # the enhanced A4/A6 no longer modify the Skill
        assert target is not None
        with self.action(ActionKind.SKILL, "skill", target) as act:
            self._res_down(target, self.p("skill", 5))  # script order: RES shred, then the implant
            el = self._implant_element(target)
            if el is not None:
                self.battle.remove_named(target, "Implanted Weakness")
                stats = {} if target.is_weak_to(el) else {f"{S.RES_REDUCTION}:{el.value}": self.p("skill", 3)}
                self.battle.try_debuff(
                    Modifier(
                        "Implanted Weakness",
                        stats=stats,
                        duration=int(self.p("skill", 2)),
                        kind=ModKind.DEBUFF,
                        tags={f"weak:{el.value}"},
                    ),
                    target,
                    self.char,
                    self.p("skill", 1),
                )
            act.hit(target, self.p("skill", 0), toughness=self.toughness("skill"), splits="data")
