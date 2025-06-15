# states/input_handler.py
from __future__ import annotations

import math
from typing import Any, Dict, Optional, Tuple

import pygame
from engine.crafting import craft, dismantle
from data.constants import (
    MAX_ITEMS_EQUIPPED,
    REFRESH_COST,
    XP_BUY_AMOUNT,
    XP_BUY_COST,
    REFRESH_CRYSTAL_COST,
    XP_BUY_CRYSTAL_COST
)
from data.definitions import SYNERGY_DEFINITIONS,NODE_REWARDS
from data.enums import ItemType
from engine.classes import Artifact, Item, Unit
from engine.game_state import GameState
from engine.logic import (
    attempt_equip_item,
    attempt_unequip_item,
    buy_unit_from_shop,
    handle_sell_unit,
    handle_unit_placement,
)
from states.enums import GamePhase, UnitLocation
from states.state_machine import (
    change_volume,
    close_settings,
    cycle_resolution,
    go_to_main_menu,
    go_to_map,
    navigate_map,
    open_settings,
    resolve_event_choice,
    run_preparation_phase,
    start_combat,
    start_new_run,
)
from ui import sounds
from ui.details_window import DetailsWindow
from ui.drag_manager import get_drag_manager
from ui.ui_context import UIContext
from ui.crafting_window import CraftingWindow
from ui.stats_panel import StatsPanel

def get_clicked_object_info(
    pos: Tuple[int, int], state: GameState, context: UIContext
) -> Optional[Tuple[UnitLocation, Any, Any]]:
    # Checks all clickable slots/items in prep phase
    player = state.player
    shop = state.shop
    # Check items first (higher z-order)
    for i in range(len(player.item_inventory)):
        rect = context.get_slot_rect(UnitLocation.INVENTORY, i)
        if rect and rect.collidepoint(pos):
            return (UnitLocation.INVENTORY, i, player.item_inventory[i])

    # Check equipped items on hovered/selected unit
    unit_to_check_info = None
    if context.selected_unit_info:
        unit_to_check_info = context.selected_unit_info
    elif (
        context.hovered_rect
    ):  # Find unit whose rect CONTAINS the hovered rect (for item hover)
        # Bench Units
        for i in range(len(player.bench)):
            unit_rect = context.get_slot_rect(UnitLocation.BENCH, i)
            # FIX: check if hovered_rect is the unit rect OR contained within it (item)
            if unit_rect and (
                unit_rect == context.hovered_rect
                or unit_rect.colliderect(context.hovered_rect)
            ):
                if player.bench[i]:
                    unit_to_check_info = (UnitLocation.BENCH, i, player.bench[i])
                    break
        # Board Units
        if not unit_to_check_info:
            for (r, c), unit in player.board.items():
                unit_rect = context.get_slot_rect(UnitLocation.BOARD, (r, c))
                if unit_rect and (
                    unit_rect == context.hovered_rect
                    or unit_rect.colliderect(context.hovered_rect)
                ):
                    if unit:
                        unit_to_check_info = (UnitLocation.BOARD, (r, c), unit)
                        break

    # Check items on the identified unit (selected or hovered)
    if unit_to_check_info:
        unit_loc, unit_idx, unit = unit_to_check_info
        unit_base_rect = context.get_slot_rect(unit_loc, unit_idx)
        if unit_base_rect:
            for i in range(MAX_ITEMS_EQUIPPED):  # Check all item slots
                item = unit.equipped_items[i] if i < len(unit.equipped_items) else None
                rect = context.get_slot_rect(
                    UnitLocation.EQUIPPED, i, base_rect=unit_base_rect
                )
                # FIX: Check if click is on the item rect itself
                if rect and rect.collidepoint(pos):
                    # Return the ITEM if it exists, otherwise None but still the location info
                    return (
                        UnitLocation.EQUIPPED,
                        unit_to_check_info,
                        item,
                    )  # returns item or None

    # Check unit slots if no item was clicked
    for i in range(len(player.bench)):
        rect = context.get_slot_rect(UnitLocation.BENCH, i)
        if rect and rect.collidepoint(pos):
            return (UnitLocation.BENCH, i, player.bench[i])
    for r in range(3):  # BOARD_ROWS
        for c in range(6):  # BOARD_COLS
            rect = context.get_slot_rect(UnitLocation.BOARD, (r, c))
            if rect and rect.collidepoint(pos):
                return (UnitLocation.BOARD, (r, c), player.board.get((r, c)))
    for unit, (row, col) in zip(
        state.enemy_preview_units, state.enemy_preview_positions
    ):
        rect = context.get_slot_rect(UnitLocation.PREVIEW, (row, col))
        if rect and rect.collidepoint(pos):
            return (UnitLocation.PREVIEW, (row, col), unit)
    for i in range(len(shop.slots)):
        rect = context.get_slot_rect(UnitLocation.SHOP, i)
        if rect and rect.collidepoint(pos):
            return (UnitLocation.SHOP, i, shop.slots[i])
    return None


