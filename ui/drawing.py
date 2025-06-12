from __future__ import annotations
import pygame
import math
from typing import Dict, Any, Optional # FIX: add Optional
from engine.game_state import GameState
from engine.classes import Unit, Item, VisualEffect, DamageFloater
from engine.enums import AnimationState, EffectType
from engine.utils import lerp, lerp_color, clamp
from ui.ui_context import UIContext
from ui.constants import (
    KEY_TO_COLOR, RARITY_COLORS, GOLD, HIGHLIGHT_COLOR, WHITE, BLACK, GRAY, RED, GREEN,
    PANEL_BG, DARK_GRAY, BUTTON_HOVER, BUTTON_BG, ITEM_COLOR,
    INACTIVE_SYNERGY, ACTIVE_SYNERGY_BRONZE, ACTIVE_SYNERGY_SILVER, ACTIVE_SYNERGY_GOLD,
    MAP_NODE_BG, MAP_NODE_CURRENT, MAP_NODE_VISITED, MAP_PATH, YELLOW, LIGHT_GRAY,
    HEALTH_BAR_BG, HEALTH_BAR_COLOR,
    SYNERGY_LINE_HEIGHT, ANIM_DURATIONS, DEATH_ANIM_DURATION, MAX_ITEMS_EQUIPPED
)
from data.definitions import SYNERGY_DEFINITIONS
from states.enums import GamePhase, UnitLocation


# --- Helper Drawing Functions ---
def draw_text(context: UIContext, text: str, pos: tuple, font_key="default", color=WHITE, align='left', alpha=255):
    # FIX: Ensure context and screen exist
    if not context or not context.screen: return
    font_obj = context.get_font(font_key)
    lines = str(text).split('\n'); y = pos[1]
    line_height = font_obj.get_linesize(); surfaces = []
    max_width = 0
    for line in lines:
        text_surface = font_obj.render(line, True, color)
        max_width = max(max_width, text_surface.get_width())
        if alpha < 255:
            # FIX: Alpha blending method
            temp_surf = pygame.Surface(text_surface.get_size(), pygame.SRCALPHA)
            text_surface.set_alpha(alpha)
            temp_surf.blit(text_surface, (0,0))
            text_surface = temp_surf # Use the surface with alpha
        surfaces.append(text_surface)

    final_y = y
    x_offset = 0
    if align == 'center': x_offset = -max_width / 2.0
    elif align == 'right': x_offset = -max_width

    for text_surface in surfaces:
        draw_x = pos[0]
        if align == 'center': draw_x = pos[0] - text_surface.get_width() / 2.0
        elif align == 'right': draw_x = pos[0] - text_surface.get_width()

        context.screen.blit(text_surface, (int(draw_x), int(final_y)))
        final_y += line_height

def draw_button(context: UIContext, rect: Optional[pygame.Rect], text: str, font_key: str, is_hovered: bool):
      # FIX: Check if rect exists
     if not rect or not context or not context.screen: return
     color = BUTTON_HOVER if is_hovered else BUTTON_BG
     pygame.draw.rect(context.screen, color, rect, border_radius=5)
     pygame.draw.rect(context.screen, LIGHT_GRAY, rect, 2, border_radius=5)
     draw_text(context, text, rect.center, font_key, WHITE, align='center')

