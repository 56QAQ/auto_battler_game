"""Black Swan (黑天鹅) — Nihility / Wind. Arcana: a stacking Wind DoT that spreads and ignores DEF.

Base kit only (the enhanced kit is not implemented yet).
"""

from __future__ import annotations

from collections import defaultdict

from .. import events as E
from .. import stats as S
from ..battle import Battle
from ..entities import Enemy, Entity
from ..enums import ActionKind, DmgTag, Element
from ..modifiers import DotModifier, Modifier, ModKind, Stacking, Tick
from . import register
from .base import Kit

DOT_KINDS = ("wind_shear", "bleed", "burn", "shock")
MAX_ARCANA = 50


@register
class BlackSwan(Kit):
    char_id = "1307"

    def setup(self) -> None:
        if self.char.enhanced:
            raise NotImplementedError("Black Swan enhanced kit is not implemented yet")
        self.a4_count: dict[tuple[int, int], int] = defaultdict(int)
        self.on(E.DOT_TRIGGERED, self._on_dot)
        if self.trace(2):
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
        if self.e(6):
            self.on(E.ATTACK_END, self._e6)

    def on_battle_start(self) -> None:
        if self.trace(2):
            for e in self.enemies():
                self.add_arcana(e, 1, self.tp(2, 0))

    def _a6(self, mod: Modifier, key: str, ent: Entity) -> float:
        return min(self.tp(3, 1), self.tp(3, 0) * self.char.stat(S.EHR))

    def _e1(self, mod: Modifier, key: str, enemy: Entity) -> float:
        kind = {"Wind": "wind_shear", "Physical": "bleed", "Fire": "burn", "Thunder": "shock"}[key.split(":")[1]]
        return self.ep(1, 0) if enemy.has_tag(kind) else 0.0

    # ------------------------------------------------------------- Arcana
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

        return DotModifier(
            "Arcana",
            dot_type="arcana",
            damage_fn=dmg,
            duration=None,  # type: ignore[arg-type]
            stacks=stacks,
            max_stacks=MAX_ARCANA,
            stacking=Stacking.STACK,
            key="Arcana",
        )

    def add_arcana(self, target: Entity, n: int, chance: float, fixed: bool = False) -> None:
        if not isinstance(target, Enemy) or not target.alive:
            return
        if self.e(6) and self.battle.rng.random() < self.ep(6, 0):
            n += 1
        mod = self.arcana_mod(target, n)
        mod.duration = None
        self.battle.try_debuff(mod, target, self.char, chance, fixed=fixed)

    def _on_dot(self, ev: E.Ev) -> None:
        t = ev.target
        if not t.alive:
            return
        if ev.turn_start:
            self.add_arcana(t, 1, self.p("talent", 1))
        elif self.trace(2) and ev.action is not None:
            key = (id(ev.action), t.uid)
            if self.a4_count[key] < self.tp(2, 1):
                self.a4_count[key] += 1
                self.add_arcana(t, 1, self.tp(2, 0))

    def _e6(self, ev: E.Ev) -> None:
        act = ev.attack
        if act.owner is self.char or act.owner.side != self.char.side:
            return
        for t in act.attacked:
            self.add_arcana(t, 1, self.ep(6, 1))

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
            hits = act.blast(
                target,
                self.p("skill", 0),
                self.p("skill", 0),
                toughness=(self.toughness("skill", 0), self.toughness("skill", 2)),
            )
            for t in {h.target for h in hits}:
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
                mod = self.battle.apply(
                    Epiphany(
                        "Epiphany",
                        stats=stats,
                        duration=int(self.p("ult", 1)),
                        kind=ModKind.DEBUFF,
                        tick=Tick.HOLDER_TURN_END,
                        tags=set(DOT_KINDS),
                    ),
                    e,
                    self.char,
                )
                mod.data["keep"] = int(self.p("ult", 3))
                mod.data["vuln"] = self.p("ult", 2)
            act.aoe(self.p("ult", 0), toughness=self.toughness("ult", 1), main_target=target)


class Epiphany(Modifier):
    """Enemies take more DMG during their own turn; Arcana counts as all four DoT types."""

    def on_apply(self, battle: Battle) -> None:
        def before_hit(ev: E.Ev) -> None:
            if ev.hit.target is self.holder and battle.current_turn is self.holder:
                ev.hit.add(S.VULN, self.data.get("vuln", 0.0))

        self.listen(E.BEFORE_HIT, before_hit)
