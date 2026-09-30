"""The Herta (大黑塔) — Erudition / Ice. "Interpretation" stacks on enemies power up her Enhanced Skill
("Hear Me Out", unlocked by "Inspiration" from her Ultimate); spreading Skill hits.

Options (``default_opts``):
  * ``rotation``: ``"skill"`` (Enhanced Skill / Skill whenever SP allows, default) or ``"basic"``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .. import events as E
from .. import stats as S
from ..entities import Character, Enemy
from ..enums import ActionKind, EnemyRank, Path, Side
from ..modifiers import Modifier, ModKind, Stacking, Tick
from . import register
from .base import Kit

if TYPE_CHECKING:
    from ..battle import Action

INTERPRETATION = "Interpretation"
MAX_TARGETS_FOR_ENERGY = 5  # A2 "counting up to a maximum of 5 targets" (literal)
SPREAD_INSTANCES = 3  # Skill: one hit + "This effect can repeat 2 times" (literal)


def _elite(e: Enemy) -> bool:
    return e.rank in (EnemyRank.ELITE, EnemyRank.BOSS)


@register
class TheHerta(Kit):
    char_id = "1401"
    default_opts = {"rotation": "skill"}

    def setup(self) -> None:
        self.inspiration = 0
        self.answers = 0
        self.eru = sum(1 for c in self.battle.team if c.path == Path.ERUDITION)
        self.a4 = self.trace(2) and self.eru >= 2
        self.on(E.ENEMY_SPAWNED, lambda ev: self.add_interp(ev.enemy, 1))
        self.on(E.WAVE_START, self._wave_start)
        self.on(E.KILL, self._transfer)
        self.on(E.ATTACK_END, self._on_attack_end)
        if self.a4:
            self.passive("Message From Beyond the Veil", {S.CRIT_DMG: self.tp(2, 0)}, scope=self.ally_scope)
        if self.e(4):
            self.passive(
                "The Sixteenth Key",
                {S.SPD_PCT: self.ep(4, 0)},
                scope=lambda e: isinstance(e, Character) and e.path == Path.ERUDITION,
            )
        if self.e(6):
            self.passive("Sweet Lure of Answer", {f"{S.RES_PEN}:{self.char.element.value}": self.ep(6, 3)})

    def on_battle_start(self) -> None:
        if self.e(2):
            self._gain_inspiration(1)

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        self.buff_self(Modifier("Vibe Checker", stats={S.ATK_PCT: p[0]}, duration=int(p[1])))

    # ------------------------------------------------------- Interpretation
    @staticmethod
    def stacks(e: Enemy) -> int:
        m = e.get_mod(INTERPRETATION)
        return m.stacks if m is not None else 0

    def add_interp(self, e: Enemy, n: int) -> None:
        if n <= 0 or not e.alive:
            return
        self.battle.apply(
            Modifier(
                INTERPRETATION,
                kind=ModKind.OTHER,
                stacks=n,
                max_stacks=int(self.p("talent", 2)),
                stacking=Stacking.STACK,
                tick=Tick.NONE,
                dispellable=False,
                key=INTERPRETATION,
            ),
            e,
            self.char,
        )
        if self.trace(3):
            self.answers = min(int(self.tp(3, 1)), self.answers + n)

    def set_interp(self, e: Enemy, n: int) -> None:
        m = e.get_mod(INTERPRETATION)
        if m is None:
            self.add_interp(e, n)
        elif n <= 0:
            self.battle.remove_modifier(m)
        else:
            m.stacks = min(m.max_stacks, n)

    def _priority(self, pool: list[Enemy]) -> list[Enemy]:
        elites = [e for e in pool if _elite(e)]
        return elites or pool

    def _wave_start(self, ev: E.Ev) -> None:
        pool = self._priority(self.enemies())
        if pool:
            self.add_interp(self.battle.rng.choice(pool), int(self.p("talent", 5)))

    def _transfer(self, ev: E.Ev) -> None:
        n = self.stacks(ev.target)
        others = [e for e in self.enemies() if e is not ev.target and e.hp > 0]
        if n and others:
            dest = max(self._priority(others), key=lambda e: e.max_hp)
            self.add_interp(dest, n)

    def _on_attack_end(self, ev: E.Ev) -> None:
        act = ev.attack
        owner = act.owner
        if owner is None or owner.side != Side.ALLY or not act.attacked:
            return
        hit = [t for t in act.attacked if t.alive]
        if self.trace(1):
            for t in hit:
                self.add_interp(t, 1)
            n = len(act.attacked)
            if self.a4:
                n = max(n, int(self.tp(2, 1)))
            self.battle.gain_energy(self.char, self.tp(1, 0) * min(MAX_TARGETS_FOR_ENERGY, n), fixed=True)
        if self.a4 and hit:
            top = max(hit, key=self.stacks)
            eru = isinstance(owner, Character) and owner.path == Path.ERUDITION
            self.add_interp(top, int(self.tp(2, 2)) + (int(self.tp(2, 3)) if eru else 0))

    def _gain_inspiration(self, n: int) -> None:
        self.inspiration = min(int(self.p("ult", 5)), self.inspiration + n)

    # ------------------------------------------------------------- policy
    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        if self.opts.get("rotation", "skill") == "skill" and self.can_skill():
            if self.inspiration > 0:
                best = max(self.enemies(), key=lambda e: (self.stacks(e), e.max_hp))
                self.skill(best)
            else:
                self.skill(target)
        else:
            self.basic(target)

    # ------------------------------------------------------------ actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        self.simple_basic(target)

    def _rings(self, target: Enemy) -> list[list[Enemy]]:
        """Targets of the spreading Skill instances: main, + adjacent, + their adjacent."""
        rings = [[target]]
        seen = {target.uid}
        for _ in range(SPREAD_INSTANCES - 1):
            nxt = []
            for t in rings[-1]:
                for a in self.battle.adjacent(t):
                    if a.uid not in seen:
                        seen.add(a.uid)
                        nxt.append(a)
            rings.append(nxt)
        return rings

    def _spread(
        self,
        act: Action,
        target: Enemy,
        mult: float,
        tough_main: float,
        tough_other: float,
        bonus: tuple[float, float] = (0.0, 0.0),
        extra: dict[str, float] | None = None,
    ) -> None:
        """Main target: 3 instances, adjacent targets: 2, targets adjacent to those: 1.

        # approximation: the data's Toughness values are per-target totals (main / adjacent); they are split
        # evenly over the instances (targets two steps away take one adjacent-sized instance). The
        # Interpretation multiplier bonus is added once, to the first instance on each target."""
        rings = self._rings(target)
        first_hit: set[int] = set()
        for i in range(SPREAD_INSTANCES):
            for ring_no, ring in enumerate(rings[: i + 1]):
                for t in ring:
                    if not t.alive:
                        continue
                    tough = tough_main / SPREAD_INSTANCES if ring_no == 0 else tough_other / (SPREAD_INSTANCES - 1)
                    m = mult
                    if t.uid not in first_hit:
                        first_hit.add(t.uid)
                        m += bonus[0] if t is target else bonus[1]
                    act.hit(t, m, toughness=tough, extra=extra, primary=t is target)

    def skill(self, target: Enemy | None) -> None:
        assert target is not None
        if self.inspiration > 0:
            self._enhanced_skill(target)
            return
        with self.action(ActionKind.SKILL, "skill", target) as act:
            self._spread(act, target, self.p("skill", 0), self.toughness("skill", 0), self.toughness("skill", 2))
            self.add_interp(target, int(self.p("skill", 1)))

    def counted_stacks(self, target: Enemy) -> float:
        n = float(self.stacks(target))
        if self.e(1):
            pool = [target, *self.battle.adjacent(target)]
            n += self.ep(1, 0) * max(self.stacks(e) for e in pool)
        return n

    def _enhanced_skill(self, target: Enemy) -> None:
        rec = self.sk("140109")
        lv = rec["params"][self.level_of(rec) - 1]
        tough = rec["toughness"]
        self.inspiration -= 1
        counted = self.counted_stacks(target)
        k = 2 if self.eru >= 2 else 1
        bonus = (self.p("talent", 0) * counted * k, self.p("talent", 1) * counted * k)
        extra: dict[str, float] = {}
        if self.trace(1) and counted >= self.p("talent", 2):
            extra[f"{S.DMG_PCT}:{self.char.element.value}"] = self.tp(1, 1)
        with self.action(ActionKind.SKILL, rec, target) as act:
            self._spread(act, target, lv[0], float(tough[0]), float(tough[2]), bonus, extra or None)
            act.aoe(lv[2], main_target=target, extra=extra or None)
            self.add_interp(target, int(lv[1]))
            self.set_interp(target, int(self.ep(1, 1)) if self.e(1) else 1)
        if self.e(2):
            self.battle.advance(self.char, self.ep(2, 0))

    def ult(self, target: Enemy | None) -> None:
        b = self.battle
        enemies = self.enemies()
        stacks = sorted((self.stacks(e) for e in enemies), reverse=True)
        order = sorted(enemies, key=lambda e: (not _elite(e), -e.max_hp))
        for e, n in zip(order, stacks, strict=False):
            self.set_interp(e, n)
        mult = self.p("ult", 0)
        if self.trace(3):
            mult += self.tp(3, 0) * self.answers
        if self.e(6):
            n = len(enemies)
            mult += self.ep(6, 2) if n <= 1 else self.ep(6, 1) if n == 2 else self.ep(6, 0)
        self.buff_self(
            Modifier("Told Ya! Magic Happens", stats={S.ATK_PCT: self.p("ult", 3)}, duration=int(self.p("ult", 4)))
        )
        with self.action(ActionKind.ULT, "ult", target) as act:
            act.aoe(mult, toughness=self.toughness("ult", 1), main_target=target)
        self._gain_inspiration(1 + (1 if self.e(2) else 0))
        b.advance(self.char, 1.0)