def draw_hover_info(state: GameState, context: UIContext):
       # FIX: Check context/screen
      if not context or not context.screen: return
      # Draw highlight box only if not hovering a button
      if context.hovered_rect and not context.hovered_button_rect:
          pygame.draw.rect(context.screen, YELLOW, context.hovered_rect, 2) # Increased width

      if state.hovered_info:
        mx, my = pygame.mouse.get_pos()
        info_lines = state.hovered_info.split('\n')
        font = context.get_font("small")
        # FIX: Check if info_lines is empty
        max_line_width = max(font.size(line)[0] for line in info_lines) if info_lines else 10
        info_height = len(info_lines) * font.get_linesize() + 10
        info_width = max_line_width + 20
        # FIX: Default info rect position to mouse
        info_rect = pygame.Rect(mx + 15, my - info_height/2 , info_width, info_height)
        # Adjust position if hovering a specific rect
        if context.hovered_rect:
             info_rect.left = context.hovered_rect.right + 5
             info_rect.centery = context.hovered_rect.centery

        # Clamp to screen bounds
        info_rect.left = clamp(info_rect.left, 5, context.screen.get_width() - info_width - 5)
        info_rect.top = clamp(info_rect.top, 5, context.screen.get_height() - info_height - 5)

        pygame.draw.rect(context.screen, BLACK, info_rect, border_radius=3)
        pygame.draw.rect(context.screen, LIGHT_GRAY, info_rect, 1, border_radius=3)
        draw_text(context, state.hovered_info, (info_rect.left + 10, info_rect.top + 5), "small", WHITE)

def draw_unit_prep(context: UIContext, rect: Optional[pygame.Rect], unit: Optional[Unit], is_selected: bool):
    # FIX: Check rect
    if not rect or not context or not context.screen: return
    pygame.draw.rect(context.screen, DARK_GRAY, rect, 0)
    pygame.draw.rect(context.screen, GRAY, rect, 2)
    if unit:
        color = RARITY_COLORS.get(unit.rarity, WHITE)
        pygame.draw.rect(context.screen, color, rect.inflate(-4,-4), 0)
        draw_text(context, f"{unit.name[0]}", rect.center, "large", BLACK, align='center') # Use first letter
        star_y = rect.bottom - 12 # FIX: place stars better
        if unit.level >= 2: draw_text(context, '*' * unit.level, (rect.centerx, star_y), "small", GOLD, align='center')
    if is_selected: pygame.draw.rect(context.screen, HIGHLIGHT_COLOR, rect, 4)

def draw_item_prep(context: UIContext, rect: Optional[pygame.Rect], item: Optional[Item], is_selected: bool):
      # FIX: Check rect
      if not rect or not context or not context.screen: return
      pygame.draw.rect(context.screen, DARK_GRAY, rect, 0); pygame.draw.rect(context.screen, GRAY, rect, 1)
      if item:
         color = ITEM_COLOR if item.type == "COMPONENT" else GOLD
         pygame.draw.rect(context.screen, color, rect.inflate(-4,-4), 0) # Inflate more
         draw_text(context, item.name[0], rect.center, "small", WHITE, align='center')
      if is_selected: pygame.draw.rect(context.screen, HIGHLIGHT_COLOR, rect, 3)

def draw_health_bar(context: UIContext, x, y, current_hp, max_hp, width, height):
      # FIX: Check context/screen
      if not context or not context.screen: return
      if max_hp <= 0 or width < 1: return
      ratio = max(0, min(1, current_hp / max_hp))
      # Draw BG first
      pygame.draw.rect(context.screen, HEALTH_BAR_BG, (int(x), int(y), int(width), int(height)))
      # Then fill
      if ratio > 0: pygame.draw.rect(context.screen, HEALTH_BAR_COLOR, (int(x), int(y), int(width * ratio), int(height)))
      # Then border
      pygame.draw.rect(context.screen, BLACK, (int(x), int(y), int(width), int(height)), 1)

# --- Phase-Specific Drawing Functions ---

def draw_player_info(state: GameState, context: UIContext):
     # FIX: Check rect
    if not context.info_panel_rect: return
    panel_rect = pygame.Rect(context.info_panel_rect)
    pygame.draw.rect(context.screen, PANEL_BG, panel_rect)
    pygame.draw.rect(context.screen, GRAY, panel_rect, 1)
    player = state.player
    xp_needed = player.xp_to_next_level()
    xp_text = f"{player.xp}/{xp_needed}" if player.level < 9 else "MAX"
    board_count = len([u for u in player.board.values() if u]); max_board = player.level
    info = [ f"Health: {player.health}", f"Gold: {player.gold}", f"Level: {player.level}", f"XP: {xp_text}", f"Units: {board_count}/{max_board}", "--- Artifacts ---" ]
    info.extend([a.name for a in player.artifacts if a] if player.artifacts else ["None"])
    line_height = context.get_font("default").get_linesize()
    for i, line in enumerate(info):
         font_key = "small" if i > 4 else "default"
         # Adjust y offset based on font size change
         current_y = panel_rect.y + 10 + i * line_height
         if i > 4 : current_y -= (i-4) * (context.get_font("default").get_linesize() - context.get_font("small").get_linesize())
         draw_text(context, line, (panel_rect.x + 10, current_y), font_key)

