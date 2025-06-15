from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List, Tuple

from data.enums import DamageSource
from engine.classes import Unit


class CombatStats:
    """Track per-unit combat statistics."""

    def __init__(self) -> None:
        self.data: Dict[str, Dict[str, Dict[str, float] | str]] = {}

    def reset(self) -> None:
        self.data.clear()

    def _ensure_unit(self, unit: Unit) -> None:
        if unit.id not in self.data:
            self.data[unit.id] = {
                "name": unit.name,
                "damage_dealt": defaultdict(float),
                "damage_taken": defaultdict(float),
                "healing_done": defaultdict(float),
            }

    def record_damage_dealt(
        self, unit: Unit, amount: float, source: DamageSource
    ) -> None:
        if amount <= 0:
            return
        self._ensure_unit(unit)
        self.data[unit.id]["damage_dealt"][source.name] += amount

    def record_damage_taken(
        self, unit: Unit, amount: float, source: DamageSource
    ) -> None:
        if amount <= 0:
            return
        self._ensure_unit(unit)
        self.data[unit.id]["damage_taken"][source.name] += amount

    def record_healing_done(
        self, unit: Unit, amount: float, source: DamageSource
    ) -> None:
        if amount <= 0:
            return
        self._ensure_unit(unit)
        self.data[unit.id]["healing_done"][source.name] += amount

    def sorted_units(
        self, metric: str
    ) -> List[Tuple[str, Dict[str, Dict[str, float] | str]]]:
        return sorted(
            self.data.items(),
            key=lambda it: sum(it[1][metric].values()),
            reverse=True,
        )

    def iter_units(self) -> Iterable[Tuple[str, Dict[str, Dict[str, float] | str]]]:
        return self.data.items()