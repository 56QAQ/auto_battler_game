from __future__ import annotations

import random
import uuid
from typing import TYPE_CHECKING, Set

if TYPE_CHECKING:
    from engine.game_state import GameState


class SteamCloudArea:
    """Temporary field that penalises accuracy for units inside it."""

    def __init__(
        self,
        x: float,
        y: float,
        radius: float,
        duration: float,
        accuracy_penalty: float,
    ) -> None:
        self.x = x
        self.y = y
        self.radius = radius
        self.duration = duration
        self.remaining = duration
        self.elapsed = 0.0
        self.accuracy_penalty = accuracy_penalty
        self._affected: Set[str] = set()
        self._source_id = f"STEAM_CLOUD_{uuid.uuid4()}"
        self.puff_offsets = [
            (0.0, 0.0),
            *[
                (
                    random.uniform(-0.45, 0.45),
                    random.uniform(-0.45, 0.45),
                )
                for _ in range(3)
            ],
        ]

    def update(self, state: "GameState", dt: float) -> None:
        self.remaining -= dt
        self.elapsed += dt
        radius_sq = self.radius * self.radius
        units = state.player_combat_team + state.enemy_combat_team
        current: Set[str] = set()
        for unit in units:
            if not unit.is_alive:
                continue
            dx = unit.x - self.x
            dy = unit.y - self.y
            if dx * dx + dy * dy > radius_sq:
                continue
            current.add(unit.id)
            unit.add_stat_modifier(
                "accuracy",
                self.accuracy_penalty,
                0.2,
                self._source_id,
                True,
            )
        if self._affected:
            for unit in units:
                if unit.id in self._affected and unit.id not in current:
                    unit.remove_buffs_from_source(self._source_id)
                elif not unit.is_alive and unit.id in self._affected:
                    unit.remove_buffs_from_source(self._source_id)
        self._affected = current

    def is_expired(self) -> bool:
        return self.remaining <= 0.0

    def cleanup(self, state: "GameState") -> None:
        if not self._affected:
            return
        units = state.player_combat_team + state.enemy_combat_team
        for unit in units:
            if unit.id in self._affected:
                unit.remove_buffs_from_source(self._source_id)
        self._affected.clear()
