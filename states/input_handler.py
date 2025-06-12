# states/input_handler.py
from __future__ import annotations
import pygame
from typing import Optional, Tuple, Any, Dict
from engine.game_state import GameState
from engine.classes import Unit, Item
from ui.ui_context import UIContext
from states.enums import GamePhase, UnitLocation
from states.state_machine import (
     start_new_run, go_to_main_menu, go_to_map, start_combat,
     run_preparation_phase, navigate_map, resolve_event_choice
)
from engine.logic import (
     buy_unit_from_shop, handle_sell_unit, handle_unit_placement,
     attempt_equip_item, attempt_unequip_item
)
from data.definitions import SYNERGY_DEFINITIONS
from data.constants import REFRESH_COST, XP_BUY_COST, XP_BUY_AMOUNT, NODE_REWARDS, MAX_ITEMS_EQUIPPED
import math

def get_clicked_object_info(pos: Tuple[int, int], state: GameState, context: UIContext) -> Optional[Tuple[UnitLocation, Any, Any]]:
    # Checks all clickable slots/items in prep phase
    player = state.player; shop = state.shop
    # Check items first (higher z-order)
    for i in range(len(player.item_inventory)):
        rect = context.get_slot_rect(UnitLocation.INVENTORY, i)
        if rect and rect.collidepoint(pos): return (UnitLocation.INVENTORY, i, player.item_inventory[i])

    # Check equipped items on hovered/selected unit
    unit_to_check_info = None
    if context.selected_unit_info:
         unit_to_check_info = context.selected_unit_info
    elif context.hovered_rect: # Find unit whose rect CONTAINS the hovered rect (for item hover)
        # Bench Units
        for i in range(len(player.bench)):
            unit_rect = context.get_slot_rect(UnitLocation.BENCH, i)
            # FIX: check if hovered_rect is the unit rect OR contained within it (item)
            if unit_rect and (unit_rect == context.hovered_rect or unit_rect.colliderect(context.hovered_rect)):
                 if player.bench[i]: unit_to_check_info = (UnitLocation.BENCH, i, player.bench[i]); break
        # Board Units
        if not unit_to_check_info:
            for (r,c), unit in player.board.items():
                 unit_rect = context.get_slot_rect(UnitLocation.BOARD, (r,c))
                 if unit_rect and (unit_rect == context.hovered_rect or unit_rect.colliderect(context.hovered_rect)):
                     if unit: unit_to_check_info = (UnitLocation.BOARD, (r,c), unit); break

    # Check items on the identified unit (selected or hovered)
    if unit_to_check_info:
        unit_loc, unit_idx, unit = unit_to_check_info
        unit_base_rect = context.get_slot_rect(unit_loc, unit_idx)
        if unit_base_rect:
            for i in range(MAX_ITEMS_EQUIPPED): # Check all item slots
                item = unit.equipped_items[i] if i < len(unit.equipped_items) else None
                rect = context.get_slot_rect(UnitLocation.EQUIPPED, i, base_rect=unit_base_rect)
                # FIX: Check if click is on the item rect itself
                if rect and rect.collidepoint(pos):
                    # Return the ITEM if it exists, otherwise None but still the location info
                    return (UnitLocation.EQUIPPED, unit_to_check_info, item) # returns item or None

    # Check unit slots if no item was clicked
    for i in range(len(player.bench)):
        rect = context.get_slot_rect(UnitLocation.BENCH, i)
        if rect and rect.collidepoint(pos): return (UnitLocation.BENCH, i, player.bench[i])
    for r in range(3): #BOARD_ROWS
        for c in range(6): #BOARD_COLS
            rect = context.get_slot_rect(UnitLocation.BOARD, (r,c))
            if rect and rect.collidepoint(pos): return (UnitLocation.BOARD, (r,c), player.board.get((r,c)))
    for i in range(len(shop.slots)):
         rect = context.get_slot_rect(UnitLocation.SHOP, i)
         if rect and rect.collidepoint(pos): return (UnitLocation.SHOP, i, shop.slots[i])
    return None


