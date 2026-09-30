"""Jing Yuan (景元) — Erudition / Lightning. Lightning-Lord: a summon whose SPD grows with its hit count."""

from __future__ import annotations

from .. import stats as S
from ..entities import Enemy, Summon
from ..enums import ActionKind, DmgTag
from ..modifiers import Modifier, ModKind, Stacking, Tick
from . import register
from .base import Kit

# Avatar_JingYuan_00_Skill02_Phase02: 40% on all enemies, then two random-animation hits of 30% on each enemy
# (the data snapshot has no splits for this skill because of the Retarget/RandomConfig wrapper)
SKILL_SPLITS = [0.4, 0.3, 0.3]


@register
class JingYuan(Kit):
    char_id = "1204"

    def setup(self) -> None:
        self.base_hits = int(self.p("talent", 3))
        self.hits = self.base_hits
        self.ll: Summon | None = None

    def on_battle_start(self) -> None:
        self.ll = self.battle.add_unit(
            Summon("Lightning-Lord", self.char, spd=self.p("talent", 0), on_turn=self._ll_turn)
        )
        self._set_hits(self.base_hits)
        if self.trace(2):  # MAvatar_JingYuan_00_SkillTree02: ModifySPNew AddValue (ERR-scaled)
            self.battle.gain_energy(self.char, self.tp(2, 0))

    def technique(self) -> None:
        self.add_hits(int(self.sk("technique")["params"][0][0]))

    # -------------------------------------------------------- Lightning-Lord
    def _set_hits(self, n: int) -> None:
        self.hits = max(self.base_hits, min(int(self.p("talent", 5)), n))
        if self.ll is not None:
            self.ll.base[S.BASE_SPD] = self.p("talent", 0) + self.p("talent", 2) * (self.hits - self.base_hits)

    def add_hits(self, n: int) -> None:
        self._set_hits(self.hits + n)

    def _ll_turn(self, unit: Summon, battle: object) -> None:
        b = self.battle
        n = self.hits
        if self.trace(1) and n >= self.tp(1, 0):
            # Avatar_JingYuan_00_Passive_Insert_Ability: MAvatar_JingYuan_00_CriticalDamageUp (LifeTime=1) is added to
            # the ability's Caster, Jing Yuan himself (the same Caster that holds the hit counter), before the hits.
            # Applied outside his turn, it lasts until the end of his next turn and also buffs that turn's action.
            self.buff_self(Modifier("Battalia Crush", stats={S.CRIT_DMG: self.tp(1, 1)}, duration=1))
        adj_ratio = self.p("talent", 4) + (self.ep(1, 0) if self.e(1) else 0.0)
        main = self.p("talent", 1)
        with b.action(unit, ActionKind.FUA, skill=self.sk("talent"), label="Lightning-Lord", energy=0, sp=0) as act:
            for _ in range(n):
                enemies = [e for e in b.alive_enemies() if e.hp > 0] or b.alive_enemies()
                if not enemies:
                    break
                t = b.rng.choice(enemies)
                act.hit(t, main, toughness=self.toughness("talent"), tags=(DmgTag.FUA,))
                for a in b.adjacent(t):
                    act.hit(a, main * adj_ratio, tags=(DmgTag.FUA,), primary=False)
                if self.e(4):
                    b.gain_energy(self.char, self.ep(4, 0))
                if self.e(6) and t.alive:
                    b.apply(
                        Modifier(
                            "Sweep, Souls Slain",
                            stats={S.VULN: self.ep(6, 0)},
                            kind=ModKind.DEBUFF,
                            stacking=Stacking.STACK,
                            max_stacks=int(self.ep(6, 1)),
                            tick=Tick.NONE,
                            key="JY E6",
                        ),
                        t,
                        self.char,
                    )
        if self.e(6):
            for e in b.alive_enemies():
                b.remove_named(e, "Sweep, Souls Slain")
        self._set_hits(self.base_hits)
        if self.e(2):
            self.buff_self(
                Modifier(
                    "Swing, Skies Squashed",
                    stats={f"{S.DMG_PCT}:{t}": self.ep(2, 0) for t in ("basic", "skill", "ult")},
                    duration=int(self.ep(2, 1)),
                )
            )

    # ------------------------------------------------------------ actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        self.simple_basic(target)

    def skill(self, target: Enemy | None) -> None:
        with self.action(ActionKind.SKILL, "skill", target) as act:
            act.aoe(self.p("skill", 0), toughness=self.toughness("skill", 1), main_target=target, splits=SKILL_SPLITS)
        self.add_hits(int(self.p("skill", 1)))
        if self.trace(3):
            self.buff_self(Modifier("War Marshal", stats={S.CRIT_RATE: self.tp(3, 0)}, duration=int(self.tp(3, 1))))

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult", target) as act:
            act.aoe(self.p("ult", 0), toughness=self.toughness("ult", 1), main_target=target, splits="data")
        self.add_hits(int(self.p("ult", 1)))
