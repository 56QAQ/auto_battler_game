# ui/ui_context.py
import pygame
from typing import Dict, Any, Optional, Tuple
from ui import constants as ui_c
from states.enums import UnitLocation
# Type hinting forward
from engine.classes import Unit, Item
SelectedUnitInfo = Tuple[UnitLocation, Any, Unit]
# FIX: Correct Type hint for SelectedItemInfo when item is equipped
# idx is the UnitInfo tuple: (loc, idx, unit)
SelectedItemInfo = Tuple[UnitLocation, Any, Item] # Any = index for INVENTORY, UnitInfo for EQUIPPED


class UIContext:
    def __init__(self, screen, fonts: Dict[str, pygame.font.Font]):
        self.screen = screen
        self.fonts = fonts
        self.hovered_rect: Optional[pygame.Rect] = None
        self.hovered_button_rect: Optional[pygame.Rect] = None
        # Type hinting definitions - Input sets these, Drawing reads
        self.selected_unit_info: Optional[SelectedUnitInfo] = None
        self.selected_item_info: Optional[SelectedItemInfo] = None

        # Define all static button rects
        self.refresh_shop_button_rect = pygame.Rect(ui_c.SHOP_X_START, ui_c.SHOP_Y + ui_c.SLOT_SIZE + 10, 100, ui_c.BUTTON_HEIGHT)
        self.buy_xp_button_rect = pygame.Rect(ui_c.SHOP_X_START + 110, ui_c.SHOP_Y + ui_c.SLOT_SIZE + 10, 100, ui_c.BUTTON_HEIGHT)
        self.start_combat_button_rect = pygame.Rect(ui_c.SCREEN_WIDTH - 160, ui_c.SCREEN_HEIGHT - 60, 150, ui_c.BUTTON_HEIGHT)
        self.map_button_rect = pygame.Rect(ui_c.SCREEN_WIDTH - 160, 20, 150, ui_c.BUTTON_HEIGHT)
        self.sell_area_rect = pygame.Rect(ui_c.SHOP_X_START + ui_c.SHOP_SLOTS * (ui_c.SLOT_SIZE + ui_c.SLOT_MARGIN) + 20, ui_c.SHOP_Y, 80, ui_c.SLOT_SIZE)
        self.start_menu_button_rect = pygame.Rect(ui_c.SCREEN_WIDTH//2 - 100, ui_c.SCREEN_HEIGHT//2, 200, 60)
        self.restart_button_rect = pygame.Rect(ui_c.SCREEN_WIDTH//2 - 100, ui_c.SCREEN_HEIGHT - 100, 200, 60)
        self.synergy_panel_rect = pygame.Rect(ui_c.SYNERGY_PANEL_X, ui_c.SYNERGY_PANEL_Y, 200, ui_c.SCREEN_HEIGHT - ui_c.SYNERGY_PANEL_Y - 10)
        self.info_panel_rect = pygame.Rect(ui_c.INFO_PANEL_X, ui_c.INFO_PANEL_Y, 200, ui_c.SYNERGY_PANEL_Y - ui_c.INFO_PANEL_Y -10 ) # FIX: End before synergy panel
        self.event_choice_rect = ui_c.EVENT_CHOICE_RECT
        self.map_y_start = ui_c.MAP_Y_START
        self.shop_x_start = ui_c.SHOP_X_START
        self.shop_y = ui_c.SHOP_Y
        self.inventory_x_start = ui_c.INVENTORY_X_START
        self.inventory_y = ui_c.INVENTORY_Y
        # FIX: Use correct WIDTH and HEIGHT constants
        self.combat_arena_rect = pygame.Rect(ui_c.COMBAT_ARENA_X, ui_c.COMBAT_ARENA_Y, ui_c.COMBAT_ARENA_WIDTH, ui_c.COMBAT_ARENA_HEIGHT)

    def map_color(self, color_key: Optional[str]) -> Tuple[int, int, int]:
         # FIX: Handle None key
         if not color_key: return ui_c.WHITE
         return ui_c.KEY_TO_COLOR.get(color_key, ui_c.WHITE)

    def get_font(self, key: str = "default") -> pygame.font.Font:
         return self.fonts.get(key, self.fonts["default"])

    def get_slot_rect(self, location: UnitLocation, index: Any, base_rect: Optional[pygame.Rect] = None) -> Optional[pygame.Rect]:
        # From original get_slot_rect
        # FIX: Return None for invalid cases, add safety checks
        try:
            if location == UnitLocation.BENCH:
                return pygame.Rect(ui_c.BENCH_X_START + index * (ui_c.SLOT_SIZE + ui_c.SLOT_MARGIN), ui_c.BENCH_Y, ui_c.SLOT_SIZE, ui_c.SLOT_SIZE)
            elif location == UnitLocation.BOARD:
                 row, col = index
                 return pygame.Rect(ui_c.BOARD_X_START + col * (ui_c.SLOT_SIZE + ui_c.SLOT_MARGIN), ui_c.BOARD_Y_START + row * (ui_c.SLOT_SIZE + ui_c.SLOT_MARGIN), ui_c.SLOT_SIZE, ui_c.SLOT_SIZE)
            elif location == UnitLocation.SHOP:
                 return pygame.Rect(ui_c.SHOP_X_START + index * (ui_c.SLOT_SIZE + ui_c.SLOT_MARGIN), ui_c.SHOP_Y, ui_c.SLOT_SIZE, ui_c.SLOT_SIZE)
            elif location == UnitLocation.INVENTORY:
                 return pygame.Rect(ui_c.INVENTORY_X_START + index * (ui_c.ITEM_SLOT_SIZE + ui_c.SLOT_MARGIN), ui_c.INVENTORY_Y, ui_c.ITEM_SLOT_SIZE, ui_c.ITEM_SLOT_SIZE)
            elif location == UnitLocation.EQUIPPED and base_rect:
                  # FIX: Item placement relative to unit rect
                 item_x = base_rect.centerx - (ui_c.MAX_ITEMS_EQUIPPED * (ui_c.ITEM_SLOT_SIZE+2) / 2.0) + index * (ui_c.ITEM_SLOT_SIZE + 2)
                 return pygame.Rect(item_x , base_rect.top - ui_c.ITEM_SLOT_SIZE - 5, ui_c.ITEM_SLOT_SIZE, ui_c.ITEM_SLOT_SIZE)
            # Default or invalid
            return None # pygame.Rect(0, 0, 0, 0)
        except TypeError: # e.g., index is not a number or tuple
             return None


    def clear_hover(self):
         self.hovered_rect = None
         self.hovered_button_rect = None

    def clear_selection(self):
        self.selected_item_info = None
        self.selected_unit_info = None