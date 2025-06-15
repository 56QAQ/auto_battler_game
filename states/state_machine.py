import random
from typing import Any, Dict, List, Optional

import pygame  # Only for Rect creation in events

from data.constants import MAX_COMBAT_DURATION
from data.definitions import (ENEMY_TEAM_DEFINITIONS, ITEM_DEFINITIONS,
                              POSSIBLE_EVENT_ARTIFACTS, POSSIBLE_EVENT_ITEMS,
                              SYNERGY_DEFINITIONS)
from data.enums import TriggerTiming
from engine.classes import Artifact, Item, Player
from engine.game_state import GameState, reset_game_state
from engine.logic import (add_item_to_inventory, apply_artifact_buffs,
                          apply_artifact_effect, apply_synergy_buffs,
                          calculate_active_synergies, create_enemy_units,
                          give_node_rewards, remove_synergy_buffs,
                          resolve_trigger, setup_combat_team,
                          setup_enemy_combat_team, update_player_synergies,resolve_passive)
from states.enums import GamePhase
from ui.constants import (EVENT_BUTTON_HEIGHT, EVENT_BUTTON_WIDTH,
                          EVENT_CHOICE_RECT)
from ui.ui_context import UIContext
from ui.layout_manager import LayoutManager

# State Transition Functions
def go_to_main_menu(state: GameState):
    state.current_phase = GamePhase.MAIN_MENU


def start_new_run(state: GameState, difficulty_level: str | None = None):
    # Must return the NEW state instance
    from engine.game_state import get_game_state
    if difficulty_level is None:
        difficulty_level = getattr(state, "difficulty_level", "medium")
    reset_game_state(difficulty_level)
    return get_game_state()


def start_combat(state: GameState, enemy_team_data: List[Dict]):
    print("\n--- COMBAT START ---")
    state.combat_stats.reset()
    state.current_phase = GamePhase.COMBAT
    state.combat_timer = 0
    state.overtime_damage_timer = 0
    state.damage_floaters = []
    state.visual_effects = []
    enemy_units = create_enemy_units(enemy_team_data, state)
    state.player_combat_team = setup_combat_team(state.player, is_enemy=False)
    state.enemy_combat_team = setup_enemy_combat_team(enemy_units)

    apply_artifact_buffs(
        state.player_combat_team, state.player.artifacts, state.combat_timer
    )
    apply_artifact_buffs(state.enemy_combat_team, [], state.combat_timer)
    apply_synergy_buffs(
        state.player_combat_team, state.player.active_synergies, state.combat_timer
    )

    enemy_active_synergies = calculate_active_synergies(
        type(
            "obj",
            (object,),
            {"board": {i: u for i, u in enumerate(state.enemy_combat_team)}},
        )()
    )
    apply_synergy_buffs(
        state.enemy_combat_team, enemy_active_synergies, state.combat_timer
    )

    all_units = state.player_combat_team + state.enemy_combat_team
    for unit in all_units:
        resolve_trigger(unit, TriggerTiming.START_OF_COMBAT, state, event_target=None)
        resolve_passive(unit, TriggerTiming.START_OF_COMBAT, state, event_target=None)

