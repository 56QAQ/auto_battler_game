from __future__ import annotations

import math
from typing import Optional

import pygame
from data.enums import Color
from data.constants import REFRESH_CRYSTAL_COST, XP_BUY_CRYSTAL_COST
from data.definitions import SYNERGY_DEFINITIONS
from engine.classes import DamageFloater, Item, Unit, VisualEffect
from engine.environment_effects import SteamCloudArea
from engine.enums import AnimationState, EffectType, StatusCategory
from engine.game_state import GameState
from engine.logic import _material_cost_bundle as _mat_cost_bundle
from engine.utils import clamp, lerp_color
from states.enums import GamePhase, UnitLocation
from ui.constants import (
    ACTIVE_SYNERGY_BRONZE,
    ACTIVE_SYNERGY_GOLD,
    ACTIVE_SYNERGY_SILVER,
    ANIM_DURATIONS,
    BENCH_SLOTS,
    BENCH_X_START,
    BENCH_Y,
    BLACK,
    BLUE,
    BOARD_COLS,
    BOARD_ROWS,
    BOARD_X_START,
    BOARD_Y_START,
    PREVIEW_Y_START,
    BUTTON_ACTIVE,
    BUTTON_BG,
    BUTTON_DISABLED,
    BUTTON_HOVER,
    CYAN,
    DARK_GRAY,
    DEATH_ANIM_DURATION,
    GOLD,
    GRAY,
    GREEN,
    GRID_LINE,
    HEALTH_BAR_BG,
    HEALTH_BAR_COLOR,
    HIGHLIGHT_COLOR,
    INACTIVE_SYNERGY,
    ITEM_COLOR,
    LIGHT_GRAY,
    MAP_NODE_BG,
    MAP_NODE_CURRENT,
    MAP_NODE_VISITED,
    MAP_PATH,
    MAX_ITEMS_EQUIPPED,
    PANEL_BG,
    RARITY_COLORS,
    RED,
    SLOT_MARGIN,
    SLOT_SIZE,
    STATUS_ICON_KEYS,
    STATUS_ICON_SIZE,
    STATUS_ICON_SPACING,
    SYNERGY_LINE_HEIGHT,
    RELIC_ICON_SIZE,
    WHITE,
    YELLOW,
    PURPLE,
)
from ui.ui_context import UIContext

# --------------------------------------------------------------- #
#  Status‑Effect icon map (Enum → icon‑key defined in constants)  #
# --------------------------------------------------------------- #
_CATEGORY_ICON_MAP: dict[StatusCategory, str] = {
    StatusCategory.DOT: STATUS_ICON_KEYS["DOT"],
    StatusCategory.HOT: STATUS_ICON_KEYS["HOT"],
    StatusCategory.ACTION_BLOCK: STATUS_ICON_KEYS["STUN"],
    StatusCategory.SHIELD: STATUS_ICON_KEYS["SHIELD"],
    StatusCategory.BUFF: STATUS_ICON_KEYS["BUFF"],
    StatusCategory.DEBUFF: STATUS_ICON_KEYS["DEBUFF"],
}


# --- Helper Drawing Functions ---
def _lighten(color, amt=20):
    return tuple(min(255, c + amt) for c in color[:3])


def _darken(color, amt=20):
    return tuple(max(0, c - amt) for c in color[:3])


def draw_beveled_rect(
    surface: pygame.Surface,
    rect: pygame.Rect,
    base_color: tuple,
    texture: Optional[pygame.Surface] = None,
):
    if texture:
        scaled = pygame.transform.smoothscale(texture, rect.size)
        surface.blit(scaled, rect.topleft)
    else:
        pygame.draw.rect(surface, base_color, rect)
    pygame.draw.line(
        surface, _lighten(base_color, 30), rect.topleft, (rect.right - 1, rect.top)
    )
    pygame.draw.line(
        surface, _lighten(base_color, 30), rect.topleft, (rect.left, rect.bottom - 1)
    )
    pygame.draw.line(
        surface,
        _darken(base_color, 30),
        (rect.left, rect.bottom - 1),
        (rect.right - 1, rect.bottom - 1),
    )
    pygame.draw.line(
        surface,
        _darken(base_color, 30),
        (rect.right - 1, rect.top),
        (rect.right - 1, rect.bottom - 1),
    )


def draw_text(
    context: UIContext,
    text: str,
    pos: tuple,
    font_key="default",
    color=WHITE,
    align="left",
    alpha=255,
):
    # FIX: Ensure context and screen exist
    if not context or not context.screen:
        return
    font_obj = context.get_font(font_key)
    lines = str(text).split("\n")
    y = pos[1]
    line_height = font_obj.get_linesize()
    surfaces = []
    max_width = 0
    for line in lines:
        text_surface = font_obj.render(line, True, color)
        max_width = max(max_width, text_surface.get_width())
        if alpha < 255:
            # FIX: Alpha blending method
            temp_surf = pygame.Surface(text_surface.get_size(), pygame.SRCALPHA)
            text_surface.set_alpha(alpha)
            temp_surf.blit(text_surface, (0, 0))
            text_surface = temp_surf  # Use the surface with alpha
        surfaces.append(text_surface)

    final_y = y

    for text_surface in surfaces:
        draw_x = pos[0]
        if align == "center":
            draw_x = pos[0] - text_surface.get_width() / 2.0
        elif align == "right":
            draw_x = pos[0] - text_surface.get_width()

        context.screen.blit(text_surface, (int(draw_x), int(final_y)))
        final_y += line_height