def handle_game_event(event: pygame.event.Event, state: GameState, context: UIContext) -> Optional[GameState]:
    player = state.player; shop = state.shop
    # FIX: Ensure state and context are valid
    if not state or not context: return None

    if event.type == pygame.MOUSEMOTION:
        pos = event.pos; state.hovered_info = None; context.clear_hover()
        # Phase-specific motion handling
        if state.current_phase == GamePhase.MAIN_MENU and context.start_menu_button_rect and context.start_menu_button_rect.collidepoint(pos):
             context.hovered_button_rect = context.start_menu_button_rect
        elif state.current_phase in [GamePhase.GAME_OVER, GamePhase.RUN_COMPLETE] and context.restart_button_rect and context.restart_button_rect.collidepoint(pos):
             context.hovered_button_rect = context.restart_button_rect
        elif state.current_phase == GamePhase.EVENT_CHOICE:
             for choice in state.event_choices:
                  # FIX: check if rect exists
                  if 'rect' in choice and choice['rect'] and choice['rect'].collidepoint(pos): context.hovered_button_rect = choice['rect']; break
        elif state.current_phase == GamePhase.PREPARATION:
            # Button hovers
            if context.refresh_shop_button_rect and context.refresh_shop_button_rect.collidepoint(pos): context.hovered_button_rect = context.refresh_shop_button_rect
            elif context.buy_xp_button_rect and context.buy_xp_button_rect.collidepoint(pos): context.hovered_button_rect = context.buy_xp_button_rect
            elif context.sell_area_rect and context.sell_area_rect.collidepoint(pos): context.hovered_rect = context.sell_area_rect; state.hovered_info = "SELL UNIT"
            elif state.allow_combat_start and context.start_combat_button_rect and context.start_combat_button_rect.collidepoint(pos): context.hovered_button_rect = context.start_combat_button_rect
            elif not state.allow_combat_start and context.map_button_rect and context.map_button_rect.collidepoint(pos): context.hovered_button_rect = context.map_button_rect
            # Slot/Object hovers
            else:
                 # FIX: Pass pos to get_clicked_object_info for item rect detection
                 # The logic in get_clicked_object_info needs the rects first.
                 # Instead, determine hover target rect here based on pos.
                 hover_rect = None
                 clicked_info = get_clicked_object_info(pos, state, context)

                 if clicked_info:
                      loc, idx, obj = clicked_info
                      # FIX: Determine the correct rect for hovering highlight and info text
                      if loc == UnitLocation.EQUIPPED:
                           unit_info_tuple = idx
                           unit_loc, unit_idx, unit = unit_info_tuple
                           # Find item index to get its specific rect
                           item_index = -1
                           if unit and obj: # obj is the item
                              for i, item_on_unit in enumerate(unit.equipped_items):
                                 if item_on_unit and item_on_unit.id == obj.id:
                                     item_index = i; break
                           if item_index != -1:
                                unit_base_rect = context.get_slot_rect(unit_loc, unit_idx)
                                hover_rect = context.get_slot_rect(UnitLocation.EQUIPPED, item_index, base_rect=unit_base_rect)
                      else: # Unit or Inventory/Shop item
                           hover_rect = context.get_slot_rect(loc, idx)

                      context.hovered_rect = hover_rect # Assign the correctly identified rect

                      if obj: # Generate hover text only if an object exists
                           if isinstance(obj, Unit):
                               cost = obj.get_cost() if loc == UnitLocation.SHOP else obj.get_sell_price()
                               cost_label = "Cost" if loc == UnitLocation.SHOP else "Sell";
                                # FIX: use .get safely
                               stats_str = ", ".join([f"{k.upper()}:{v:.0f}" for k,v in obj.current_stats.items() if k != 'range'])
                               items_str = ", ".join([item.name for item in obj.equipped_items if item]) or "None";
                               trigger_info = "None"
                               # FIX: Access trigger data safely
                               if obj.trigger:
                                   tr = obj.trigger
                                   interval = tr.get('timing_data',{}).get('interval','')
                                   interval_txt = f"({interval}s)" if interval else ""
                                   # Add more trigger info display if needed
                               state.hovered_info = f"{obj.name} L{obj.level}\nTraits: {', '.join(obj.traits)}\nItems: {items_str}\n{cost_label}:{cost}G\n{stats_str}"
                           elif isinstance(obj, Item):
                               state.hovered_info = f"{obj.name} ({obj.type})\n{obj.description}"
                 # Synergy hover
                 elif context.synergy_panel_rect and context.synergy_panel_rect.collidepoint(pos):
                     # Logic to find which synergy is hovered
                     pass # Simplified for now
        elif state.current_phase == GamePhase.MAP_NAVIGATION:
            for node in state.game_map.nodes.values():
                 if node and node.collidepoint(pos):
                      context.hovered_rect = pygame.Rect(node.x - node.radius, node.y - node.radius, node.radius*2, node.radius*2)
                      rewards = NODE_REWARDS.get(node.node_type, {})
                      state.hovered_info = f"Node {node.node_id}: {node.node_type}\n{node.enemy_team_key or ''}"
                      break
        elif state.current_phase == GamePhase.COMBAT:
            all_combat_units = []
            if state.player_combat_team: all_combat_units.extend(state.player_combat_team)
            if state.enemy_combat_team: all_combat_units.extend(state.enemy_combat_team)
            for unit in all_combat_units:
                 if unit and math.dist((unit.x, unit.y), pos) < unit.radius:
                      # FIX use .get
                      stats_str = ", ".join([f"{k.upper()}:{v:.0f}" for k,v in unit.current_stats.items()])
                      state.hovered_info = f"{unit.name} L{unit.level}\nHP: {unit.current_hp:.0f}/{unit.current_stats.get('hp',0):.0f}\n{stats_str}"
                      # FIX: Set hovered rect for combat units
                      context.hovered_rect = pygame.Rect(unit.x - unit.radius, unit.y - unit.radius, unit.radius*2, unit.radius*2)
                      break

    elif event.type == pygame.MOUSEBUTTONDOWN:
        pos = event.pos; is_left = event.button == 1; is_right = event.button == 3
        if state.current_phase == GamePhase.MAIN_MENU:
            if is_left and context.start_menu_button_rect and context.start_menu_button_rect.collidepoint(pos): return start_new_run(state)
        elif state.current_phase in [GamePhase.GAME_OVER, GamePhase.RUN_COMPLETE]:
            if is_left and context.restart_button_rect and context.restart_button_rect.collidepoint(pos): return start_new_run(state)
        elif state.current_phase == GamePhase.EVENT_CHOICE:
            if is_left:
                for choice in state.event_choices:
                    # FIX: check rect exists
                    if 'rect' in choice and choice['rect'] and choice['rect'].collidepoint(pos): resolve_event_choice(state, choice); break
        elif state.current_phase == GamePhase.MAP_NAVIGATION:
            if is_left:
                for node_id, node in state.game_map.nodes.items():
                    if node and node.collidepoint(pos): navigate_map(state, context, node_id); break
        elif state.current_phase == GamePhase.PREPARATION:
            if is_right: # Right click always deselects or sells
                clicked_info = get_clicked_object_info(pos, state, context)
                if clicked_info and isinstance(clicked_info[2], Unit) and clicked_info[0] in [UnitLocation.BENCH, UnitLocation.BOARD]:
                    handle_sell_unit(player, shop, clicked_info)
                context.clear_selection()
            elif is_left:
                # Button clicks
                if context.refresh_shop_button_rect and context.refresh_shop_button_rect.collidepoint(pos) and player.gold >= REFRESH_COST:
                    player.gold -= REFRESH_COST; shop.refresh(player.level)
                elif context.buy_xp_button_rect and context.buy_xp_button_rect.collidepoint(pos) and player.gold >= XP_BUY_COST:
                    player.gold -= XP_BUY_COST; player.gain_xp(XP_BUY_AMOUNT)
                elif not state.allow_combat_start and context.map_button_rect and context.map_button_rect.collidepoint(pos):
                    go_to_map(state)
                elif state.allow_combat_start and context.start_combat_button_rect and context.start_combat_button_rect.collidepoint(pos):
                    start_combat(state, state.enemy_combat_team_data_cache)
                # FIX: ensure sell_area_rect exists
                elif context.selected_unit_info and context.sell_area_rect and context.sell_area_rect.collidepoint(pos):
                    if context.selected_unit_info[0] != UnitLocation.SHOP:
                        handle_sell_unit(player, shop, context.selected_unit_info)
                    context.clear_selection()
                else: # Slot/Object clicks
                    clicked_info = get_clicked_object_info(pos, state, context)
                    if not clicked_info: context.clear_selection(); return # Clicked empty space
                    loc, idx, obj = clicked_info

                    if context.selected_item_info: # Try to use selected item
                        # Equip item to unit (from inventory -> unit slot)
                        if isinstance(obj, Unit) and loc in [UnitLocation.BENCH, UnitLocation.BOARD]:
                            attempt_equip_item(player, context.selected_item_info, (loc, idx, obj))
                         # Unequip item (from unit slot -> inventory slot, or swap)
                        elif loc == UnitLocation.INVENTORY:
                            if context.selected_item_info[0] == UnitLocation.EQUIPPED:
                                attempt_unequip_item(player, context.selected_item_info, idx)
                         # Equip item (from inventory -> empty item slot on unit)
                        elif loc == UnitLocation.EQUIPPED and obj is None :
                            unit_info = idx # idx is (loc, idx, unit) for equipped items
                            attempt_equip_item(player, context.selected_item_info, unit_info)
                         # Swap item (from inventory -> occupied item slot on unit)
                        elif loc == UnitLocation.EQUIPPED and isinstance(obj, Item):
                             # This case is tricky - swap inventory item with equipped item.
                             # Or maybe just select the new item?
                             # For now, just deselect.
                             pass
                        context.clear_selection() # Always clear after item action attempt

                    elif context.selected_unit_info: # Try to move selected unit
                         if loc in [UnitLocation.BENCH, UnitLocation.BOARD]:
                             if context.selected_unit_info[0] != UnitLocation.SHOP:
                                 handle_unit_placement(player, context.selected_unit_info, idx, loc)
                         # FIX: allow clicking item on selected unit
                         elif loc == UnitLocation.EQUIPPED and isinstance(obj, Item):
                               context.selected_item_info = (loc, idx, obj) # idx is unit_info
                               return # Don't clear selection yet, item is now "held"
                         context.clear_selection() # Clear unit selection

                    else: # No active selection, so select new object
                        if isinstance(obj, Unit):
                            if loc == UnitLocation.SHOP:
                                if not buy_unit_from_shop(player, shop, idx):
                                     # FIX: only select if buy failed AND unit still exists in slot
                                     if shop.slots[idx]: context.selected_unit_info = (loc, idx, obj)
                            else: context.selected_unit_info = (loc, idx, obj)
                        elif isinstance(obj, Item):
                            if loc == UnitLocation.EQUIPPED:
                                context.selected_unit_info = idx # idx is the unit info tuple
                                context.selected_item_info = (loc, idx, obj)
                            elif loc == UnitLocation.INVENTORY: # Select item from inventory
                                 context.selected_item_info = (loc, idx, obj)
    return None # No state change by default