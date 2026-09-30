"""Black Swan (黑天鹅) — Nihility / Wind. Arcana: a stacking Wind DoT that spreads and ignores DEF.

Base kit and enhanced kit (``BlackSwanEnhanced``).
"""

from __future__ import annotations

from collections.abc import Iterable

from .. import events as E
from .. import stats as S
from ..battle import Battle
from ..entities import Character, Enemy, Entity
from ..enums import ActionKind, DmgTag, Element
from ..modifiers import DotModifier, Modifier, ModKind, Stacking, Tick
from . import register, register_enhanced
from .base import Kit

DOT_KINDS = ("wind_shear", "bleed", "burn", "shock")
# Avatar_BlackSwan_00_SkillMazeInLevel_Insert: the Technique's repeated Arcana rolls stop after 99 loops at most
TECHNIQUE_MAX_ROLLS = 99


class Arcana(DotModifier):
    """Arcana DoT. While its holder is in Epiphany it is also considered Wind Shear, Bleed, Burn and Shock
    (the enhanced kit gives it those tags permanently)."""

    @property
    def tags(self) -> set[str]:
        h = self.holder
        if h is not None and not self.removed and h.has_mod("Epiphany"):
            return self._tags | set(DOT_KINDS)
        return self._tags

    @tags.setter
    def tags(self, value: Iterable[str]) -> None:
        self._tags = set(value)


def _adjacent_to_fallen(battle: Battle, target: Enemy) -> list[Enemy]:
    """The alive enemies next to ``target`` in the line-up (``battle.adjacent`` needs a living target)."""
    enemies = battle.enemies
    if target not in enemies:
        return []
    i = enemies.index(target)
    out = []
    for side in (range(i - 1, -1, -1), range(i + 1, len(enemies))):
        for j in side:
            if enemies[j].alive and enemies[j].hp > 0:
                out.append(enemies[j])
                break
    return out