def draw_button(
    context: UIContext,
    rect: Optional[pygame.Rect],
    text: str,
    font_key: str,
    is_hovered: bool,
    is_pressed: bool = False,
    is_disabled: bool = False,
):
    """Draw a button with simple bevel and states."""
    if not rect or not context or not context.screen:
        return

    if is_disabled:
        base = BUTTON_DISABLED
        text_col = GRAY
    elif is_pressed:
        base = BUTTON_ACTIVE
        text_col = WHITE
    else:
        base = BUTTON_HOVER if is_hovered else BUTTON_BG
        text_col = WHITE

    texture = context.get_ui_image("button", (rect.width, rect.height))
    draw_beveled_rect(context.screen, rect, base, texture)

    offset = (1, 1) if is_pressed else (0, 0)
    font_obj = context.get_font(font_key)
    text_y = rect.centery - font_obj.get_linesize() // 2 + offset[1]
    draw_text(
        context,
        text,
        (rect.centerx + offset[0], text_y),
        font_key,
        text_col,
        align="center",
    )


def draw_hover_info(state: GameState, context: UIContext):
    # FIX: Check context/screen
    if not context or not context.screen:
        return
    # Draw highlight box only if not hovering a button
    if context.hovered_rect and not context.hovered_button_rect:
        pygame.draw.rect(
            context.screen, YELLOW, context.hovered_rect, 2
        )  # Increased width

    if state.hovered_info:
        mx, my = pygame.mouse.get_pos()
        info_lines = state.hovered_info.split("\n")
        font = context.get_font("small")
        # FIX: Check if info_lines is empty
        max_line_width = (
            max(font.size(line)[0] for line in info_lines) if info_lines else 10
        )
        info_height = len(info_lines) * font.get_linesize() + 10
        info_width = max_line_width + 20
        # FIX: Default info rect position to mouse
        info_rect = pygame.Rect(mx + 15, my - info_height / 2, info_width, info_height)
        # Adjust position if hovering a specific rect
        if context.hovered_rect:
            info_rect.left = context.hovered_rect.right + 5
            info_rect.centery = context.hovered_rect.centery

        # Clamp to screen bounds
        info_rect.left = clamp(
            info_rect.left, 5, context.screen.get_width() - info_width - 5
        )
        info_rect.top = clamp(
            info_rect.top, 5, context.screen.get_height() - info_height - 5
        )

        # Slight transparency to allow background to show through
        info_surf = pygame.Surface(info_rect.size, pygame.SRCALPHA)
        info_surf.fill((*BLACK[:3], 200))
        context.screen.blit(info_surf, info_rect.topleft)
        pygame.draw.rect(context.screen, LIGHT_GRAY, info_rect, 1, border_radius=3)
        draw_text(
            context,
            state.hovered_info,
            (info_rect.left + 10, info_rect.top + 5),
            "small",
            WHITE,
        )


def draw_unit_prep(
    context: UIContext,
    rect: Optional[pygame.Rect],
    unit: Optional[Unit],
    is_selected: bool,
):
    # FIX: Check rect
    if not rect or not context or not context.screen:
        return
    texture = context.get_ui_image("panel", (rect.width, rect.height))
    draw_beveled_rect(context.screen, rect, DARK_GRAY, texture)
    if unit:
        color = RARITY_COLORS.get(unit.rarity, WHITE)
        inner = rect.inflate(-4, -4)
        pygame.draw.rect(context.screen, color, inner, 1)
        img = context.get_unit_image(unit.name, (inner.width, inner.height))
        context.screen.blit(img, inner.topleft)
        if hasattr(unit, "primary_color"):
            pc: Color = unit.primary_color
            col_map = {
                Color.RED: RED,
                Color.GREEN: GREEN,
                Color.BLUE: BLUE,
                Color.YELLOW: YELLOW,
                Color.PURPLE: PURPLE,
                Color.CYAN: CYAN,
                Color.BLACK: BLACK,
                Color.WHITE: WHITE,
            }
            pygame.draw.circle(
                context.screen,
                col_map.get(pc, WHITE),
                (inner.right - 6, inner.top + 6),
                4,
            )

        star_y = rect.bottom - 12
        if unit.level >= 2:
            draw_text(
                context,
                "*" * unit.level,
                (rect.centerx, star_y),
                "small",
                GOLD,
                align="center",
            )
    if is_selected:
        pygame.draw.rect(context.screen, HIGHLIGHT_COLOR, rect, 4)


def draw_item_prep(
    context: UIContext,
    rect: Optional[pygame.Rect],
    item: Optional[Item],
    is_selected: bool,
):
    # FIX: Check rect
    if not rect or not context or not context.screen:
        return
    texture = context.get_ui_image("panel", (rect.width, rect.height))
    draw_beveled_rect(context.screen, rect, DARK_GRAY, texture)
    if item:
        color = ITEM_COLOR if item.item_type == "COMPONENT" else GOLD
        inner = rect.inflate(-4, -4)
        pygame.draw.rect(context.screen, color, inner, 1)
        img = context.get_item_image(item.name, (inner.width, inner.height))
        context.screen.blit(img, inner.topleft)
    if is_selected:
        pygame.draw.rect(context.screen, HIGHLIGHT_COLOR, rect, 3)


def draw_health_bar(context: UIContext, x, y, current_hp, max_hp, width, height):
    # FIX: Check context/screen
    if not context or not context.screen:
        return
    if max_hp <= 0 or width < 1:
        return
    ratio = max(0, min(1, current_hp / max_hp))
    # Draw BG first
    pygame.draw.rect(
        context.screen, HEALTH_BAR_BG, (int(x), int(y), int(width), int(height))
    )
    # Then fill
    if ratio > 0:
        pygame.draw.rect(
            context.screen,
            HEALTH_BAR_COLOR,
            (int(x), int(y), int(width * ratio), int(height)),
        )
    # Then border
    pygame.draw.rect(
        context.screen, BLACK, (int(x), int(y), int(width), int(height)), 1
    )


def draw_bar(context: UIContext, rect: pygame.Rect, ratio: float, color: tuple):
    if not context or not context.screen or not rect:
        return
    pygame.draw.rect(context.screen, DARK_GRAY, rect)
    fill = int(rect.width * clamp(ratio, 0, 1))
    if fill > 0:
        pygame.draw.rect(context.screen, color, (rect.x, rect.y, fill, rect.height))
    pygame.draw.rect(context.screen, BLACK, rect, 1)


# --- Phase-Specific Drawing Functions ---