def draw_synergies(state: GameState, context: UIContext):
      # FIX: Check rect
     if not context.synergy_panel_rect: return
     panel_rect = context.synergy_panel_rect
     pygame.draw.rect(context.screen, PANEL_BG, panel_rect)
     pygame.draw.rect(context.screen, GRAY, panel_rect, 1)
     draw_text(context, "SYNERGIES:", (panel_rect.x+10, panel_rect.y+5), "default", GOLD)
     y_offset = 30;
     # FIX: ensure active_synergies is not None
     if not state.player.active_synergies: return
     sorted_traits = sorted(state.player.active_synergies.keys())
     for trait in sorted_traits:
          status = state.player.active_synergies[trait]; count = status.get('count', 0); level_index = status.get('level_index', -1) # FIX .get
          definition = SYNERGY_DEFINITIONS.get(trait)
           # FIX: check definition and thresholds exist
          if not definition or 'thresholds' not in definition: continue
          thresholds = definition['thresholds']; color = INACTIVE_SYNERGY
          level_colors = [ACTIVE_SYNERGY_BRONZE, ACTIVE_SYNERGY_SILVER, ACTIVE_SYNERGY_GOLD]
          if level_index != -1: color = level_colors[min(level_index, len(level_colors)-1)]
          next_threshold_str = "MAX"
          # FIX: bounds check for next_threshold
          if level_index == -1 and thresholds:
               next_threshold_str = str(thresholds[0])
          elif level_index != -1 and level_index < len(thresholds) -1 :
               next_threshold_str = str(thresholds[level_index+1])

          count_text = f"[{count}/{next_threshold_str}]"
          draw_text(context, f"{count_text} {trait}", (panel_rect.x + 10, panel_rect.y + y_offset), "small", color); y_offset += SYNERGY_LINE_HEIGHT


