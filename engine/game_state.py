# engine/game_state.py
# forward declarations for type hints
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

import engine.classes as engine_classes
from data.enums import TriggerTiming
# from states.enums import GamePhase, UnitLocation # Cannot import yet, circular dependency risk
from engine.classes import (
    DamageFloater,
    GameMap,
    Item,
    Player,
    Shop,
    Unit,
    VisualEffect,
)
from engine.combat_stats import CombatStats

if TYPE_CHECKING:
    from states.enums import GamePhase, UnitLocation
    from engine.classes import Item, Unit

    SelectedUnitInfo = tuple["UnitLocation", Union[int, tuple[int, int]], "Unit"]
    SelectedItemInfo = tuple["UnitLocation", Union[int, "SelectedUnitInfo"], "Item"]
# Type Alias - Define here as they relate directly to GameState structure
SynergyStatus = Dict[
    str, Dict[str, Union[int, List[str]]]
]  # {"count": X, "level_index": Y, "units": [names]}
Buff = Dict[str, Any]  # {stat, value, duration, timestamp, source_id, is_percent}
EventChoice = Dict[
    str, Any
]  # {text, apply_func, display_rect_key} -> rect key to be used by UI

# UI needs these:
# SelectedUnitInfo = Tuple[UnitLocation, Union[int, Tuple[int, int]], Unit]
# SelectedItemInfo = Tuple[UnitLocation, Union[int, SelectedUnitInfo], Item] # loc, index_or_unit_info, item

@dataclass
class TriggerEvent:
    unit: "Unit"
    timing: "TriggerTiming"
    event_target: "Unit | None"
    data: Dict[str, Any]

class GameState:
    def __init__(self):
        self.player = Player()
        self.shop = Shop()
        self.game_map = GameMap()
        # Using string type hint to avoid circular import during refactor
        self.current_phase: "GamePhase" = None  #  Set in main/reset
        self.previous_phase: "GamePhase" | None = None
        self.volume: float = 0.6
        self.resolution_options: list[tuple[int, int]] = [
            (1920, 1080),
            (1600, 900),
            (1280, 720),
        ]
        self.resolution_index: int = 0

        # --- Selections / UI State (Managed by states/input, read by ui/drawing) ---
        # Using string type hint
        self.selected_unit_info: Optional["SelectedUnitInfo"] = None
        self.selected_item_info: Optional["SelectedItemInfo"] = None
        self.hovered_info: Optional[str] = None
        # UI will manage the actual rects, engine just stores info text
        # self.hovered_rect: Optional[pygame.Rect] = None # MOVED TO UI
        # self.hovered_button_rect: Optional[pygame.Rect] = None # MOVED TO UI
        # -------------------------------------------------------------------------

        self.combat_timer: float = 0.0
        self.overtime_damage_timer: float = 0.0
        self.delta_time_combat: float = 0.0
        self.player_combat_team: List[Unit] = []
        self.enemy_combat_team: List[Unit] = []
        self.damage_floaters: List[DamageFloater] = []
        self.visual_effects: List[VisualEffect] = []
        self.current_node_id: int = self.game_map.start_node_id
        self.allow_combat_start: bool = False
        self.current_node_type: str = ""
        self.prepare_ui_message: str = ""
        self.difficulty_level: str = "easy"
        self.nodes_cleared: int = 0
        self.act: int = 1
        self.available_themes: list[str] = ["MECHANICAL", "FROST", "ARCANE", "DESERT"]
        self.chosen_themes: list[str] = []
        self.current_theme: str | None = None
        self.enemy_combat_team_data_cache: List[Dict] = []
        self.enemy_preview_units: List[Unit] = []
        self.enemy_preview_positions: List[tuple[int, int]] = []
        self.event_choices: List[EventChoice] = []
        self.combat_stats = CombatStats()
        self.pending_triggers: deque[TriggerEvent] = deque()
        self.player_total_damage: float = 0.0
        self.enemy_total_damage: float = 0.0
        self.player_next_damage_threshold: float = 100.0
        self.enemy_next_damage_threshold: float = 100.0
        # Button rects belong in UI/States, not engine state.
    def queue_trigger(
        self,
        unit: "Unit",
        timing: TriggerTiming,
        event_target: "Unit | None" = None,
        data: Dict[str, Any] | None = None,
    ) -> None:
        self.pending_triggers.append(
            TriggerEvent(unit, timing, event_target, data or {})
        )

    def process_triggers(self) -> None:
        while self.pending_triggers:
            event = self.pending_triggers.popleft()
            if engine_classes.resolve_trigger_func:
                engine_classes.resolve_trigger_func(
                    event.unit,
                    event.timing,
                    self,
                    event.event_target,
                    event.data,
                )
    def record_team_damage(self, source: Unit, amount: float) -> None:
        if amount <= 0:
            return
        is_enemy = source.is_enemy
        if is_enemy:
            self.enemy_total_damage += amount
            if self.enemy_total_damage >= self.enemy_next_damage_threshold:
                self.enemy_next_damage_threshold *= 2
                self._trigger_team_damage_doubled(True)
        else:
            self.player_total_damage += amount
            if self.player_total_damage >= self.player_next_damage_threshold:
                self.player_next_damage_threshold *= 2
                self._trigger_team_damage_doubled(False)

    def _trigger_team_damage_doubled(self, enemy_team: bool) -> None:
        team = self.enemy_combat_team if enemy_team else self.player_combat_team
        if not team:
            return
        # Determine highest damage dealer
        top_unit: Unit | None = None
        top_damage = -1.0
        for u in team:
            if not u.is_alive:
                continue
            dmg = sum(
                self.combat_stats.data.get(u.id, {}).get("damage_dealt", {}).values()
            )
            if dmg > top_damage:
                top_damage = dmg
                top_unit = u
        if not top_unit:
            return
        from data.enums import TriggerTiming

        for u in team:
            if (
                u.is_alive
                and u.trigger
                and u.trigger.get("timing_type") == TriggerTiming.ON_TEAM_DAMAGE_DOUBLED
            ):
                count = u.trigger_counts[TriggerTiming.ON_TEAM_DAMAGE_DOUBLED]
                self.queue_trigger(
                    u,
                    TriggerTiming.ON_TEAM_DAMAGE_DOUBLED,
                    event_target=top_unit,
                    data={"count": count + 1},
                )
                u.trigger_counts[TriggerTiming.ON_TEAM_DAMAGE_DOUBLED] += 1


# Global state instance
run_state: Optional[GameState] = None


def reset_game_state(difficulty_level: str = "easy"):
    # Needs to be called by main after all modules imported
    global run_state
    from states.enums import GamePhase  # Local import

    print("\n======= RESET GAME STATE / NEW RUN =======\n")
    run_state = GameState()
    run_state.difficulty_level = difficulty_level
    run_state.current_phase = GamePhase.MAP_NAVIGATION
    # Ensure map generation happens on reset
    run_state.game_map = GameMap()
    run_state.current_node_id = run_state.game_map.start_node_id


def get_game_state() -> GameState:
    global run_state
    if run_state is None:
        # Initialize state but don't set phase to allow MAIN_MENU start
        run_state = GameState()
    return run_state