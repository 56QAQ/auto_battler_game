"""Lingsha (灵砂) — Abundance / Fire. Fuyuan: a summon (own SPD, limited action count) that follows up.

Options: ``rotation``: "auto" (default: Skill only when Fuyuan is absent or can take the whole
+3 action count without overflowing) | "skill" | "basic".

Healing is modelled with ``battle.heal`` (it drives A6 and team effects); Fuyuan's debuff dispel
removes one dispellable debuff from each ally.
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..entities import Character, Enemy, Entity, Summon
from ..enums import ActionKind, DmgTag, Element, Side
from ..modifiers import Modifier, ModKind, Tick, hidden
from . import register
from .base import Kit

BEFOG = "Befog"


@register
class Lingsha(Kit):
    char_id = "1222"
    default_opts = {"rotation": "auto"}

    def setup(self) -> None:
        self.fuyuan: Summon | None = None
        self.count = 0  # Fuyuan's action count
        self.e6_field: Modifier | None = None
        self.a6_cd = 0
        self.on(E.TURN_START, self._on_turn_start)
        if self.trace(1):
            self.passive("Vermilion Waft", {}, dyn=self._a2, dyn_keys={S.ATK_PCT, S.HEAL_PCT})
        if self.trace(3):
            self.on(E.HP_CHANGED, self._a6)
        if self.e(1):
            self.passive("Bloom on Vileward Bouquet", {S.BREAK_EFF: self.ep(1, 1)})
            self.on(E.BREAK, self._e1_break)
            self.on(E.RECOVERED, lambda ev: self.battle.remove_named(ev.enemy, "Bloom on Vileward Bouquet"))

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        self._summon()
        for e in self.enemies():
            self._befog(e, int(p[0]))

    def _on_turn_start(self, ev: E.Ev) -> None:
        if ev.entity is self.char and not ev.extra and self.a6_cd > 0:
            self.a6_cd -= 1

    # ------------------------------------------------------------ passives
    def _a2(self, mod: Modifier, key: str, ent: Entity) -> float:
        be = self.char.stat(S.BREAK_EFFECT)
        if key == S.ATK_PCT:
            return min(self.tp(1, 2), self.tp(1, 0) * be)
        return min(self.tp(1, 3), self.tp(1, 1) * be)

    def _e1_break(self, ev: E.Ev) -> None:
        t = ev.target
        if t.alive:
            self.battle.apply(
                Modifier(
                    "Bloom on Vileward Bouquet",
                    stats={S.DEF_REDUCTION: self.ep(1, 0)},
                    kind=ModKind.DEBUFF,
                    tick=Tick.NONE,  # removed when the enemy recovers from Weakness Break
                ),
                t,
                self.char,
            )

    def _a6(self, ev: E.Ev) -> None:
        ent = ev.entity
        if ev.delta >= 0 or not isinstance(ent, Character) or ent.side != Side.ALLY:
            return
        if not self.fuyuan_alive or self.a6_cd > 0:
            return
        if any(c.hp_ratio <= self.tp(3, 0) for c in self.allies()):
            self.a6_cd = int(self.tp(3, 1))
            self.battle.queue_action(lambda: self._fuyuan_attack(consume=False), self.char, "Fuyuan (A6)")

    # -------------------------------------------------------------- healing
    def _heal_value(self, pct: float, flat: float) -> float:
        return (pct * self.char.atk + flat) * (1.0 + self.char.stat(S.HEAL_PCT))

    def _heal_all(self, pct: float, flat: float) -> None:
        v = self._heal_value(pct, flat)
        for c in self.allies():
            self.battle.heal(c, v, self.char)

    # --------------------------------------------------------------- Fuyuan
    @property
    def fuyuan_alive(self) -> bool:
        return self.fuyuan is not None and self.fuyuan.alive

    def _summon(self) -> None:
        """Summon Fuyuan (initial action count) or add to its action count."""
        n = int(self.p("talent", 6))
        cap = int(self.p("talent", 4))
        if not self.fuyuan_alive:
            self.fuyuan = self.battle.add_unit(
                Summon("Fuyuan", self.char, spd=self.p("talent", 0), on_turn=lambda u, b: self._fuyuan_attack(True))
            )
            self.count = 0
            if self.e(6):
                self.e6_field = self.buff_self(
                    hidden("Arcadia Under Deep Seclusion", {S.RES_REDUCTION: self.ep(6, 0)}, scope=self.enemy_scope)
                )
        self.count = min(cap, self.count + n)

    def _dismiss(self) -> None:
        if self.fuyuan is not None:
            self.battle.remove_unit(self.fuyuan)
        self.fuyuan = None
        self.count = 0
        if self.e6_field is not None:
            self.battle.remove_modifier(self.e6_field)
            self.e6_field = None

    def _fire_target(self) -> Enemy | None:
        """Random enemy, preferring ones with Toughness left and a Fire Weakness."""
        pool = [e for e in self.enemies() if e.hp > 0] or self.enemies()
        pri = [e for e in pool if not e.broken and e.toughness > 0 and e.is_weak_to(Element.FIRE)]
        cands = pri or pool
        return self.battle.rng.choice(cands) if cands else None

    def _fuyuan_attack(self, consume: bool) -> None:
        unit = self.fuyuan
        if unit is None or not unit.alive or not self.enemies():
            return
        b = self.battle
        tough = self.toughness("talent", 1)
        with b.action(unit, ActionKind.FUA, skill=self.sk("talent"), label="Fuyuan", energy=0, sp=0) as act:
            act.aoe(self.p("talent", 1), toughness=tough)
            t = self._fire_target()
            if t is not None:
                # approximation: the extra single-target hit reduces Toughness like the AoE part
                act.hit(t, self.p("talent", 7), toughness=tough, primary=False)
            if self.e(6):
                for _ in range(int(self.ep(6, 1))):
                    t = self._fire_target()
                    if t is None:
                        break
                    act.hit(t, self.ep(6, 2), toughness=self.ep(6, 3), primary=False, label="Fuyuan (E6)")
        for c in self.allies():
            for m in c.debuffs[:1]:
                if m.dispellable:
                    b.remove_modifier(m)
            b.heal(c, self._heal_value(self.p("talent", 2), self.p("talent", 3)), self.char)
        if self.e(4):
            low = min(self.allies(), key=lambda c: c.hp_ratio, default=None)
            if low is not None:
                b.heal(low, self._heal_value(self.ep(4, 0), 0.0), self.char)
        if consume:
            self.count -= 1
            if self.count <= 0:
                self._dismiss()

    def _befog(self, e: Enemy, turns: int) -> None:
        self.battle.apply(
            Modifier(
                BEFOG,
                stats={f"{S.VULN}:{DmgTag.BREAK}": self.p("ult", 3)},
                duration=turns,
                kind=ModKind.DEBUFF,
                key=BEFOG,
            ),
            e,
            self.char,
        )

    # --------------------------------------------------------------- policy
    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        rot = self.opts.get("rotation", "auto")
        if rot == "basic" or not self.can_skill():
            self.basic(target)
        elif rot == "skill":
            self.skill(target)
        else:
            count = self.count if self.fuyuan_alive else 0
            if count + int(self.p("talent", 6)) <= int(self.p("talent", 4)):
                self.skill(target)
            else:
                self.basic(target)

    # --------------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.BASIC, "basic", target) as act:
            act.hit(target, self.p("basic", 0), toughness=self.toughness("basic"))
            if self.trace(2):
                act.energy += self.tp(2, 0)

    def skill(self, target: Enemy | None) -> None:
        with self.action(ActionKind.SKILL, "skill", target) as act:
            act.aoe(self.p("skill", 0), toughness=self.toughness("skill", 1), main_target=target)
            self._summon()
            self._heal_all(self.p("skill", 1), self.p("skill", 2))
        if self.fuyuan is not None and self.fuyuan.alive:
            self.battle.advance(self.fuyuan, self.p("skill", 3))

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult", target) as act:
            if self.e(2):
                for c in self.allies():
                    self.buff(
                        c,
                        Modifier(
                            "Leisure in Carmine Smokeveil",
                            stats={S.BREAK_EFFECT: self.ep(2, 0)},
                            duration=int(self.ep(2, 1)),
                        ),
                    )
            for e in self.enemies():
                self._befog(e, int(self.p("ult", 4)))
            act.aoe(self.p("ult", 0), toughness=self.toughness("ult", 1), main_target=target)
            self._heal_all(self.p("ult", 1), self.p("ult", 2))
        if self.fuyuan is not None and self.fuyuan.alive:
            self.battle.advance(self.fuyuan, self.p("ult", 5))