@register
class BlackSwan(Kit):
    char_id = "1307"

    def setup(self) -> None:
        self.on(E.DOT_TRIGGERED, self._on_dot)
        if self.trace(2):
            # every enemy entering combat (wave 1 included: setup runs before wave 1 spawns)
            self.on(E.ENEMY_SPAWNED, lambda ev: self.add_arcana(ev.enemy, 1, self.tp(2, 0)))
        if self.trace(3):
            self.passive("Candleflame's Portent", {}, dyn=self._a6, dyn_keys={S.DMG_PCT})
        if self.e(1):
            self.passive(
                "Seven Pillars of Wisdom",
                {},
                scope=self.enemy_scope,
                dyn=self._e1,
                dyn_keys={f"{S.RES_REDUCTION}:{el}" for el in ("Wind", "Physical", "Fire", "Thunder")},
            )
        if self.e(2):
            self.on(E.KILL, self._e2)
        if self.e(6):
            self.on(E.BEFORE_HIT, self._e6)

    def technique(self) -> None:
        """Each enemy rolls Arcana repeatedly; every success halves (#2) the next roll's base chance."""
        p = self.sk("technique")["params"][0]
        for e in self.enemies():
            chance = p[0]
            for _ in range(TECHNIQUE_MAX_ROLLS):
                if self.add_arcana(e, 1, chance) is None:
                    break
                chance *= p[1]

    def _a6(self, mod: Modifier, key: str, ent: Entity) -> float:
        return min(self.tp(3, 1), self.tp(3, 0) * self.char.stat(S.EHR))

    def _e1(self, mod: Modifier, key: str, enemy: Entity) -> float:
        kind = {"Wind": "wind_shear", "Physical": "bleed", "Fire": "burn", "Thunder": "shock"}[key.split(":")[1]]
        return self.ep(1, 0) if enemy.has_tag(kind) else 0.0

    def _e2(self, ev: E.Ev) -> None:
        """E2: an enemy defeated while afflicted with Arcana spreads 6 stacks to its adjacent targets."""
        if isinstance(ev.target, Enemy) and ev.target.has_mod("Arcana"):
            for adj in _adjacent_to_fallen(self.battle, ev.target):
                self.add_arcana(adj, int(self.ep(2, 1)), self.ep(2, 0))

    # ------------------------------------------------------------- Arcana
    def max_arcana(self) -> int:
        return int(self.p("talent", 7))

    def arcana_mod(self, target: Enemy, stacks: int) -> DotModifier:
        bs = self.char

        def dmg(mod: DotModifier, b: Battle, ratio: float) -> float:
            n = mod.stacks
            extra: dict[str, float] = {}
            if mod.turn_start and n >= self.p("talent", 5):
                extra[S.DEF_IGNORE] = self.p("talent", 6)
            mult = self.p("talent", 0) + self.p("talent", 2) * n
            d = b.dot_damage(
                bs, target, Element.WIND, mult, label="Arcana", tags=(DmgTag.DOT, "arcana"), ratio=ratio, extra=extra
            )
            if mod.turn_start:
                if n >= self.p("talent", 3):
                    for adj in b.adjacent(target):
                        b.dot_damage(
                            bs,
                            adj,
                            Element.WIND,
                            self.p("talent", 4),
                            label="Arcana (adjacent)",
                            tags=(DmgTag.DOT, "arcana"),
                            extra=extra,
                        )
                        self.add_arcana(adj, 1, self.p("talent", 1))
                ep = target.get_mod("Epiphany")
                if ep is not None and ep.data.get("keep", 0) > 0:
                    ep.data["keep"] -= 1
                else:
                    mod.stacks = 1
            return d

        return Arcana(
            "Arcana",
            dot_type="arcana",
            damage_fn=dmg,
            duration=None,  # type: ignore[arg-type]
            stacks=stacks,
            max_stacks=self.max_arcana(),
            stacking=Stacking.STACK,
            key="Arcana",
        )

    def add_arcana(self, target: Entity, n: int, chance: float, fixed: bool = False) -> Modifier | None:
        if not isinstance(target, Enemy) or not target.alive:
            return None
        if self.e(6) and self.battle.rng.random() < self.ep(6, 0):
            n += 1
        mod = self.arcana_mod(target, n)
        mod.duration = None
        return self.battle.try_debuff(mod, target, self.char, chance, fixed=fixed)

    def _on_dot(self, ev: E.Ev) -> None:
        t = ev.target
        if not t.alive:
            return
        if ev.turn_start:
            self.add_arcana(t, 1, self.p("talent", 1))
        elif self.trace(2) and ev.action is not None:
            # A4: at most #2 stacks per target from the DoTs triggered during one attack
            counts: dict[int, int] = ev.action.data.setdefault("bs_a4", {})
            if counts.get(t.uid, 0) < self.tp(2, 1):
                counts[t.uid] = counts.get(t.uid, 0) + 1
                self.add_arcana(t, 1, self.tp(2, 0))

    def _e6(self, ev: E.Ev) -> None:
        """E6: an enemy attacked by a teammate rolls Arcana once per attack, before the DMG
        (Rank06_SubOnEnemy listens to OnBeforeBeingAttacked)."""
        hit = ev.hit
        act = hit.action
        if act is None or act.owner is self.char or act.owner.side != self.char.side:
            return
        if not isinstance(hit.target, Enemy):
            return
        done: set[int] = act.data.setdefault("bs_e6", set())
        if hit.target.uid in done:
            return
        done.add(hit.target.uid)
        self.add_arcana(hit.target, 1, self.ep(6, 1))

    # ------------------------------------------------------------ actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.BASIC, "basic", target) as act:
            act.hit(target, self.p("basic", 0), toughness=self.toughness("basic"))
            if target.alive:
                self.add_arcana(target, 1, self.p("basic", 1))
                for kind in DOT_KINDS:
                    if target.has_tag(kind):
                        self.add_arcana(target, 1, self.p("basic", 2))

    def skill(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.SKILL, "skill", target) as act:
            act.blast(
                target,
                self.p("skill", 0),
                self.p("skill", 0),
                toughness=(self.toughness("skill", 0), self.toughness("skill", 2)),
            )
            for t in list(act.attacked):  # main target first, then adjacent (deterministic RNG order)
                if not t.alive:
                    continue
                self.add_arcana(t, 1, self.p("skill", 1))
                self.battle.try_debuff(
                    Modifier(
                        "Decadence, False Twilight",
                        stats={S.DEF_REDUCTION: self.p("skill", 3)},
                        duration=int(self.p("skill", 4)),
                        kind=ModKind.DEBUFF,
                    ),
                    t,
                    self.char,
                    self.p("skill", 2),
                )
            if self.trace(1) and target.alive:
                for kind in DOT_KINDS:
                    if target.has_tag(kind):
                        self.add_arcana(target, 1, self.tp(1, 0))

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult", target) as act:
            for e in self.enemies():
                stats = {S.EFFECT_RES: -self.ep(4, 0)} if self.e(4) else {}
                # MAvatar_BlackSwan_00_DOT_Enhance: LifeStepMoment ModifierPhase1End (counts down at the start of
                # the enemy's turn, after its DoTs)
                mod = self.battle.apply(
                    Epiphany(
                        "Epiphany",
                        stats=stats,
                        duration=int(self.p("ult", 1)),
                        kind=ModKind.DEBUFF,
                        tick=Tick.HOLDER_TURN_START,
                    ),
                    e,
                    self.char,
                )
                mod.data["keep"] = int(self.p("ult", 3))
                mod.data["vuln"] = self.p("ult", 2)
                mod.data["e4_energy"] = self.ep(4, 1) if self.e(4) else 0.0
                mod.data["e4_used"] = False  # the E4 trigger count resets when Epiphany is applied again
            act.aoe(self.p("ult", 0), toughness=self.toughness("ult", 1), main_target=target, splits="data")