def end_combat(
    state: GameState,
    player_won: bool,
    damage_taken: int = 0,
    overtime_loss: bool = False,
):
    print(
        f"--- COMBAT END: Player {'WON' if player_won else 'LOST'} ({state.combat_timer:.1f}s / {MAX_COMBAT_DURATION}) {'OVERTIME' if overtime_loss else ''}---"
    )
    remove_synergy_buffs(state.player.get_board_units())
    update_player_synergies(state.player)
    state.player_combat_team = []
    state.enemy_combat_team = []
    state.player.health -= damage_taken
    state.player.health = max(0, state.player.health)
    print(f"DEBUG: Player Health: {state.player.health}")
    current_node = state.game_map.get_node(state.current_node_id)
    node_type = current_node.node_type if current_node else "UNKNOWN"
    if current_node and not overtime_loss:
        give_node_rewards(state, node_type, player_won)
        current_node.visited = True
        current_node.completed = True
        if player_won and "COMBAT" in node_type:
            state.nodes_cleared += 1
    elif overtime_loss and not player_won:  # Only XP if player lost due to time
        # state.player.gain_xp(PASSIVE_XP) # Removed: give_node_rewards handles passive xp
        give_node_rewards(state, node_type, player_won=False)  # get passive XP only

    if state.player.health <= 0:
        state.current_phase = GamePhase.GAME_OVER
        print("--- GAME OVER ---")
    elif player_won and node_type == "BOSS":
        # BOSS 击败：推进幕流程
        state.nodes_cleared += 1
        if state.act < 4:
            state.act += 1
            from engine.classes import GameMap
            state.game_map = GameMap()             # 新地图
            state.current_node_id = state.game_map.start_node_id
            state.allow_combat_start = False
            # 幕 2、3 进入主题选择
            if state.act in (2, 3):
                state.current_phase = GamePhase.THEME_SELECT
            else:  # 幕 4 直接继续
                state.current_phase = GamePhase.MAP_NAVIGATION
        else:
            state.current_phase = GamePhase.RUN_COMPLETE
            print("--- RUN COMPLETE ---")
            state.allow_combat_start = False
    else:
        state.current_phase = GamePhase.MAP_NAVIGATION
        state.allow_combat_start = False


def go_to_map(state: GameState):
    current_node = state.game_map.get_node(state.current_node_id)
    if current_node and not current_node.completed:
        current_node.completed = True
    state.current_phase = GamePhase.MAP_NAVIGATION
    state.allow_combat_start = False  # Ensure button state is correct


def setup_event_choice(state: GameState, context: UIContext):
    print("\n--- ENTER EVENT PHASE ---")
    state.current_phase = GamePhase.EVENT_CHOICE
    state.event_choices = []
    player = state.player
    choices_data = []
    item_name = random.choice(POSSIBLE_EVENT_ITEMS)
    choices_data.append(
        {
            "text": f"Receive Item: {item_name}",
            "apply_func": lambda p: add_item_to_inventory(p, Item(item_name)),
        }
    )
    available_arts = [
        a
        for a in POSSIBLE_EVENT_ARTIFACTS
        if not any(pa.name == a for pa in player.artifacts)
    ]
    art_name = random.choice(available_arts or ["Lucky Coin"])
    choices_data.append(
        {
            "text": f"Receive Artifact: {art_name}",
            # Need to add to artifacts list AND apply effect
            "apply_func": lambda p, an=art_name: (
                apply_artifact_effect(p, Artifact(an)),
                (
                    p.artifacts.append(Artifact(an))
                    if an not in [x.name for x in p.artifacts]
                    else None
                ),
            ),
        }
    )
    choices_data.append(
        {
            "text": f"Trade 10 HP for 15 Gold",
            "apply_func": lambda p: setattr(p, "health", max(1, p.health - 10))
            or setattr(p, "gold", p.gold + 15),
        }
    )
    random.shuffle(choices_data)
    final_choices = choices_data[:3]
    start_y = (
        EVENT_CHOICE_RECT.centery
        - (len(final_choices) * (EVENT_BUTTON_HEIGHT + 10)) // 2
    )
    for i, data in enumerate(final_choices):
        rect = pygame.Rect(
            EVENT_CHOICE_RECT.centerx - EVENT_BUTTON_WIDTH // 2,
            start_y + i * (EVENT_BUTTON_HEIGHT + 10),
            EVENT_BUTTON_WIDTH,
            EVENT_BUTTON_HEIGHT,
        )
        # Store the rect in the choice data
        state.event_choices.append(
            {"text": data["text"], "rect": rect, "apply_func": data["apply_func"]}
        )


def resolve_event_choice(state: GameState, choice: Dict):
    print(f"DEBUG: Event Choice: {choice['text']}")
    choice["apply_func"](state.player)
    current_node = state.game_map.get_node(state.current_node_id)
    if current_node:
        give_node_rewards(state, current_node.node_type, True)
        current_node.visited = True
        current_node.completed = True
    state.current_phase = GamePhase.MAP_NAVIGATION
    state.event_choices = []


