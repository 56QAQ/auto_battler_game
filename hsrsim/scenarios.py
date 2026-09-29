"""Enemy specs and scenario presets.

Enemy stats are parameters, not a claim about a specific endgame lineup: set HP,
Toughness, weaknesses and RES to match the fight you want to study.
"""

from __future__ import annotations

import copy
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from typing import Any

from .battle import Battle, BattleConfig
from .build import Build, make_character
from .entities import Enemy
from .enums import Element, EnemyRank
from .report import Report

ALL_ELEMENTS = tuple(Element)


def parse_elements(xs: Iterable[str | Element] | str) -> list[Element]:
    if isinstance(xs, str):
        if xs.lower() in ("all", "*"):
            return list(ALL_ELEMENTS)
        xs = [x.strip() for x in xs.split(",") if x.strip()]
    out = []
    for x in xs:
        if isinstance(x, Element):
            out.append(x)
            continue
        low = x.lower()
        match = [e for e in Element if e.value.lower() == low or e.name.lower() == low or e.cn == x]
        if not match:
            raise ValueError(f"unknown element {x!r}")
        out.append(match[0])
    return out


@dataclass
class EnemySpec:
    name: str = "Enemy"
    level: int = 95
    hp: float = 1_000_000.0
    atk: float = 1500.0
    spd: float = 150.0
    toughness: float = 100.0
    weaknesses: list[str] | str = "all"
    res: dict[str, float] = field(default_factory=dict)
    default_res: float = 0.2
    weak_res: float = 0.0
    effect_res: float = 0.3
    rank: str = "elite"
    count: int = 1
    debuff_res: dict[str, float] = field(default_factory=dict)

    def make(self) -> list[Enemy]:
        res = {parse_elements([k])[0]: v for k, v in self.res.items()}
        out = []
        for i in range(self.count):
            name = self.name if self.count == 1 else f"{self.name} {i + 1}"
            out.append(
                Enemy(
                    name,
                    level=self.level,
                    hp=self.hp,
                    atk=self.atk,
                    spd=self.spd,
                    toughness=self.toughness,
                    weaknesses=parse_elements(self.weaknesses),
                    res=res,
                    default_res=self.default_res,
                    weak_res=self.weak_res,
                    effect_res=self.effect_res,
                    rank=EnemyRank(self.rank),
                    debuff_res=self.debuff_res,
                )
            )
        return out


@dataclass
class Scenario:
    name: str
    waves: list[list[EnemySpec]]
    max_cycles: int | None = None
    max_av: float | None = None
    config: dict[str, Any] = field(default_factory=dict)
    description: str = ""

    def make_waves(self) -> list[list[Enemy]]:
        return [[e for spec in wave for e in spec.make()] for wave in self.waves]

    def run(self, team: list[Build], seed: int = 0, verbose: bool = False, **cfg: Any) -> Report:
        conf = BattleConfig(**{**self.config, **cfg, "seed": seed})
        chars = [make_character(copy.deepcopy(b)) for b in team]
        battle = Battle(chars, self.make_waves(), conf)
        battle.verbose = verbose
        return battle.run(max_av=self.max_av, max_cycles=self.max_cycles)

    def with_weakness(self, elements: Iterable[str | Element] | str) -> Scenario:
        waves = [[replace(s, weaknesses=[e.value for e in parse_elements(elements)]) for s in w] for w in self.waves]
        return replace(self, waves=waves)


def boss_dps(cycles: int = 5, weaknesses: str | list[str] = "all", **enemy: Any) -> Scenario:
    """Single high-HP boss; total DMG after ``cycles`` cycles (single-target output)."""
    spec = EnemySpec(
        name="Boss", hp=enemy.pop("hp", 1e12), toughness=enemy.pop("toughness", 300.0), rank="boss",
        weaknesses=weaknesses, **enemy,
    )
    return Scenario(f"boss_dps_{cycles}c", [[spec]], max_cycles=cycles, description=boss_dps.__doc__ or "")


def aoe_dps(cycles: int = 5, count: int = 5, weaknesses: str | list[str] = "all", **enemy: Any) -> Scenario:
    """``count`` high-HP elites side by side (blast / AoE output)."""
    spec = EnemySpec(
        name="Elite", hp=enemy.pop("hp", 1e12), toughness=enemy.pop("toughness", 100.0), rank="elite",
        count=count, weaknesses=weaknesses, **enemy,
    )
    return Scenario(f"aoe_dps_{cycles}c", [[spec]], max_cycles=cycles, description=aoe_dps.__doc__ or "")


def clear_waves(
    waves: list[list[EnemySpec]] | None = None, max_cycles: int = 30, weaknesses: str | list[str] = "all"
) -> Scenario:
    """MoC-style: clear all waves as fast as possible; the report shows cycles used."""
    if waves is None:
        waves = [
            [
                EnemySpec("Minion", hp=300_000, toughness=60, rank="normal", count=2, weaknesses=weaknesses),
                EnemySpec("Elite", hp=1_200_000, toughness=160, rank="elite", weaknesses=weaknesses),
            ],
            [
                EnemySpec("Minion", hp=300_000, toughness=60, rank="normal", count=2, weaknesses=weaknesses),
                EnemySpec("Boss", hp=3_000_000, toughness=300, rank="boss", weaknesses=weaknesses),
            ],
        ]
    return Scenario("clear_waves", waves, max_cycles=max_cycles, description=clear_waves.__doc__ or "")


PRESETS = {
    "boss": boss_dps,
    "aoe": aoe_dps,
    "waves": clear_waves,
}