def draw_preparation_phase(state: GameState, context: UIContext):
    player = state.player; shop = state.shop
    selected_unit_info = context.selected_unit_info
    selected_item_info = context.selected_item_info
    draw_player_info(state, context); draw_synergies(state, context)
    draw_text(context, state.prepare_ui_message or "PREPARATION", (context.screen.get_width() // 2, 20), "large", YELLOW, align='center') # FIX default msg

    # Shop
    draw_text(context, "SHOP", (context.shop_x_start, context.shop_y - 25))
    for i in range(len(shop.slots)):
        rect = context.get_slot_rect(UnitLocation.SHOP, i)
        is_selected = selected_unit_info is not None and selected_unit_info[0] == UnitLocation.SHOP and selected_unit_info[1] == i
        draw_unit_prep(context, rect, shop.slots[i], is_selected)
        if shop.slots[i]:
             cost_text = f"{shop.slots[i].get_cost()}G"
             # FIX: Check rect exists
             if rect: draw_text(context, cost_text, (rect.centerx, rect.bottom + 2), "small", GOLD, align='center')

    draw_button(context, context.refresh_shop_button_rect, f"Refresh ({2}G)", "default", context.hovered_button_rect == context.refresh_shop_button_rect)
    draw_button(context, context.buy_xp_button_rect, f"Buy XP ({4}G)", "default", context.hovered_button_rect == context.buy_xp_button_rect)
     # FIX: Check rect
    if context.sell_area_rect:
        pygame.draw.rect(context.screen, RED, context.sell_area_rect, 2)
        draw_text(context, "SELL", context.sell_area_rect.center, "default", RED, align='center')

    if state.allow_combat_start:
         draw_button(context, context.start_combat_button_rect, "START COMBAT", "default", context.hovered_button_rect == context.start_combat_button_rect)
    else:
         draw_button(context, context.map_button_rect, "RETURN TO MAP", "default", context.hovered_button_rect == context.map_button_rect)

    # Item Inventory
    draw_text(context, "ITEMS:", (context.inventory_x_start, context.inventory_y - 20), "default", ITEM_COLOR)
    for i in range(len(player.item_inventory)):
         rect = context.get_slot_rect(UnitLocation.INVENTORY, i)
         item = player.item_inventory[i]
         is_selected = selected_item_info is not None and selected_item_info[0] == UnitLocation.INVENTORY and selected_item_info[1] == i
         draw_item_prep(context, rect, item, is_selected)

    # Bench & Board
    # Determine if an item is currently hovered to keep its unit items visible
    is_any_item_hovered = context.hovered_rect and context.hovered_rect != context.sell_area_rect and state.hovered_info and "(" in state.hovered_info # weak check

    # Bench
    for i in range(len(player.bench)):
        rect = context.get_slot_rect(UnitLocation.BENCH, i); unit = player.bench[i]
        is_selected_unit = selected_unit_info and selected_unit_info[0] == UnitLocation.BENCH and selected_unit_info[1] == i
        # FIX: check rect exists
        is_hovered_unit = context.hovered_rect and rect and context.hovered_rect == rect
        is_unit_item_hovered = is_any_item_hovered and rect and context.hovered_rect and rect.colliderect(context.hovered_rect) and not is_hovered_unit

        draw_unit_prep(context, rect, unit, is_selected_unit)
        # FIX: Also draw items if an item on THIS unit is selected
        is_unit_item_selected = selected_item_info and selected_item_info[0] == UnitLocation.EQUIPPED and selected_item_info[1][0] == UnitLocation.BENCH and selected_item_info[1][1] == i
        if unit and (is_selected_unit or is_hovered_unit or is_unit_item_hovered or is_unit_item_selected):
              for item_idx in range(MAX_ITEMS_EQUIPPED): # Draw all slots
                   item = unit.equipped_items[item_idx] if item_idx < len(unit.equipped_items) else None
                   item_rect = context.get_slot_rect(UnitLocation.EQUIPPED, item_idx, base_rect=rect)
                   # Check if this specific item is selected
                   item_selected = selected_item_info and selected_item_info[0] == UnitLocation.EQUIPPED and item and selected_item_info[2].id == item.id
                   draw_item_prep(context, item_rect, item, item_selected)

    # Board
    for (r,c), unit in player.board.items():
        rect = context.get_slot_rect(UnitLocation.BOARD, (r,c))
        is_selected_unit = selected_unit_info and selected_unit_info[0] == UnitLocation.BOARD and selected_unit_info[1] == (r,c)
        # FIX: check rect exists
        is_hovered_unit = context.hovered_rect and rect and context.hovered_rect == rect
        is_unit_item_hovered = is_any_item_hovered and rect and context.hovered_rect and rect.colliderect(context.hovered_rect) and not is_hovered_unit

        draw_unit_prep(context, rect, unit, is_selected_unit)
        # FIX: Also draw items if an item on THIS unit is selected
        is_unit_item_selected = selected_item_info and selected_item_info[0] == UnitLocation.EQUIPPED and selected_item_info[1][0] == UnitLocation.BOARD and selected_item_info[1][1] == (r,c)
        if unit and (is_selected_unit or is_hovered_unit or is_unit_item_hovered or is_unit_item_selected):
             for item_idx in range(MAX_ITEMS_EQUIPPED): # Draw all slots
                  item = unit.equipped_items[item_idx] if item_idx < len(unit.equipped_items) else None
                  item_rect = context.get_slot_rect(UnitLocation.EQUIPPED, item_idx, base_rect=rect)
                  # Check if this specific item is selected
                  item_selected = selected_item_info and selected_item_info[0] == UnitLocation.EQUIPPED and item and selected_item_info[2].id == item.id
                  draw_item_prep(context, item_rect, item, item_selected)
    # Draw hover info LAST so it's on top
    draw_hover_info(state, context)

# ... (rest of drawing.py remains the same) ...
def draw_combat_phase(state: GameState, context: UIContext):
    # Arena BG
     # FIX: check rect
    if context.combat_arena_rect:
        pygame.draw.rect(context.screen, DARK_GRAY, context.combat_arena_rect)
        pygame.draw.rect(context.screen, LIGHT_GRAY, context.combat_arena_rect, 2)
    # Panels
    draw_player_info(state, context); draw_synergies(state, context)
    is_overtime = state.combat_timer > 30 # Use raw value
    timer_color = RED if is_overtime else YELLOW
    timer_text = f"{state.current_node_type or 'COMBAT'}! Time: {state.combat_timer:.1f}s {'OVERTIME!' if is_overtime else ''}" # FIX default type
    draw_text(context, timer_text, (context.screen.get_width() // 2, 20), "large", timer_color, align='center')

    all_units = []
    if state.player_combat_team: all_units.extend(state.player_combat_team)
    if state.enemy_combat_team: all_units.extend(state.enemy_combat_team)
    for unit in all_units:
        if unit: draw_unit_combat(context, unit)
    if state.visual_effects:
       for effect in state.visual_effects:
           if effect: draw_visual_effect(context, effect)
    if state.damage_floaters:
       for floater in state.damage_floaters:
           if floater: draw_damage_floater(context, floater)

    draw_hover_info(state, context)

def draw_unit_combat(context: UIContext, unit: Unit):
    # FIX: Check context/screen
    if not unit or not context or not context.screen: return
    if not unit.is_alive and unit.anim_state != AnimationState.DYING and unit.anim_timer > DEATH_ANIM_DURATION: return

    x, y = int(unit.x), int(unit.y)
    current_radius = float(unit.radius) # Use float for lerp

    # Handle death shrink
    progress = 0.0
    duration = 0.0
    if unit.anim_state == AnimationState.DYING:
          # FIX: handle zero duration
          duration = max(0.01, DEATH_ANIM_DURATION)
          progress = clamp(unit.anim_timer / duration, 0, 1)
          current_radius = unit.radius * (1.0 - progress)
    # FIX: Use int() for drawing
    if int(current_radius) < 1: return

    # Handle color lerping for animations
    base_color = context.map_color(unit.base_color_key)
    current_color = base_color
    if unit.anim_state in [AnimationState.HIT, AnimationState.HEALED, AnimationState.CASTING]:
         duration = ANIM_DURATIONS.get(unit.anim_state.name, 0.3)
         # FIX: handle zero duration
         progress = clamp(unit.anim_timer / max(0.01, duration), 0, 1)
         flash_color = context.map_color(unit.flash_color_key)
         current_color = lerp_color(flash_color, base_color, progress)
    elif unit.anim_state == AnimationState.DYING:
         # progress already calculated above
         current_color = lerp_color(base_color, BLACK, progress)
    # FIX: use int radius
    pygame.draw.circle(context.screen, current_color, (x, y), int(current_radius))

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
    pygame.draw.line(context.screen, line_color, (x,y), (int(end_x), int(end_y)), 2)

    # FIX: use int radius
    if unit.anim_state != AnimationState.DYING or unit.anim_timer < DEATH_ANIM_DURATION * 0.5:
        if unit.level > 1: draw_text(context, '*' * unit.level, (x, y - int(current_radius) - 12), "small", GOLD, align='center')
        hb_width = int(current_radius) * 2.5; hb_height = 6
        hb_x = x - hb_width / 2.0; hb_y = y + int(current_radius) + 4
        draw_health_bar(context, hb_x, hb_y, unit.current_hp, unit.current_stats.get('hp',0), hb_width, hb_height) # FIX .get

def draw_visual_effect(context: UIContext, effect: VisualEffect):
     # FIX: Check context/screen
    if not effect or not context or not context.screen: return
    # FIX: handle zero lifespan
    progress = clamp(effect.timer / max(0.01, effect.lifespan), 0, 1)
    alpha = int(255 * (1.0 - progress))
    if alpha <= 0 : return # Don't draw if fully transparent
    ix, iy = int(effect.x), int(effect.y)
    draw_color = context.map_color(effect.color_key)
    size = int(max(1, effect.size)) # ensure size is at least 1

    if effect.type in [EffectType.PROJECTILE_BASIC, EffectType.PROJECTILE_MAGIC]:
        # FIX: Apply alpha
        shape_surf = pygame.Surface((size*2, size*2), pygame.SRCALPHA)
        pygame.draw.circle(shape_surf, (draw_color[0], draw_color[1], draw_color[2], alpha), (size, size), size)
        context.screen.blit(shape_surf, (ix - size, iy - size))
        # pygame.draw.circle(context.screen, draw_color, (ix, iy), size)
    elif effect.type == EffectType.SLASH:
         end_x = ix + math.cos(effect.angle) * size * 1.5
         end_y = iy + math.sin(effect.angle) * size * 1.5
         # Alpha line drawing is complex, just draw solid short-lived line
         pygame.draw.line(context.screen, draw_color, (ix, iy), (int(end_x), int(end_y)), 3)
    elif effect.type in [EffectType.HEAL_AURA, EffectType.BUFF_AURA, EffectType.CAST_AURA, EffectType.DEATH_EFFECT, EffectType.HIT_SPARK]:
        radius_f = effect.size * (progress * 1.5) if effect.type != EffectType.DEATH_EFFECT else effect.size * (1-progress)
        radius = int(radius_f)
        if radius > 1:
             shape_surf = pygame.Surface((radius*2, radius*2), pygame.SRCALPHA)
             inner_alpha = alpha // (2 if effect.type==EffectType.HIT_SPARK else 3)
             pygame.draw.circle(shape_surf, (draw_color[0], draw_color[1], draw_color[2], inner_alpha), (radius, radius), radius)
             if effect.type != EffectType.DEATH_EFFECT:
                 pygame.draw.circle(shape_surf, (draw_color[0], draw_color[1], draw_color[2], alpha), (radius, radius), radius, 2)
             context.screen.blit(shape_surf, (ix - radius, iy - radius))

def draw_damage_floater(context: UIContext, floater: DamageFloater):
     # FIX: Check context/screen
    if not floater or not context or not context.screen: return
     # FIX: handle zero lifespan
    alpha = int(255 * (1.0 - (floater.timer / max(0.01, floater.lifespan))))
    if alpha <= 0: return

    color = context.map_color(floater.color_key)
    font_key = "small" if len(floater.text) < 5 else "default"
    # FIX: alpha text rendering
    text_surface = context.get_font(font_key).render(floater.text, True, color)
    text_surface.set_alpha(alpha)
    temp_surface = pygame.Surface(text_surface.get_size(), pygame.SRCALPHA)
    temp_surface.blit(text_surface, (0,0))
    rect = temp_surface.get_rect(center=(int(floater.x), int(floater.y)))
    context.screen.blit(temp_surface, rect)


def draw_map_phase(state: GameState, context: UIContext):
      # FIX: Check context/screen
      if not context or not context.screen: return
      draw_player_info(state, context)
      draw_text(context, "NAVIGATION MAP", (context.screen.get_width() // 2, context.map_y_start - 40), "large", GOLD, align='center') # FIX: move up
      current_node = state.game_map.get_node(state.current_node_id)
      for node_id, node in state.game_map.nodes.items(): # FIX iterate items
          if not node: continue
          start_pos = (int(node.x), int(node.y))
          for next_node_id in node.next_nodes:
              next_node = state.game_map.get_node(next_node_id)
              if next_node:
                   end_pos = (int(next_node.x), int(next_node.y))
                   color, width = (MAP_PATH, 2)
                   if node.node_id == state.current_node_id and current_node and next_node_id in current_node.next_nodes:
                        color, width = (YELLOW, 3)
                   elif node.visited and next_node.visited : color, width = (LIGHT_GRAY, 2)
                   pygame.draw.line(context.screen, color, start_pos, end_pos, width)
      for node_id, node in state.game_map.nodes.items():
           if not node: continue
           color = MAP_NODE_CURRENT if node_id == state.current_node_id else MAP_NODE_VISITED if node.visited else MAP_NODE_BG
           border_color, border_width = (GRAY, 1)
            # FIX: only show reachable nodes if current node is visited
           if current_node and node_id in current_node.next_nodes and current_node.visited: border_color, border_width = (YELLOW, 3)
           pygame.draw.circle(context.screen, color, (int(node.x), int(node.y)), node.radius)
           pygame.draw.circle(context.screen, border_color, (int(node.x), int(node.y)), node.radius, border_width)
           node_text_map = {'HARD': 'H', 'MEDIUM': 'M', 'EASY': 'E', 'BOSS': 'B!', 'SHOP': '$', 'EVENT': '?'}
           node_text = next((v for k, v in node_text_map.items() if k in node.node_type), '?')
           draw_text(context, node_text, (node.x, node.y), "small", WHITE, align='center')
      draw_hover_info(state, context)

def draw_main_menu(state: GameState, context: UIContext):
     if not context or not context.screen: return
     draw_text(context, "CLOCKWORK REQUIEM", (context.screen.get_width()//2, context.screen.get_height()//4), "menu", GOLD, align='center')
     draw_text(context, "A Rogue-lite Auto-Battler", (context.screen.get_width()//2, context.screen.get_height()//4 + 60), "large", LIGHT_GRAY, align='center')
     draw_button(context, context.start_menu_button_rect, "Start New Run", "large", context.hovered_button_rect == context.start_menu_button_rect)

def draw_game_over(state: GameState, context: UIContext):
     if not context or not context.screen: return
     draw_text(context, "GAME OVER", (context.screen.get_width()//2, context.screen.get_height()//2 - 100), "menu", RED, align='center')
     node = state.game_map.get_node(state.current_node_id)
     node_info = f"Node {state.current_node_id} ({node.node_type if node else '?'})"
     draw_text(context, f"Defeated at {node_info}", (context.screen.get_width()//2, context.screen.get_height()//2 + 10), "default", WHITE, align='center')
     draw_button(context, context.restart_button_rect, "Restart Run", "large", context.hovered_button_rect == context.restart_button_rect)

def draw_run_complete(state: GameState, context: UIContext):
     if not context or not context.screen: return
     draw_text(context, "RUN COMPLETE!", (context.screen.get_width()//2, context.screen.get_height()//2 - 100), "menu", GREEN, align='center')
     draw_text(context, "CONGRATULATIONS, BOSS DEFEATED", (context.screen.get_width()//2, context.screen.get_height()//2 - 20), "large", GOLD, align='center')
     draw_text(context, f"Final Health: {state.player.health}", (context.screen.get_width()//2, context.screen.get_height()//2 + 20), "default", WHITE, align='center')
     draw_button(context, context.restart_button_rect, "Start New Run", "large", context.hovered_button_rect == context.restart_button_rect)

def draw_event_choice(state: GameState, context: UIContext):
      if not context or not context.screen or not context.event_choice_rect: return
      pygame.draw.rect(context.screen, PANEL_BG, context.event_choice_rect, border_radius=10)
      pygame.draw.rect(context.screen, GRAY, context.event_choice_rect, 2, border_radius=10)
      draw_text(context, "EVENT: CHOOSE A REWARD", (context.event_choice_rect.centerx, context.event_choice_rect.top + 20), "large", YELLOW, align='center')
      for choice in state.event_choices:
           # FIX: check rect exists
          rect = choice.get('rect')
          is_hovered = context.hovered_button_rect and rect and context.hovered_button_rect == rect
          draw_button(context, rect, choice.get('text', '?'), "default", is_hovered)