def run_preparation_phase(
    state: GameState,
    context: UIContext,
    enemy_team_data: Optional[List[Dict]],
    node_type: str,
    allow_combat_start: bool,
):
    if node_type == "EVENT":
        setup_event_choice(state, context)
        return

    print(f"\n--- ENTER PREPARATION PHASE (Node: {node_type}) ---")
    state.current_phase = GamePhase.PREPARATION
    state.shop.refresh(state.player.level)
    state.allow_combat_start = allow_combat_start
    state.current_node_type = node_type
    update_player_synergies(state.player)
    context.clear_selection()  # Clear UI selection
    state.enemy_preview_units = []
    state.enemy_preview_positions = []
    current_node = state.game_map.get_node(state.current_node_id)

    if node_type == "SHOP":
        state.prepare_ui_message = "SHOP NODE: Buy and sell units. (+5 Gold)"
        if current_node and not current_node.visited:
            give_node_rewards(state, node_type, True)
            current_node.visited = True
    elif "COMBAT" in node_type or "BOSS" in node_type:
        enemy_count = len(enemy_team_data) if enemy_team_data else 0
        state.prepare_ui_message = (
            f"{node_type}: Prepare for battle against {enemy_count} foes!"
        )
        state.enemy_combat_team_data_cache = enemy_team_data
        from engine.logic import create_enemy_units, calculate_enemy_positions

        state.enemy_preview_units = create_enemy_units(enemy_team_data or [], state)
        state.enemy_preview_positions = calculate_enemy_positions(
            state.enemy_preview_units
        )
    else:
        state.prepare_ui_message = "Prepare your team."


def navigate_map(state: GameState, context: UIContext, target_node_id: int):
    current_node = state.game_map.get_node(state.current_node_id)
    target_node = state.game_map.get_node(target_node_id)
    if target_node and (
        (target_node_id == state.current_node_id and not current_node.completed)
        or (
            current_node
            and target_node_id in current_node.next_nodes
            and current_node.visited
        )
    ):
        state.current_node_id = target_node_id
        enemy_data = (
            ENEMY_TEAM_DEFINITIONS.get(target_node.enemy_team_key, [])
            if target_node.enemy_team_key
            else []
        )
        allow_start = (
            "COMBAT" in target_node.node_type or "BOSS" in target_node.node_type
        )
        run_preparation_phase(
            state,
            context,
            enemy_data,
            target_node.node_type,
            allow_combat_start=allow_start,
        )
        return True
    return False


def open_settings(state: GameState):
    state.previous_phase = state.current_phase
    state.current_phase = GamePhase.SETTINGS


def close_settings(state: GameState):
    if state.previous_phase is not None:
        state.current_phase = state.previous_phase
    else:
        state.current_phase = GamePhase.MAIN_MENU


def change_volume(state: GameState, delta: float):
    state.volume = max(0.0, min(1.0, state.volume + delta))


def cycle_resolution(state: GameState, context: UIContext):
    state.resolution_index = (state.resolution_index + 1) % len(
        state.resolution_options
    )
    width, height = state.resolution_options[state.resolution_index]
    import ui.constants as ui_c
    from ui.fonts import load_fonts

    layout = LayoutManager(width, height)
    state.game_map.rescale(
        ui_c.MAP_WIDTH,
        ui_c.MAP_HEIGHT,
        ui_c.MAP_X_START,
        ui_c.MAP_Y_START,
        ui_c.MAP_NODE_RADIUS,
    )
    state.game_map.rescale(
        ui_c.MAP_WIDTH,
        ui_c.MAP_HEIGHT,
        ui_c.MAP_X_START,
        ui_c.MAP_Y_START,
        ui_c.MAP_NODE_RADIUS,
    )
    screen = pygame.display.set_mode((width, height))
    fonts = load_fonts()
    context.rebuild(screen, fonts, layout)