class Epiphany(Modifier):
    """Enemies take more DMG during their own turn. E4: Black Swan regenerates Energy once per Epiphany, at the
    start of the holder's turn or when it is defeated."""

    def on_apply(self, battle: Battle) -> None:
        def before_hit(ev: E.Ev) -> None:
            if ev.hit.target is self.holder and battle.current_turn is self.holder:
                ev.hit.add(S.VULN, self.data.get("vuln", 0.0))

        def e4(ev: E.Ev) -> None:
            who = ev.data.get("entity", ev.data.get("target"))
            if who is not self.holder or not self.data.get("e4_energy") or self.data.get("e4_used"):
                return
            self.data["e4_used"] = True
            src = self.source
            if isinstance(src, Character):
                battle.gain_energy(src, self.data["e4_energy"])

        self.listen(E.BEFORE_HIT, before_hit)
        self.listen(E.TURN_START, e4)
        self.listen(E.KILL, e4)


@register_enhanced
class BlackSwanEnhanced(BlackSwan):
    """Enhanced Black Swan: Arcana always counts as all four DoTs, halves instead of resetting, 20% DEF ignore,
    team-wide EHR-based DMG%, stronger Epiphany."""

    def setup(self) -> None:
        self.on(E.AFTER_HIT, self._on_dot_hit)
        self.on(E.ATTACK_END, self._on_attack_enh)
        self.on(E.BEFORE_HIT, self._epiphany_vuln)
        if self.trace(2) or self.e(2):
            # every enemy entering combat (wave 1 included: setup runs before wave 1 spawns)
            self.on(E.ENEMY_SPAWNED, lambda ev: self._on_enter(ev.enemy))
        if self.trace(3):
            self.passive(
                "Candleflame's Portent",
                {},
                scope=self.ally_scope,
                key="BS A6",
                dyn=lambda m, k, e: min(self.tp(3, 1), self.tp(3, 0) * self.char.stat(S.EHR)),
                dyn_keys={S.DMG_PCT},
            )
        if self.e(1):
            self.passive(
                "Seven Pillars of Wisdom",
                {},
                scope=self.enemy_scope,
                dyn=self._e1,
                dyn_keys={f"{S.RES_REDUCTION}:{el}" for el in ("Wind", "Physical", "Fire", "Thunder")},
            )
        if self.e(4):
            self.on(E.TURN_START, self._e4_energy)
            self.on(
                E.KILL, lambda ev: ev.target.has_mod("Epiphany") and self.battle.gain_energy(self.char, self.ep(4, 1))
            )
        if self.e(6):
            self.on(E.BEFORE_HIT, self._e6)

    def _on_enter(self, e: Enemy) -> None:
        if self.trace(2):
            self.add_arcana(e, 1, self.tp(2, 0))
            self._def_down(e, self.tp(2, 1), int(self.tp(2, 2)))
        if self.e(2):
            self.add_arcana(e, int(self.ep(2, 1)), self.ep(2, 0))

    def _e1(self, mod: Modifier, key: str, enemy: Entity) -> float:
        return (
            self.ep(1, 0)
            if enemy.has_mod("Arcana")
            or enemy.has_tag(
                {"Wind": "wind_shear", "Physical": "bleed", "Fire": "burn", "Thunder": "shock"}[key.split(":")[1]]
            )
            else 0.0
        )

    def _e4_energy(self, ev: E.Ev) -> None:
        if isinstance(ev.entity, Enemy) and ev.entity.has_mod("Epiphany"):
            self.battle.gain_energy(self.char, self.ep(4, 1))

    def max_arcana(self) -> int:
        return int(self.p("talent", 7)) + (int(self.ep(6, 3)) if self.e(6) else 0)

    def arcana_mod(self, target: Enemy, stacks: int) -> DotModifier:
        bs = self.char

        def dmg(mod: DotModifier, b: Battle, ratio: float) -> float:
            n = min(mod.stacks, self.max_arcana())
            extra = {S.DEF_IGNORE: self.p("talent", 6)}
            mult = self.p("talent", 0) + self.p("talent", 2) * n
            d = b.dot_damage(
                bs, target, Element.WIND, mult, label="Arcana", tags=(DmgTag.DOT, "arcana"), ratio=ratio, extra=extra
            )
            if mod.turn_start:
                for adj in b.adjacent(target):
                    b.dot_damage(
                        bs,
                        adj,
                        Element.WIND,
                        self.p("talent", 4),
                        label="Arcana (adjacent)",
                        tags=(DmgTag.DOT, "arcana"),
                        extra=extra,
                    )
                mod.stacks = min(mod.stacks, self.max_arcana())
                if not target.has_mod("Epiphany"):
                    mod.stacks = max(1, mod.stacks // 2)
            return d

        # Arcana counts as Wind Shear, Bleed, Burn and Shock at all times in the enhanced kit
        return Arcana(
            "Arcana",
            dot_type="arcana",
            damage_fn=dmg,
            duration=None,  # type: ignore[arg-type]
            stacks=stacks,
            max_stacks=10_000,
            stacking=Stacking.STACK,
            key="Arcana",
            tags=set(DOT_KINDS),
        )

    def add_arcana(self, target: Entity, n: int, chance: float, fixed: bool = False) -> Modifier | None:
        if not isinstance(target, Enemy) or not target.alive:
            return None
        if target.has_mod("Epiphany"):
            n += sum(1 for _ in range(n) if self.battle.rng.random() < self.p("ult", 3))
        if self.e(6):
            n *= 2
        mod = self.arcana_mod(target, n)
        mod.duration = None
        return self.battle.try_debuff(mod, target, self.char, chance, fixed=fixed)

    def _on_dot_hit(self, ev: E.Ev) -> None:
        """Talent: every instance of DoT an enemy receives (turn start, detonations, Arcana's adjacent DMG, Break
        DoTs ...) rolls 1 Arcana stack (M_Advanced_BlackSwan_P01_ListenAddPoison_SubOnEnemy, AttackType DOT)."""
        hit = ev.hit
        if DmgTag.DOT in hit.tags and isinstance(hit.target, Enemy) and hit.target.alive:
            self.add_arcana(hit.target, 1, self.p("talent", 1))

    def _on_attack_enh(self, ev: E.Ev) -> None:
        act = ev.attack
        if act.owner is self.char:
            if self.trace(1):
                for t in act.attacked:
                    self.add_arcana(t, int(self.tp(1, 1)), self.tp(1, 0))
            if self.trace(2) and act.kind in (ActionKind.BASIC, ActionKind.ULT):
                for t in act.attacked:
                    self._def_down(t, self.tp(2, 1), int(self.tp(2, 2)))

    def _def_down(self, t: Enemy, chance: float, turns: int) -> None:
        if t.alive:
            self.battle.try_debuff(
                Modifier(
                    "Decadence, False Twilight",
                    stats={S.DEF_REDUCTION: self.p("skill", 3)},
                    duration=turns,
                    kind=ModKind.DEBUFF,
                ),
                t,
                self.char,
                chance,
            )

    def _epiphany_vuln(self, ev: E.Ev) -> None:
        ep = ev.hit.target.get_mod("Epiphany")
        if ep is not None and ev.hit.attacker.side == self.char.side:
            ev.hit.add(S.VULN, self.p("ult", 2) + (self.ep(4, 0) if self.e(4) else 0.0))

    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        self.simple_basic(target)

    def skill(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.SKILL, "skill", target) as act:
            act.blast(
                target,
                self.p("skill", 0),
                self.p("skill", 0),
                toughness=(self.toughness("skill", 0), self.toughness("skill", 2)),
            )
            for t in list(act.attacked):  # main target first, then adjacent (deterministic RNG order)
                self._def_down(t, self.p("skill", 2), int(self.p("skill", 1)))

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult", target) as act:
            for e in self.enemies():
                self.battle.apply(
                    Modifier("Epiphany", duration=int(self.p("ult", 1)), kind=ModKind.DEBUFF, key="Epiphany"),
                    e,
                    self.char,
                )
            act.aoe(self.p("ult", 0), toughness=self.toughness("ult", 1), main_target=target, splits="data")
