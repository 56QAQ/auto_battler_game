# engine/game_state.py
# forward declarations for type hints
from __future__ import annotations 
from typing import List, Dict, Tuple, Optional, Any, Union, Callable
# from states.enums import GamePhase, UnitLocation # Cannot import yet, circular dependency risk
from engine.classes import Player, Shop, GameMap, Unit, Item, Artifact, DamageFloater, VisualEffect

# Type Alias - Define here as they relate directly to GameState structure
SynergyStatus = Dict[str, Dict[str, Union[int, List[str]]]] # {"count": X, "level_index": Y, "units": [names]}
Buff = Dict[str, Any] # {stat, value, duration, timestamp, source_id, is_percent}
EventChoice = Dict[str, Any] # {text, apply_func, display_rect_key} -> rect key to be used by UI

# UI needs these:
# SelectedUnitInfo = Tuple[UnitLocation, Union[int, Tuple[int, int]], Unit]
# SelectedItemInfo = Tuple[UnitLocation, Union[int, SelectedUnitInfo], Item] # loc, index_or_unit_info, item

class GameState:
     def __init__(self):
        self.player = Player()
        self.shop = Shop()
        self.game_map = GameMap()
        # Using string type hint to avoid circular import during refactor
        self.current_phase: 'GamePhase' = None #  Set in main/reset
        
        # --- Selections / UI State (Managed by states/input, read by ui/drawing) ---
        # Using string type hint
        self.selected_unit_info: Optional['SelectedUnitInfo'] = None
        self.selected_item_info: Optional['SelectedItemInfo'] = None 
        self.hovered_info: Optional[str] = None
        # UI will manage the actual rects, engine just stores info text
        # self.hovered_rect: Optional[pygame.Rect] = None # MOVED TO UI
        # self.hovered_button_rect: Optional[pygame.Rect] = None # MOVED TO UI
         # -------------------------------------------------------------------------
        
        self.combat_timer : float = 0.0
        self.overtime_damage_timer: float = 0.0 
        self.delta_time_combat : float = 0.0 
        self.player_combat_team : List[Unit] = []
        self.enemy_combat_team : List[Unit] = []
        self.damage_floaters: List[DamageFloater] = [] 
        self.visual_effects: List[VisualEffect] = [] 
        self.current_node_id : int = self.game_map.start_node_id
        self.allow_combat_start: bool = False 
        self.current_node_type: str = ""
        self.prepare_ui_message: str = ""
        self.enemy_combat_team_data_cache: List[Dict] = [] 
        self.event_choices: List[EventChoice] = [] 
        # Button rects belong in UI/States, not engine state.

# Global state instance
run_state: Optional[GameState] = None

def reset_game_state():
    # Needs to be called by main after all modules imported
    global run_state
    from states.enums import GamePhase # Local import
    print("\n======= RESET GAME STATE / NEW RUN =======\n")
    run_state = GameState()
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