def handle_game_event(
    event: pygame.event.Event, state: GameState, context: UIContext
) -> Optional[GameState]:
    player = state.player
    shop = state.shop
    # FIX: Ensure state and context are valid
    if not state or not context:
        return None

    # Give the details window priority to handle interactions and
    # consume events that occur within its bounds. This prevents other
    # UI logic from reacting to clicks or drags intended for the
    # window, which previously made the close button and dragging
    # unreliable.
    if context.details_window:
        dw = context.details_window
        dw.handle_event(event, context)
        if event.type == pygame.KEYDOWN:
            return None
        if getattr(event, "pos", None) and dw.rect.collidepoint(event.pos):
            return None
        if dw.dragging or context.details_window is None:
            return None
    if context.stats_panel:
        if context.stats_panel.handle_event(event):
            return None

    if event.type == pygame.MOUSEMOTION:
        pos = event.pos
        # -------- 若正在拖拽，更新并短路其余 Hover 逻辑 -------- #
        drag_mgr = get_drag_manager(context)
        context.set_drag_manager(drag_mgr)
        drag_mgr.update(pos)
        if drag_mgr.active:
            return None
        if drag_mgr.active:
            drag_mgr.update(pos)
            return None
        state.hovered_info = None
        context.clear_hover()
        if context.settings_button_rect and context.settings_button_rect.collidepoint(
            pos
        ):
            context.hovered_button_rect = context.settings_button_rect
        elif (
            context.stats_toggle_button_rect
            and context.stats_toggle_button_rect.collidepoint(pos)
        ):
            context.hovered_button_rect = context.stats_toggle_button_rect
        # Phase-specific motion handling
        elif (
            state.current_phase == GamePhase.MAIN_MENU
            and context.start_menu_button_rect
            and context.start_menu_button_rect.collidepoint(pos)
        ):
            context.hovered_button_rect = context.start_menu_button_rect
        elif state.current_phase in [GamePhase.GAME_OVER, GamePhase.RUN_COMPLETE]:
            if (
                context.restart_button_rect
                and context.restart_button_rect.collidepoint(pos)
            ):
                context.hovered_button_rect = context.restart_button_rect
            elif (
                context.main_menu_button_rect
                and context.main_menu_button_rect.collidepoint(pos)
            ):
                context.hovered_button_rect = context.main_menu_button_rect
        elif state.current_phase == GamePhase.DIFFICULTY_SELECT:
            for rect in context.difficulty_button_rects:
                if rect.collidepoint(pos):
                    context.hovered_button_rect = rect
                    break
        elif state.current_phase == GamePhase.THEME_SELECT:
            for rect in context.theme_button_rects:
                if rect.collidepoint(pos):
                    context.hovered_button_rect = rect
                    break
        elif state.current_phase == GamePhase.EVENT_CHOICE:
            for choice in state.event_choices:
                # FIX: check if rect exists
                if (
                    "rect" in choice
                    and choice["rect"]
                    and choice["rect"].collidepoint(pos)
                ):
                    context.hovered_button_rect = choice["rect"]
                    break
        elif state.current_phase == GamePhase.SETTINGS:
            if context.volume_down_rect and context.volume_down_rect.collidepoint(pos):
                context.hovered_button_rect = context.volume_down_rect
            elif context.volume_up_rect and context.volume_up_rect.collidepoint(pos):
                context.hovered_button_rect = context.volume_up_rect
            elif context.resolution_rect and context.resolution_rect.collidepoint(pos):
                context.hovered_button_rect = context.resolution_rect
            elif (
                context.settings_back_button_rect
                and context.settings_back_button_rect.collidepoint(pos)
            ):
                context.hovered_button_rect = context.settings_back_button_rect
            elif (
                context.settings_abandon_button_rect
                and context.settings_abandon_button_rect.collidepoint(pos)
            ):
                context.hovered_button_rect = context.settings_abandon_button_rect
        elif state.current_phase == GamePhase.PREPARATION:
            # Button hovers
            if (
                context.refresh_shop_button_rect
                and context.refresh_shop_button_rect.collidepoint(pos)
            ):
                context.hovered_button_rect = context.refresh_shop_button_rect
            elif context.buy_xp_button_rect and context.buy_xp_button_rect.collidepoint(
                pos
            ):
                context.hovered_button_rect = context.buy_xp_button_rect
            elif context.sell_area_rect and context.sell_area_rect.collidepoint(pos):
                context.hovered_rect = context.sell_area_rect
                state.hovered_info = "SELL UNIT"
            elif (
                state.allow_combat_start
                and context.start_combat_button_rect
                and context.start_combat_button_rect.collidepoint(pos)
            ):
                context.hovered_button_rect = context.start_combat_button_rect
            elif (
                not state.allow_combat_start
                and context.map_button_rect
                and context.map_button_rect.collidepoint(pos)
            ):
                context.hovered_button_rect = context.map_button_rect
            # Slot/Object hovers
            else:
                # FIX: Pass pos to get_clicked_object_info for item rect detection
                # The logic in get_clicked_object_info needs the rects first.
                # Instead, determine hover target rect here based on pos.
                hover_rect = None
                clicked_info = get_clicked_object_info(pos, state, context)
                if not clicked_info:
                    for idx, art in enumerate(state.player.artifacts):
                        rect = context.get_artifact_rect(idx)
                        if rect and rect.collidepoint(pos):
                            context.hovered_rect = rect
                            state.hovered_info = f"{art.name}\n{art.description}"
                            break
                if clicked_info:
                    loc, idx, obj = clicked_info
                    # FIX: Determine the correct rect for hovering highlight and info text
                    if loc == UnitLocation.EQUIPPED:
                        unit_info_tuple = idx
                        unit_loc, unit_idx, unit = unit_info_tuple
                        # Find item index to get its specific rect
                        item_index = -1
                        if unit and obj:  # obj is the item
                            for i, item_on_unit in enumerate(unit.equipped_items):
                                if item_on_unit and item_on_unit.id == obj.id:
                                    item_index = i
                                    break
                        if item_index != -1:
                            unit_base_rect = context.get_slot_rect(unit_loc, unit_idx)
                            hover_rect = context.get_slot_rect(
                                UnitLocation.EQUIPPED,
                                item_index,
                                base_rect=unit_base_rect,
                            )
                    else:  # Unit or Inventory/Shop item
                        hover_rect = context.get_slot_rect(loc, idx)

                    context.hovered_rect = (
                        hover_rect  # Assign the correctly identified rect
                    )

                    if obj:  # Generate hover text only if an object exists
                        if isinstance(obj, Unit):
                            cs = obj.current_stats
                            info_lines = [
                                obj.name,
                                f"HP: {int(obj.current_hp)}/{int(cs['hp'])}",
                                f"Phys {int(cs['ad'])} / {int(cs['armor'])}",
                                f"Magic {int(cs['ap'])} / {int(cs['mr'])}",
                                f"Bonus {int(cs.get('percentage_damage_bonus',100))}% / Red {int(cs.get('percentage_damage_reduction',100))}%",
                            ]
                            state.hovered_info = "\n".join(info_lines)
                        elif isinstance(obj, Item):
                            state.hovered_info = (
                                f"{obj.name} ({obj.type})\n{obj.description}"
                            )
                # Synergy hover
                elif (
                    context.synergy_panel_rect
                    and context.synergy_panel_rect.collidepoint(pos)
                ):
                    # Logic to find which synergy is hovered
                    pass  # Simplified for now
        elif state.current_phase == GamePhase.MAP_NAVIGATION:
            clicked_info = get_clicked_object_info(pos, state, context)
            if not clicked_info:
                for idx, art in enumerate(state.player.artifacts):
                    rect = context.get_artifact_rect(idx)
                    if rect and rect.collidepoint(pos):
                        context.hovered_rect = rect
                        state.hovered_info = f"{art.name}\n{art.description}"
                        break
            for node in state.game_map.nodes.values():
                if node and node.collidepoint(pos):
                    context.hovered_rect = pygame.Rect(
                        node.x - node.radius,
                        node.y - node.radius,
                        node.radius * 2,
                        node.radius * 2,
                    )
                    rewards = NODE_REWARDS.get(node.node_type, {})
                    state.hovered_info = f"Node {node.node_id}: {node.node_type}\n{node.enemy_team_key or ''}"
                    break
        elif state.current_phase == GamePhase.COMBAT:
            all_combat_units = []
            if state.player_combat_team:
                all_combat_units.extend(state.player_combat_team)
            if state.enemy_combat_team:
                all_combat_units.extend(state.enemy_combat_team)
            for unit in all_combat_units:
                if unit and math.dist((unit.x, unit.y), pos) < unit.radius:
                    cs = unit.current_stats
                    info_lines = [
                        unit.name,
                        f"HP: {int(unit.current_hp)}/{int(cs['hp'])}",
                        f"Phys {int(cs['ad'])} / Def {int(cs['armor'])}",
                        f"Magic {int(cs['ap'])} / Res {int(cs['mr'])}",
                        f"Bonus {int(cs.get('percentage_damage_bonus',100))}% / Red {int(cs.get('percentage_damage_reduction',100))}%",
                    ]
                    state.hovered_info = "\n".join(info_lines)
                    # FIX: Set hovered rect for combat units
                    context.hovered_rect = pygame.Rect(
                        unit.x - unit.radius,
                        unit.y - unit.radius,
                        unit.radius * 2,
                        unit.radius * 2,
                    )
                    break

    elif event.type == pygame.MOUSEBUTTONDOWN:
        pos = event.pos
        is_left = event.button == 1
        is_right = event.button == 3

        drag_mgr = get_drag_manager(context)
        context.set_drag_manager(drag_mgr)
        if (
            is_left
            and context.settings_button_rect
            and context.settings_button_rect.collidepoint(pos)
        ):
            open_settings(state)
            return None
        if (
            is_left
            and context.stats_toggle_button_rect
            and context.stats_toggle_button_rect.collidepoint(pos)
        ):
            if context.stats_panel:
                context.stats_panel = None
            else:
                context.stats_panel = StatsPanel(state, context)
            return None

        if state.current_phase == GamePhase.MAIN_MENU:
            if (
                is_left
                and context.start_menu_button_rect
                and context.start_menu_button_rect.collidepoint(pos)
            ):
                # 改为进入难度选择界面
                state.current_phase = GamePhase.DIFFICULTY_SELECT
        elif state.current_phase in [GamePhase.GAME_OVER, GamePhase.RUN_COMPLETE]:
            if (
                is_left
                and context.restart_button_rect
                and context.restart_button_rect.collidepoint(pos)
            ):
                return start_new_run(state)
            elif (
                is_left
                and context.main_menu_button_rect
                and context.main_menu_button_rect.collidepoint(pos)
            ):
                go_to_main_menu(state)
        # ---------- 难度选择点击 ----------
        elif (
            state.current_phase == GamePhase.DIFFICULTY_SELECT
            and event.type == pygame.MOUSEBUTTONDOWN
            and event.button == 1
        ):
            for idx, rect in enumerate(context.difficulty_button_rects):
                if rect.collidepoint(pos):
                    levels = ["easy", "medium", "hard"]
                    state.difficulty_level = levels[idx]
                    return start_new_run(state, state.difficulty_level)

        # ---------- 主题选择点击 ----------
        elif (
            state.current_phase == GamePhase.THEME_SELECT
            and event.type == pygame.MOUSEBUTTONDOWN
            and event.button == 1
        ):
            if not state.available_themes:
                return None
            chosen = None
            for idx, rect in enumerate(context.theme_button_rects):
                if rect.collidepoint(pos):
                    if idx < len(state.available_themes):
                        chosen = state.available_themes.pop(idx)
                    break
            if not chosen:
                return None
            state.chosen_themes.append(chosen)
            state.current_theme = chosen
            state.current_phase = GamePhase.MAP_NAVIGATION
            # 进入下一幕地图
            from engine.classes import GameMap

            state.game_map = GameMap()
            state.current_node_id = state.game_map.start_node_id
            return None
        elif state.current_phase == GamePhase.EVENT_CHOICE:
            if is_left:
                for choice in state.event_choices:
                    # FIX: check rect exists
                    if (
                        "rect" in choice
                        and choice["rect"]
                        and choice["rect"].collidepoint(pos)
                    ):
                        resolve_event_choice(state, choice)
                        break
        elif state.current_phase == GamePhase.MAP_NAVIGATION:
            if is_left:
                for node_id, node in state.game_map.nodes.items():
                    if node and node.collidepoint(pos):
                        navigate_map(state, context, node_id)
                        break
        elif state.current_phase == GamePhase.COMBAT:
            if is_left:
                units: list[Unit] = []
                if state.player_combat_team:
                    units.extend(state.player_combat_team)
                if state.enemy_combat_team:
                    units.extend(state.enemy_combat_team)
                for unit in units:
                    if unit and math.dist((unit.x, unit.y), pos) < unit.radius:
                        context.details_window = DetailsWindow(unit, context)
                        break
        elif state.current_phase == GamePhase.SETTINGS:
            if (
                is_left
                and context.volume_down_rect
                and context.volume_down_rect.collidepoint(pos)
            ):
                change_volume(state, -0.1)
            elif (
                is_left
                and context.volume_up_rect
                and context.volume_up_rect.collidepoint(pos)
            ):
                change_volume(state, 0.1)
            elif (
                is_left
                and context.resolution_rect
                and context.resolution_rect.collidepoint(pos)
            ):
                cycle_resolution(state, context)
            elif (
                is_left
                and context.settings_back_button_rect
                and context.settings_back_button_rect.collidepoint(pos)
            ):
                close_settings(state)
            elif (
                is_left
                and context.settings_abandon_button_rect
                and context.settings_abandon_button_rect.collidepoint(pos)
            ):
                go_to_main_menu(state)
        elif state.current_phase == GamePhase.PREPARATION:
            # ---------------- 开始拖拽判定 ---------------- #
            drag_mgr = get_drag_manager(context)
            if is_left:
                clicked_info = get_clicked_object_info(pos, state, context)
                # 能够拖拽的对象：单位或物品，且当前没有进行中的拖拽
                if (
                    clicked_info
                    and clicked_info[0] not in [UnitLocation.SHOP, UnitLocation.PREVIEW]
                    and isinstance(clicked_info[2], (Unit, Item))
                ):
                    drag_mgr.prepare(clicked_info, pos)
                    return None

            # ---------- 右键保留原有逻辑 ----------
            if is_right and not drag_mgr.active:
                clicked_info = get_clicked_object_info(pos, state, context)
                if (
                    clicked_info
                    and isinstance(clicked_info[2], Unit)
                    and clicked_info[0] in [UnitLocation.BENCH, UnitLocation.BOARD]
                ):
                    handle_sell_unit(player, shop, clicked_info)
                    sounds.play("buy")
                context.clear_selection()
            elif is_left:
                # Button clicks
                if (
                    context.refresh_shop_button_rect
                    and context.refresh_shop_button_rect.collidepoint(pos)
                ):
                    if player.crystals >= REFRESH_CRYSTAL_COST:
                        player.crystals -= REFRESH_CRYSTAL_COST
                        shop.refresh(player.level)
                        sounds.play("buy")
                    else:
                        sounds.play("error")
                elif (
                    context.craft_button_rect
                    and context.craft_button_rect.collidepoint(pos)
                ):
                    context.crafting_window = CraftingWindow(state, context)
                elif context.crafting_window and context.crafting_window.handle_click(
                    event
                ):
                    pass
                elif (
                    context.buy_xp_button_rect
                    and context.buy_xp_button_rect.collidepoint(pos)
                ):
                    if player.crystals >= XP_BUY_CRYSTAL_COST:
                        player.crystals -= XP_BUY_CRYSTAL_COST
                        player.gain_xp(XP_BUY_AMOUNT)
                        sounds.play("buy")
                    else:
                        sounds.play("error")
                elif (
                    not state.allow_combat_start
                    and context.map_button_rect
                    and context.map_button_rect.collidepoint(pos)
                ):
                    go_to_map(state)
                    sounds.play("buy")
                elif (
                    state.allow_combat_start
                    and context.start_combat_button_rect
                    and context.start_combat_button_rect.collidepoint(pos)
                ):
                    start_combat(state, state.enemy_combat_team_data_cache)
                    sounds.play("buy")
                # FIX: ensure sell_area_rect exists
                elif (
                    context.selected_unit_info
                    and context.sell_area_rect
                    and context.sell_area_rect.collidepoint(pos)
                ):
                    if context.selected_unit_info[0] != UnitLocation.SHOP:
                        handle_sell_unit(player, shop, context.selected_unit_info)
                        sounds.play("buy")
                    context.clear_selection()
                else:  # Slot/Object clicks
                    clicked_info = get_clicked_object_info(pos, state, context)
                    if not clicked_info:
                        context.clear_selection()
                        return  # Clicked empty space
                    loc, idx, obj = clicked_info

                    if context.selected_item_info:  # Try to use selected item
                        # Equip item to unit (from inventory -> unit slot)
                        if isinstance(obj, Unit) and loc in [
                            UnitLocation.BENCH,
                            UnitLocation.BOARD,
                        ]:
                            attempt_equip_item(
                                player, context.selected_item_info, (loc, idx, obj)
                            )
                        # Unequip item (from unit slot -> inventory slot, or swap)
                        elif loc == UnitLocation.INVENTORY:
                            if context.selected_item_info[0] == UnitLocation.EQUIPPED:
                                attempt_unequip_item(
                                    player, context.selected_item_info, idx
                                )
                        # Equip item (from inventory -> empty item slot on unit)
                        elif loc == UnitLocation.EQUIPPED and obj is None:
                            unit_info = (
                                idx  # idx is (loc, idx, unit) for equipped items
                            )
                            attempt_equip_item(
                                player, context.selected_item_info, unit_info
                            )
                        # Swap item (from inventory -> occupied item slot on unit)
                        elif loc == UnitLocation.EQUIPPED and isinstance(obj, Item):
                            # This case is tricky - swap inventory item with equipped item.
                            # Or maybe just select the new item?
                            # For now, just deselect.
                            pass
                        context.clear_selection()  # Always clear after item action attempt

                    elif context.selected_unit_info:  # Try to move selected unit
                        if loc in [UnitLocation.BENCH, UnitLocation.BOARD]:
                            if context.selected_unit_info[0] != UnitLocation.SHOP:
                                handle_unit_placement(
                                    player, context.selected_unit_info, idx, loc
                                )
                        # FIX: allow clicking item on selected unit
                        elif loc == UnitLocation.EQUIPPED and isinstance(obj, Item):
                            context.selected_item_info = (
                                loc,
                                idx,
                                obj,
                            )  # idx is unit_info
                            return  # Don't clear selection yet, item is now "held"
                        context.clear_selection()  # Clear unit selection

                    else:  # No active selection, so select new object
                        if isinstance(obj, Unit):
                            if loc == UnitLocation.SHOP:
                                if not buy_unit_from_shop(player, shop, idx):
                                    # FIX: only select if buy failed AND unit still exists in slot
                                    if shop.slots[idx]:
                                        context.selected_unit_info = (loc, idx, obj)
                            elif loc == UnitLocation.PREVIEW:
                                context.details_window = DetailsWindow(obj, context)
                            else:
                                context.selected_unit_info = (loc, idx, obj)
                        elif isinstance(obj, Item):
                            if loc == UnitLocation.EQUIPPED:
                                context.selected_unit_info = (
                                    idx  # idx is the unit info tuple
                                )
                                context.selected_item_info = (loc, idx, obj)
                            elif (
                                loc == UnitLocation.INVENTORY
                            ):  # Select item from inventory
                                context.selected_item_info = (loc, idx, obj)
                            else:
                                context.details_window = DetailsWindow(obj, context)
    # ---------------- MOUSEBUTTONUP：处理拖拽释放 ---------------- #
    if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
        context.details_window = None
    if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
        pos = event.pos
        if context.details_window:
            context.details_window.handle_event(event, context)
        drag_mgr = get_drag_manager(context)
        if drag_mgr.active and drag_mgr.obj_info:
            loc0, idx0, obj0 = drag_mgr.obj_info
            drag_mgr.end()

            # 根据释放位置判断目标
            mx, my = pos
            target_info = get_clicked_object_info((mx, my), state, context)

            if isinstance(obj0, Unit):
                # 卖出判定
                if context.sell_area_rect and context.sell_area_rect.collidepoint(
                    (mx, my)
                ):
                    handle_sell_unit(state.player, state.shop, (loc0, idx0, obj0))
                # 目标槽位逻辑
                elif target_info and target_info[0] in [
                    UnitLocation.BENCH,
                    UnitLocation.BOARD,
                ]:
                    handle_unit_placement(
                        state.player, (loc0, idx0, obj0), target_info[1], target_info[0]
                    )
            elif isinstance(obj0, Item):
                if (
                    target_info
                    and isinstance(target_info[2], Unit)
                    and target_info[0] in [UnitLocation.BENCH, UnitLocation.BOARD]
                ):
                    attempt_equip_item(state.player, (loc0, idx0, obj0), target_info)
                elif (
                    target_info
                    and target_info[0] == UnitLocation.INVENTORY
                    and loc0 == UnitLocation.EQUIPPED
                ):
                    attempt_unequip_item(
                        state.player, (loc0, idx0, obj0), target_info[1]
                    )

            # 拖拽结束，清理 hover/selection
            context.clear_selection()
            context.clear_hover()
        elif drag_mgr.candidate_info:
            click_info = drag_mgr.candidate_info
            drag_mgr.cancel()
            loc, idx, obj = click_info
            if state.current_phase == GamePhase.PREPARATION:
                if isinstance(obj, Unit):
                    context.details_window = DetailsWindow(obj, context)
                context.selected_unit_info = (
                    click_info if isinstance(obj, Unit) else None
                )
                if isinstance(obj, Item):
                    context.selected_item_info = click_info
            elif state.current_phase == GamePhase.COMBAT and isinstance(obj, Unit):
                context.details_window = DetailsWindow(obj, context)
            return None
        if context.details_window:
            context.details_window.handle_event(event, context)
        return None

    if context.details_window:
        context.details_window.handle_event(event, context)
        return None
    return None  # 默认不切换状态