def draw_player_info(state: GameState, context: UIContext):
    # FIX: Check rect
    if not context.info_panel_rect:
        return
    panel_rect = pygame.Rect(context.info_panel_rect)
    texture = context.get_ui_image("panel", (panel_rect.width, panel_rect.height))
    draw_beveled_rect(context.screen, panel_rect, PANEL_BG, texture)
    player = state.player
    xp_needed = player.xp_to_next_level()
    xp_text = f"{player.xp}/{xp_needed}" if player.level < 9 else "MAX"
    board_count = len([u for u in player.board.values() if u])
    max_board = player.level
    mats = player.materials
    info = [
        (f"HP: {player.health}", HEALTH_BAR_COLOR),
        (f"Red: {mats['RED']}", RED),
        (f"Green: {mats['GREEN']}", GREEN),
        (f"Blue: {mats['BLUE']}", BLUE),
        (f"Crystal: {player.crystals}", CYAN),
        (f"Lvl {player.level}  XP {xp_text}", YELLOW),
        (f"Units {board_count}/{max_board}", LIGHT_GRAY),
    ]

    line_height = context.get_font("default").get_linesize() + 4
    for i, (line, col) in enumerate(info):
        draw_text(
            context,
            line,
            (panel_rect.x + 10, panel_rect.y + 10 + i * line_height),
            "default",
            col,
        )

    # Draw player's relics beneath the info lines
    relic_size = RELIC_ICON_SIZE
    start_y = panel_rect.y + 10 + len(info) * line_height + 10
    for idx, art in enumerate(player.artifacts):
        x = panel_rect.x + 10 + (idx % 4) * (relic_size + 4)
        y = start_y + (idx // 4) * (relic_size + 4)
        img = context.get_artifact_image(art.name, (relic_size, relic_size))
        context.screen.blit(img, (x, y))


def draw_synergies(state: GameState, context: UIContext):
    # FIX: Check rect
    if not context.synergy_panel_rect:
        return
    panel_rect = context.synergy_panel_rect
    texture = context.get_ui_image("panel", (panel_rect.width, panel_rect.height))
    draw_beveled_rect(context.screen, panel_rect, PANEL_BG, texture)
    draw_text(
        context, "SYNERGIES:", (panel_rect.x + 10, panel_rect.y + 5), "default", GOLD
    )
    y_offset = 30
    if not state.player.active_synergies:
        return
    sorted_traits = sorted(state.player.active_synergies.keys())
    bar_width = panel_rect.width - 20
    for trait in sorted_traits:
        status = state.player.active_synergies[trait]
        count = status.get("count", 0)
        level_index = status.get("level_index", -1)
        definition = SYNERGY_DEFINITIONS.get(trait)
        if not definition or "thresholds" not in definition:
            continue
        thresholds = definition["thresholds"]
        color = INACTIVE_SYNERGY
        level_colors = [
            ACTIVE_SYNERGY_BRONZE,
            ACTIVE_SYNERGY_SILVER,
            ACTIVE_SYNERGY_GOLD,
        ]
        if level_index != -1:
            color = level_colors[min(level_index, len(level_colors) - 1)]
        next_thresh = (
            thresholds[min(level_index + 1, len(thresholds) - 1)] if thresholds else 0
        )
        ratio = count / next_thresh if next_thresh else 1.0
        label_y = panel_rect.y + y_offset
        icon = context.get_icon_image(trait, (16, 16))
        context.screen.blit(icon, (panel_rect.x + 8, label_y))
        draw_text(context, trait, (panel_rect.x + 28, label_y), "small", color)
        if definition.get("description"):
            draw_text(
                context,
                definition["description"],
                (panel_rect.x + 28, label_y + 14),
                "small",
                WHITE,
            )
        bar_rect = pygame.Rect(
            panel_rect.x + 28,
            label_y + 28,
            bar_width - 18,
            6,
        )
        draw_bar(context, bar_rect, ratio, color)
        draw_text(
            context,
            f"{count}/{next_thresh if next_thresh else count}",
            (bar_rect.right - 2, bar_rect.y - 4),
            "small",
            color,
            align="right",
        )
        y_offset += SYNERGY_LINE_HEIGHT


def draw_preparation_phase(state: GameState, context: UIContext):
    bg = context.get_background_image("shop")
    context.screen.blit(bg, (0, 0))
    player = state.player
    shop = state.shop
    selected_unit_info = context.selected_unit_info
    selected_item_info = context.selected_item_info
    draw_player_info(state, context)
    draw_synergies(state, context)
    draw_text(
        context,
        state.prepare_ui_message or "PREPARATION",
        (context.screen.get_width() // 2, 20),
        "large",
        YELLOW,
        align="center",
    )  # FIX default msg

    # Shop
    draw_text(context, "SHOP", (context.shop_x_start, context.shop_y - 25))
    for i in range(len(shop.slots)):
        rect = context.get_slot_rect(UnitLocation.SHOP, i)
        is_selected = (
            selected_unit_info is not None
            and selected_unit_info[0] == UnitLocation.SHOP
            and selected_unit_info[1] == i
        )
        draw_unit_prep(context, rect, shop.slots[i], is_selected)
        if shop.slots[i]:
            bundle = _mat_cost_bundle(shop.slots[i])
            cost_text = " ".join(f"{v}{k[0]}" for k, v in bundle.items() if v) or "FREE"
            # FIX: Check rect exists
            if rect:
                draw_text(
                    context,
                    cost_text,
                    (rect.centerx, rect.bottom + 2),
                    "small",
                    YELLOW,
                    align="center",
                )

    draw_button(
        context,
        context.refresh_shop_button_rect,
        f"Refresh ({REFRESH_CRYSTAL_COST}cr)",
        "small",
        context.hovered_button_rect == context.refresh_shop_button_rect,
    )
    draw_button(
        context,
        context.buy_xp_button_rect,
        f"Buy XP ({XP_BUY_CRYSTAL_COST}cr)",
        "small",
        context.hovered_button_rect == context.buy_xp_button_rect,
    )
    draw_button(
        context,
        context.craft_button_rect,
        "Craft / Dismantle",
        "small",
        context.hovered_button_rect == context.craft_button_rect,
    )
    draw_button(
        context,
        context.stats_toggle_button_rect,
        "Stats",
        "small",
        context.hovered_button_rect == context.stats_toggle_button_rect,
    )
    # FIX: Check rect
    if context.sell_area_rect:
        pygame.draw.rect(context.screen, RED, context.sell_area_rect, 2)
        draw_text(
            context,
            "SELL",
            context.sell_area_rect.center,
            "default",
            RED,
            align="center",
        )

    if state.allow_combat_start:
        draw_button(
            context,
            context.start_combat_button_rect,
            "START COMBAT",
            "small",
            context.hovered_button_rect == context.start_combat_button_rect,
        )
    else:
        draw_button(
            context,
            context.map_button_rect,
            "RETURN TO MAP",
            "small",
            context.hovered_button_rect == context.map_button_rect,
        )

    # Item Inventory
    draw_button(
        context,
        context.warehouse_button_rect,
        "Warehouse",
        "small",
        context.hovered_button_rect == context.warehouse_button_rect,
    )
    if context.warehouse_panel:
        context.warehouse_panel.draw()

    # Board grid and bench background
    # board_w = BOARD_COLS * (SLOT_SIZE + SLOT_MARGIN) - SLOT_MARGIN
    # board_h = BOARD_ROWS * (SLOT_SIZE + SLOT_MARGIN) - SLOT_MARGIN
    # board_rect = pygame.Rect(BOARD_X_START, BOARD_Y_START, board_w, board_h)
    # pygame.draw.rect(context.screen, LIGHT_GRAY, board_rect, 1)
    for r in range(BOARD_ROWS):
        for c in range(BOARD_COLS):
            cell_rect = context.get_slot_rect(UnitLocation.BOARD, (r, c))
            pygame.draw.rect(context.screen, GRID_LINE, cell_rect, 1)
    # preview_rect = pygame.Rect(BOARD_X_START, PREVIEW_Y_START, board_w, board_h)
    # pygame.draw.rect(context.screen, LIGHT_GRAY, preview_rect, 1)
    for r in range(BOARD_ROWS):
        for c in range(BOARD_COLS):
            cell_rect = context.get_slot_rect(UnitLocation.PREVIEW, (r, c))
            pygame.draw.rect(context.screen, GRID_LINE, cell_rect, 1)

    for unit, (row, col) in zip(
        state.enemy_preview_units, state.enemy_preview_positions
    ):
        rect = context.get_slot_rect(UnitLocation.PREVIEW, (row, col))
        draw_unit_prep(context, rect, unit, False)

    bench_w = BENCH_SLOTS * (SLOT_SIZE + SLOT_MARGIN) - SLOT_MARGIN
    bench_rect = pygame.Rect(BENCH_X_START, BENCH_Y, bench_w, SLOT_SIZE)
    pygame.draw.rect(context.screen, DARK_GRAY, bench_rect)

    # Bench & Board
    # Determine if an item is currently hovered to keep its unit items visible
    is_any_item_hovered = (
        context.hovered_rect
        and context.hovered_rect != context.sell_area_rect
        and state.hovered_info
        and "(" in state.hovered_info
    )  # weak check

    # Bench
    for i in range(len(player.bench)):
        rect = context.get_slot_rect(UnitLocation.BENCH, i)
        unit = player.bench[i]
        is_selected_unit = (
            selected_unit_info
            and selected_unit_info[0] == UnitLocation.BENCH
            and selected_unit_info[1] == i
        )
        # FIX: check rect exists
        is_hovered_unit = context.hovered_rect and rect and context.hovered_rect == rect
        is_unit_item_hovered = (
            is_any_item_hovered
            and rect
            and context.hovered_rect
            and rect.colliderect(context.hovered_rect)
            and not is_hovered_unit
        )

        draw_unit_prep(context, rect, unit, is_selected_unit)
        # FIX: Also draw items if an item on THIS unit is selected
        is_unit_item_selected = (
            selected_item_info
            and selected_item_info[0] == UnitLocation.EQUIPPED
            and selected_item_info[1][0] == UnitLocation.BENCH
            and selected_item_info[1][1] == i
        )
        if unit and (
            is_selected_unit
            or is_hovered_unit
            or is_unit_item_hovered
            or is_unit_item_selected
        ):
            for item_idx in range(MAX_ITEMS_EQUIPPED):  # Draw all slots
                item = (
                    unit.equipped_items[item_idx]
                    if item_idx < len(unit.equipped_items)
                    else None
                )
                item_rect = context.get_slot_rect(
                    UnitLocation.EQUIPPED, item_idx, base_rect=rect
                )
                # Check if this specific item is selected
                item_selected = (
                    selected_item_info
                    and selected_item_info[0] == UnitLocation.EQUIPPED
                    and item
                    and selected_item_info[2].id == item.id
                )
                draw_item_prep(context, item_rect, item, item_selected)

    # Board
    for (r, c), unit in player.board.items():
        rect = context.get_slot_rect(UnitLocation.BOARD, (r, c))
        is_selected_unit = (
            selected_unit_info
            and selected_unit_info[0] == UnitLocation.BOARD
            and selected_unit_info[1] == (r, c)
        )
        # FIX: check rect exists
        is_hovered_unit = context.hovered_rect and rect and context.hovered_rect == rect
        is_unit_item_hovered = (
            is_any_item_hovered
            and rect
            and context.hovered_rect
            and rect.colliderect(context.hovered_rect)
            and not is_hovered_unit
        )

        draw_unit_prep(context, rect, unit, is_selected_unit)
        # FIX: Also draw items if an item on THIS unit is selected
        is_unit_item_selected = (
            selected_item_info
            and selected_item_info[0] == UnitLocation.EQUIPPED
            and selected_item_info[1][0] == UnitLocation.BOARD
            and selected_item_info[1][1] == (r, c)
        )
        if unit and (
            is_selected_unit
            or is_hovered_unit
            or is_unit_item_hovered
            or is_unit_item_selected
        ):
            for item_idx in range(MAX_ITEMS_EQUIPPED):  # Draw all slots
                item = (
                    unit.equipped_items[item_idx]
                    if item_idx < len(unit.equipped_items)
                    else None
                )
                item_rect = context.get_slot_rect(
                    UnitLocation.EQUIPPED, item_idx, base_rect=rect
                )
                # Check if this specific item is selected
                item_selected = (
                    selected_item_info
                    and selected_item_info[0] == UnitLocation.EQUIPPED
                    and item
                    and selected_item_info[2].id == item.id
                )
                draw_item_prep(context, item_rect, item, item_selected)

    # Overlay MAX on unused slots when board is full
    board_count = len([u for u in player.board.values() if u])
    if board_count >= player.level:
        for r in range(BOARD_ROWS):
            for c in range(BOARD_COLS):
                if not player.board.get((r, c)):
                    rect = context.get_slot_rect(UnitLocation.BOARD, (r, c))
                    if rect:
                        surf = pygame.Surface(
                            (rect.width, rect.height), pygame.SRCALPHA
                        )
                        surf.fill((40, 40, 40, 100))
                        context.screen.blit(surf, rect)
                        draw_text(
                            context, "MAX", rect.center, "small", RED, align="center"
                        )
    # Draw hover info LAST so it's on top
    draw_hover_info(state, context)
    if context.drag_mgr:
        context.draw_drag_preview()
    if context.details_window:
        context.details_window.draw(context)
    if context.crafting_window:
        context.crafting_window.draw()
    if context.stats_panel:
        context.stats_panel.draw()

# ... (rest of drawing.py remains the same) ...
def draw_combat_phase(state: GameState, context: UIContext):
    bg = context.get_background_image("combat")
    context.screen.blit(bg, (0, 0))
    # Arena BG
    if context.combat_arena_rect:
        pygame.draw.rect(context.screen, DARK_GRAY, context.combat_arena_rect)
        pygame.draw.rect(context.screen, LIGHT_GRAY, context.combat_arena_rect, 2)
    # Panels
    draw_player_info(state, context)
    draw_synergies(state, context)
    is_overtime = state.combat_timer > 30  # Use raw value
    timer_color = RED if is_overtime else YELLOW
    timer_text = f"{state.current_node_type or 'COMBAT'}! Time: {state.combat_timer:.1f}s {'OVERTIME!' if is_overtime else ''}"  # FIX default type
    draw_text(
        context,
        timer_text,
        (context.screen.get_width() // 2, 20),
        "large",
        timer_color,
        align="center",
    )

    all_units = []
    if state.player_combat_team:
        all_units.extend(state.player_combat_team)
    if state.enemy_combat_team:
        all_units.extend(state.enemy_combat_team)
    for unit in all_units:
        if unit:
            draw_unit_combat(context, unit)
    draw_environment_effects(state, context)
    if state.visual_effects:
        for effect in state.visual_effects:
            if effect:
                draw_visual_effect(context, effect)
    if state.damage_floaters:
        for floater in state.damage_floaters:
            if floater:
                draw_damage_floater(context, floater)
    draw_button(
        context,
        context.stats_toggle_button_rect,
        "Stats",
        "small",
        context.hovered_button_rect == context.stats_toggle_button_rect,
    )
    draw_hover_info(state, context)
    if context.details_window:
        context.details_window.draw(context)
    if context.stats_panel:
        context.stats_panel.draw()

def draw_unit_combat(context: UIContext, unit: Unit):
    # FIX: Check context/screen
    if not unit or not context or not context.screen:
        return
    if (
        not unit.is_alive
        and unit.anim_state != AnimationState.DYING
        and unit.anim_timer > DEATH_ANIM_DURATION
    ):
        return

    x, y = int(unit.x), int(unit.y)
    current_radius = float(unit.radius)  # Use float for lerp

    # Handle death shrink
    progress = 0.0
    duration = 0.0
    if unit.anim_state == AnimationState.DYING:
        # FIX: handle zero duration
        duration = max(0.01, DEATH_ANIM_DURATION)
        progress = clamp(unit.anim_timer / duration, 0, 1)
        current_radius = unit.radius * (1.0 - progress)
    # FIX: Use int() for drawing
    if int(current_radius) < 1:
        return

    # Handle color lerping for animations
    base_color = context.map_color(unit.base_color_key)
    current_color = base_color
    if unit.anim_state in [
        AnimationState.HIT,
        AnimationState.HEALED,
        AnimationState.CASTING,
    ]:
        duration = ANIM_DURATIONS.get(unit.anim_state.name, 0.3)
        # FIX: handle zero duration
        progress = clamp(unit.anim_timer / max(0.01, duration), 0, 1)
        flash_color = context.map_color(unit.flash_color_key)
        current_color = lerp_color(flash_color, base_color, progress)
    elif unit.anim_state == AnimationState.DYING:
        # progress already calculated above
        current_color = lerp_color(base_color, BLACK, progress)
    # FIX: use int radius
    img = context.get_unit_image(
        unit.name, (int(current_radius * 2), int(current_radius * 2))
    )
    tinted = img.copy()
    tint_surf = pygame.Surface(tinted.get_size(), pygame.SRCALPHA)
    tint_surf.fill(current_color)
    tinted.blit(tint_surf, (0, 0), special_flags=pygame.BLEND_MULT)
    context.screen.blit(tinted, (x - int(current_radius), y - int(current_radius)))

    # Orientation Line
    base_angle = 0
    if unit.target and unit.target.is_alive:
        base_angle = math.atan2(unit.target.y - y, unit.target.x - x)
    else:
        base_angle = math.radians(-90) if not unit.is_enemy else math.radians(90)

    final_angle = base_angle + unit.rotation_offset
    # FIX: use int radius
    end_x = x + math.cos(final_angle) * int(current_radius)
    end_y = y + math.sin(final_angle) * int(current_radius)
    line_color = LIGHT_GRAY if current_color != LIGHT_GRAY else DARK_GRAY
    pygame.draw.line(context.screen, line_color, (x, y), (int(end_x), int(end_y)), 2)

    # FIX: use int radius
    if (
        unit.anim_state != AnimationState.DYING
        or unit.anim_timer < DEATH_ANIM_DURATION * 0.5
    ):
        if unit.level > 1:
            draw_text(
                context,
                "*" * unit.level,
                (x, y - int(current_radius) - 12),
                "small",
                GOLD,
                align="center",
            )
        hb_width = int(current_radius) * 2.5
        hb_height = 6
        hb_x = x - hb_width / 2.0
        hb_y = y + int(current_radius) + 4
        draw_health_bar(
            context,
            hb_x,
            hb_y,
            unit.current_hp,
            unit.current_stats.get("hp", 0),
            hb_width,
            hb_height,
        )  # FIX .get

        # ---------------- 状态效果图标 ---------------- #
        if unit.statuses:
            # 汇总：同名多层 → 取首个对象并累加层数
            summaries: list[tuple[StatusCategory, str, int]] = []
            for name, bucket in unit.statuses.items():
                if not bucket:
                    continue
                cat = bucket[0].category
                stacks = sum(st.stacks for st in bucket)
                icon_key = _CATEGORY_ICON_MAP.get(cat)
                if icon_key:
                    summaries.append((cat, icon_key, stacks))
            if summaries:
                # 排序：先 Debuff → Dot → Hot → 其他
                summaries.sort(key=lambda s: s[0].value)
                total = len(summaries)
                row_w = total * STATUS_ICON_SIZE + (total - 1) * STATUS_ICON_SPACING
                start_x = x - row_w / 2
                icon_y = hb_y + hb_height + 2
                for idx, (_, icon_key, stacks) in enumerate(summaries):
                    draw_x = start_x + idx * (STATUS_ICON_SIZE + STATUS_ICON_SPACING)
                    icon_img = context.get_icon_image(
                        icon_key, (STATUS_ICON_SIZE, STATUS_ICON_SIZE)
                    )
                    context.screen.blit(icon_img, (int(draw_x), int(icon_y)))
                    # 叠层数字（>1 时显示）
                    if stacks > 1:
                        draw_text(
                            context,
                            str(stacks),
                            (
                                draw_x + STATUS_ICON_SIZE / 2,
                                icon_y + STATUS_ICON_SIZE / 2,
                            ),
                            "small",
                            WHITE,
                            align="center",
                        )


def draw_environment_effects(state: GameState, context: UIContext) -> None:
    if not state.environment_effects:
        return
    for effect in state.environment_effects:
        if isinstance(effect, SteamCloudArea):
            _draw_steam_cloud(context, effect)


def _draw_steam_cloud(context: UIContext, cloud: SteamCloudArea) -> None:
    radius = int(cloud.radius)
    if radius <= 0:
        return
    fade = clamp(cloud.remaining / max(0.01, cloud.duration), 0.0, 1.0)
    base_alpha = int(160 * fade)
    if base_alpha <= 0:
        return
    color = context.map_color("STEAM_COLOR")
    elapsed = getattr(cloud, "elapsed", 0.0)
    pulse = math.sin(elapsed * 2.2) * 0.08
    surface = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
    center = radius
    offsets = getattr(cloud, "puff_offsets", [(0.0, 0.0)])
    for idx, (ox, oy) in enumerate(offsets):
        scale = clamp(0.55 + idx * 0.18 + pulse, 0.3, 1.0)
        puff_radius = max(6, int(radius * scale))
        offset_x = center + int(ox * radius * 0.6)
        offset_y = center + int(oy * radius * 0.6)
        puff_alpha = max(15, int(base_alpha * (0.85 - idx * 0.15)))
        pygame.draw.circle(
            surface,
            (color[0], color[1], color[2], puff_alpha),
            (offset_x, offset_y),
            min(puff_radius, radius),
        )
    ring_alpha = max(8, base_alpha // 3)
    pygame.draw.circle(
        surface,
        (color[0], color[1], color[2], ring_alpha),
        (center, center),
        radius,
        3,
    )
    context.screen.blit(surface, (int(cloud.x) - radius, int(cloud.y) - radius))


def draw_visual_effect(context: UIContext, effect: VisualEffect):
    # FIX: Check context/screen
    if not effect or not context or not context.screen:
        return
    # FIX: handle zero lifespan
    progress = clamp(effect.timer / max(0.01, effect.lifespan), 0, 1)
    alpha = int(255 * (1.0 - progress))
    if alpha <= 0:
        return  # Don't draw if fully transparent
    ix, iy = int(effect.x), int(effect.y)
    draw_color = context.map_color(effect.color_key)
    size = int(max(1, effect.size))  # ensure size is at least 1

    if effect.type in [EffectType.PROJECTILE_BASIC, EffectType.PROJECTILE_MAGIC]:
        # FIX: Apply alpha
        shape_surf = pygame.Surface((size * 2, size * 2), pygame.SRCALPHA)
        pygame.draw.circle(
            shape_surf,
            (draw_color[0], draw_color[1], draw_color[2], alpha),
            (size, size),
            size,
        )
        context.screen.blit(shape_surf, (ix - size, iy - size))
        # pygame.draw.circle(context.screen, draw_color, (ix, iy), size)
    elif effect.type == EffectType.SLASH:
        end_x = ix + math.cos(effect.angle) * size * 1.5
        end_y = iy + math.sin(effect.angle) * size * 1.5
        # Alpha line drawing is complex, just draw solid short-lived line
        pygame.draw.line(
            context.screen, draw_color, (ix, iy), (int(end_x), int(end_y)), 3
        )
    elif effect.type in [
        EffectType.HEAL_AURA,
        EffectType.BUFF_AURA,
        EffectType.CAST_AURA,
        EffectType.DEATH_EFFECT,
        EffectType.HIT_SPARK,
    ]:
        radius_f = (
            effect.size * (progress * 1.5)
            if effect.type != EffectType.DEATH_EFFECT
            else effect.size * (1 - progress)
        )
        radius = int(radius_f)
        if radius > 1:
            shape_surf = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
            inner_alpha = alpha // (2 if effect.type == EffectType.HIT_SPARK else 3)
            pygame.draw.circle(
                shape_surf,
                (draw_color[0], draw_color[1], draw_color[2], inner_alpha),
                (radius, radius),
                radius,
            )
            if effect.type != EffectType.DEATH_EFFECT:
                pygame.draw.circle(
                    shape_surf,
                    (draw_color[0], draw_color[1], draw_color[2], alpha),
                    (radius, radius),
                    radius,
                    2,
                )
            context.screen.blit(shape_surf, (ix - radius, iy - radius))


def draw_damage_floater(context: UIContext, floater: DamageFloater):
    # FIX: Check context/screen
    if not floater or not context or not context.screen:
        return
    # FIX: handle zero lifespan
    alpha = int(255 * (1.0 - (floater.timer / max(0.01, floater.lifespan))))
    if alpha <= 0:
        return

    color = context.map_color(floater.color_key)
    font_key = "small" if len(floater.text) < 5 else "default"
    # FIX: alpha text rendering
    text_surface = context.get_font(font_key).render(floater.text, True, color)
    text_surface.set_alpha(alpha)
    temp_surface = pygame.Surface(text_surface.get_size(), pygame.SRCALPHA)
    temp_surface.blit(text_surface, (0, 0))
    rect = temp_surface.get_rect(center=(int(floater.x), int(floater.y)))
    context.screen.blit(temp_surface, rect)


def draw_map_phase(state: GameState, context: UIContext):
    # FIX: Check context/screen
    if not context or not context.screen:
        return
    bg = context.get_background_image("map")
    context.screen.blit(bg, (0, 0))
    draw_player_info(state, context)
    draw_text(
        context,
        "NAVIGATION MAP",
        (context.screen.get_width() // 2, context.map_y_start - 40),
        "large",
        GOLD,
        align="center",
    )  # FIX: move up
    current_node = state.game_map.get_node(state.current_node_id)
    for node_id, node in state.game_map.nodes.items():  # FIX iterate items
        if not node:
            continue
        start_pos = (int(node.x), int(node.y))
        for next_node_id in node.next_nodes:
            next_node = state.game_map.get_node(next_node_id)
            if next_node:
                end_pos = (int(next_node.x), int(next_node.y))
                color, width = (MAP_PATH, 2)
                if (
                    node.node_id == state.current_node_id
                    and current_node
                    and next_node_id in current_node.next_nodes
                ):
                    color, width = (YELLOW, 3)
                elif node.visited and next_node.visited:
                    color, width = (LIGHT_GRAY, 2)
                pygame.draw.line(context.screen, color, start_pos, end_pos, width)
    for node_id, node in state.game_map.nodes.items():
        if not node:
            continue
        color = (
            MAP_NODE_CURRENT
            if node_id == state.current_node_id
            else MAP_NODE_VISITED if node.visited else MAP_NODE_BG
        )
        border_color, border_width = (GRAY, 1)
        # FIX: only show reachable nodes if current node is visited
        if current_node and node_id in current_node.next_nodes and current_node.visited:
            border_color, border_width = (YELLOW, 3)
        pygame.draw.circle(
            context.screen, color, (int(node.x), int(node.y)), node.radius
        )
        pygame.draw.circle(
            context.screen,
            border_color,
            (int(node.x), int(node.y)),
            node.radius,
            border_width,
        )
        node_text_map = {
            "HARD": "combat",
            "MEDIUM": "combat",
            "EASY": "combat",
            "BOSS": "boss",
            "SHOP": "shop",
            "EVENT": "event",
        }
        icon_key = next(
            (v for k, v in node_text_map.items() if k in node.node_type), "event"
        )
        img = context.get_icon_image(icon_key, (node.radius * 2, node.radius * 2))
        context.screen.blit(img, (int(node.x - node.radius), int(node.y - node.radius)))
    draw_hover_info(state, context)
    draw_button(
        context,
        context.settings_button_rect,
        "Settings",
        "small",
        context.hovered_button_rect == context.settings_button_rect,
    )
    draw_button(
        context,
        context.stats_toggle_button_rect,
        "Stats",
        "small",
        context.hovered_button_rect == context.stats_toggle_button_rect,
    )
    if context.stats_panel:
        context.stats_panel.draw()

def draw_main_menu(state: GameState, context: UIContext):
    if not context or not context.screen:
        return
    draw_text(
        context,
        "CLOCKWORK REQUIEM",
        (context.screen.get_width() // 2, context.screen.get_height() // 4),
        "menu",
        GOLD,
        align="center",
    )
    draw_text(
        context,
        "A Rogue-lite Auto-Battler",
        (context.screen.get_width() // 2, context.screen.get_height() // 4 + 60),
        "large",
        LIGHT_GRAY,
        align="center",
    )
    draw_button(
        context,
        context.start_menu_button_rect,
        "Start New Run",
        "large",
        context.hovered_button_rect == context.start_menu_button_rect,
    )
    draw_button(
        context,
        context.settings_button_rect,
        "Settings",
        "small",
        context.hovered_button_rect == context.settings_button_rect,
    )


# ----------------- 新增：难度选择 -----------------
def draw_difficulty_select(state: GameState, context: UIContext):
    if not context or not context.screen:
        return
    context.screen.fill(BLACK)
    draw_text(
        context,
        "SELECT DIFFICULTY",
        (context.screen.get_width() // 2, context.screen.get_height() // 4),
        "menu",
        GOLD,
        align="center",
    )
    labels = ["EASY", "MEDIUM", "HARD"]
    context.difficulty_button_rects = [
        pygame.Rect(
            context.screen.get_width() // 2 - 100,
            context.screen.get_height() // 2 - 70 + i * 70,
            200,
            60,
        )
        for i in range(len(labels))
    ]
    for lbl, rect in zip(labels, context.difficulty_button_rects):
        draw_button(
            context,
            rect,
            lbl.title(),
            "large",
            context.hovered_button_rect == rect,
        )


# ----------------- 新增：主题选择 -----------------
def draw_theme_select(state: GameState, context: UIContext):
    if not context or not context.screen:
        return
    context.screen.fill(BLACK)
    draw_text(
        context,
        f"ACT {state.act}: CHOOSE THEME",
        (context.screen.get_width() // 2, context.screen.get_height() // 4),
        "menu",
        GOLD,
        align="center",
    )
    themes = state.available_themes
    if not themes:
        return
    w = context.screen.get_width()
    context.theme_button_rects = []
    segment = w // max(1, len(themes))
    for i, t in enumerate(themes):
        rect = pygame.Rect(
            segment * i + segment // 2 - 100,
            context.screen.get_height() // 2,
            200,
            60,
        )
        context.theme_button_rects.append(rect)
        draw_button(
            context,
            rect,
            t.title(),
            "large",
            context.hovered_button_rect == rect,
        )


def draw_game_over(state: GameState, context: UIContext):
    if not context or not context.screen:
        return
    draw_text(
        context,
        "GAME OVER",
        (context.screen.get_width() // 2, context.screen.get_height() // 2 - 100),
        "menu",
        RED,
        align="center",
    )
    node = state.game_map.get_node(state.current_node_id)
    node_info = f"Node {state.current_node_id} ({node.node_type if node else '?'})"
    draw_text(
        context,
        f"Defeated at {node_info}",
        (context.screen.get_width() // 2, context.screen.get_height() // 2 + 10),
        "default",
        WHITE,
        align="center",
    )
    draw_button(
        context,
        context.restart_button_rect,
        "Restart Run",
        "large",
        context.hovered_button_rect == context.restart_button_rect,
    )
    draw_button(
        context,
        context.main_menu_button_rect,
        "Main Menu",
        "large",
        context.hovered_button_rect == context.main_menu_button_rect,
    )
    draw_button(
        context,
        context.settings_button_rect,
        "Settings",
        "small",
        context.hovered_button_rect == context.settings_button_rect,
    )


def draw_run_complete(state: GameState, context: UIContext):
    if not context or not context.screen:
        return
    draw_text(
        context,
        "RUN COMPLETE!",
        (context.screen.get_width() // 2, context.screen.get_height() // 2 - 100),
        "menu",
        GREEN,
        align="center",
    )
    draw_text(
        context,
        "CONGRATULATIONS, BOSS DEFEATED",
        (context.screen.get_width() // 2, context.screen.get_height() // 2 - 20),
        "large",
        GOLD,
        align="center",
    )
    draw_text(
        context,
        f"Final Health: {state.player.health}",
        (context.screen.get_width() // 2, context.screen.get_height() // 2 + 20),
        "default",
        WHITE,
        align="center",
    )
    draw_button(
        context,
        context.restart_button_rect,
        "Start New Run",
        "large",
        context.hovered_button_rect == context.restart_button_rect,
    )
    draw_button(
        context,
        context.main_menu_button_rect,
        "Main Menu",
        "large",
        context.hovered_button_rect == context.main_menu_button_rect,
    )
    draw_button(
        context,
        context.settings_button_rect,
        "Settings",
        "small",
        context.hovered_button_rect == context.settings_button_rect,
    )


def draw_event_choice(state: GameState, context: UIContext):
    if not context or not context.screen or not context.event_choice_rect:
        return
    tex = context.get_ui_image(
        "panel", (context.event_choice_rect.width, context.event_choice_rect.height)
    )
    draw_beveled_rect(context.screen, context.event_choice_rect, PANEL_BG, tex)
    pygame.draw.rect(
        context.screen, GRAY, context.event_choice_rect, 2, border_radius=10
    )
    draw_text(
        context,
        "EVENT: CHOOSE A REWARD",
        (context.event_choice_rect.centerx, context.event_choice_rect.top + 20),
        "large",
        YELLOW,
        align="center",
    )
    for choice in state.event_choices:
        rect = choice.get("rect")
        is_hovered = (
            context.hovered_button_rect and rect and context.hovered_button_rect == rect
        )
        draw_button(context, rect, choice.get("text", "?"), "small", is_hovered)
    draw_button(
        context,
        context.settings_button_rect,
        "Settings",
        "small",
        context.hovered_button_rect == context.settings_button_rect,
    )


def draw_settings(state: GameState, context: UIContext):
    if not context or not context.screen:
        return
    draw_text(
        context,
        "SETTINGS",
        (context.screen.get_width() // 2, 100),
        "menu",
        GOLD,
        align="center",
    )
    draw_text(
        context,
        f"Volume: {int(state.volume * 100)}%",
        (context.screen.get_width() // 2, context.screen.get_height() // 2 - 40),
        "large",
        WHITE,
        align="center",
    )
    draw_button(
        context,
        context.volume_down_rect,
        "-",
        "large",
        context.hovered_button_rect == context.volume_down_rect,
    )
    draw_button(
        context,
        context.volume_up_rect,
        "+",
        "large",
        context.hovered_button_rect == context.volume_up_rect,
    )
    res = state.resolution_options[state.resolution_index]
    draw_text(
        context,
        f"Resolution: {res[0]}x{res[1]}",
        (context.screen.get_width() // 2, context.screen.get_height() // 2 + 20),
        "large",
        WHITE,
        align="center",
    )
    draw_button(
        context,
        context.resolution_rect,
        "Change",
        "small",
        context.hovered_button_rect == context.resolution_rect,
    )
    draw_button(
        context,
        context.settings_back_button_rect,
        "Return",
        "large",
        context.hovered_button_rect == context.settings_back_button_rect,
    )
    if state.previous_phase and state.previous_phase != GamePhase.MAIN_MENU:
        draw_button(
            context,
            context.settings_abandon_button_rect,
            "Abandon Run",
            "small",
            context.hovered_button_rect == context.settings_abandon_button_rect,
        )