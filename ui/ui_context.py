# ui/ui_context.py
import os
from typing import Any, Dict, Optional, Tuple

import pygame

# Type hinting forward
from engine.classes import Item, Unit
from states.enums import UnitLocation
from ui import constants as ui_c
from ui.layout_manager import LayoutManager
SelectedUnitInfo = Tuple[UnitLocation, Any, Unit]
# FIX: Correct Type hint for SelectedItemInfo when item is equipped
# idx is the UnitInfo tuple: (loc, idx, unit)
SelectedItemInfo = Tuple[
    UnitLocation, Any, Item
]  # Any = index for INVENTORY, UnitInfo for EQUIPPED


class UIContext:
    def __init__(
        self,
        screen: pygame.Surface,
        fonts: Dict[str, pygame.font.Font],
        layout: LayoutManager,
    ) -> None:
        self.screen = screen
        self.fonts = fonts
        self.layout = layout
        self.hovered_rect: Optional[pygame.Rect] = None
        self.hovered_button_rect: Optional[pygame.Rect] = None
        # Type hinting definitions - Input sets these, Drawing reads
        self.selected_unit_info: Optional[SelectedUnitInfo] = None
        self.selected_item_info: Optional[SelectedItemInfo] = None
        self.refresh_shop_button_rect = layout.refresh_shop_button_rect
        self.buy_xp_button_rect = layout.buy_xp_button_rect
        self.start_combat_button_rect = layout.start_combat_button_rect
        self.map_button_rect = layout.map_button_rect
        self.craft_button_rect = layout.craft_button_rect
        self.stats_toggle_button_rect = layout.stats_toggle_button_rect
        self.sell_area_rect = layout.sell_area_rect
        self.warehouse_button_rect = layout.warehouse_button_rect
        self.start_menu_button_rect = layout.start_menu_button_rect
        self.restart_button_rect = layout.restart_button_rect
        self.main_menu_button_rect = layout.main_menu_button_rect
        self.settings_button_rect = layout.settings_button_rect
        self.settings_back_button_rect = layout.settings_back_button_rect
        self.settings_abandon_button_rect = layout.settings_abandon_button_rect
        self.volume_down_rect = layout.volume_down_rect
        self.volume_up_rect = layout.volume_up_rect
        self.resolution_rect = layout.resolution_rect
        self.difficulty_button_rects = layout.difficulty_button_rects
        self.theme_button_rects: list[pygame.Rect] = []
        self.synergy_panel_rect = layout.synergy_panel_rect
        self.info_panel_rect = layout.info_panel_rect
        self.event_choice_rect = layout.event_choice_rect
        self.map_y_start = layout.map_y_start
        self.shop_x_start = layout.shop_x_start
        self.shop_y = layout.shop_y
        self.inventory_x_start = layout.inventory_x_start
        self.inventory_y = layout.inventory_y
        # FIX: Use correct WIDTH and HEIGHT constants
        self.combat_arena_rect = layout.combat_arena_rect
        # Image caches
        self.unit_images: Dict[str, pygame.Surface] = {}
        self.item_images: Dict[str, pygame.Surface] = {}
        self.icon_images: Dict[str, pygame.Surface] = {}
        self.artifact_images: Dict[str, pygame.Surface] = {}
        self.placeholder_image = self._load_image(ui_c.PLACEHOLDER_IMAGE)
        self.ui_images: Dict[str, pygame.Surface] = {}
        self.background_images: Dict[str, pygame.Surface] = {}
        self.drag_mgr = None
        self.details_window = None
        self.crafting_window = None
        self.stats_panel = None
        self.warehouse_panel = None
    def map_color(self, color_key: Optional[str]) -> Tuple[int, int, int]:
        # FIX: Handle None key
        if not color_key:
            return ui_c.WHITE
        return ui_c.KEY_TO_COLOR.get(color_key, ui_c.WHITE)

    def get_font(self, key: str = "default") -> pygame.font.Font:
        return self.fonts.get(key, self.fonts["default"])

    def get_slot_rect(
        self,
        location: UnitLocation,
        index: Any,
        base_rect: Optional[pygame.Rect] = None,
    ) -> Optional[pygame.Rect]:
        # From original get_slot_rect
        # FIX: Return None for invalid cases, add safety checks
        try:
            if location == UnitLocation.BENCH:
                return pygame.Rect(
                    ui_c.BENCH_X_START + index * (ui_c.SLOT_SIZE + ui_c.SLOT_MARGIN),
                    ui_c.BENCH_Y,
                    ui_c.SLOT_SIZE,
                    ui_c.SLOT_SIZE,
                )
            elif location == UnitLocation.BOARD:
                row, col = index
                return pygame.Rect(
                    ui_c.BOARD_X_START + col * (ui_c.SLOT_SIZE + ui_c.SLOT_MARGIN),
                    ui_c.BOARD_Y_START + row * (ui_c.SLOT_SIZE + ui_c.SLOT_MARGIN),
                    ui_c.SLOT_SIZE,
                    ui_c.SLOT_SIZE,
                )
            elif location == UnitLocation.PREVIEW:
                row, col = index
                return pygame.Rect(
                    ui_c.BOARD_X_START + col * (ui_c.SLOT_SIZE + ui_c.SLOT_MARGIN),
                    ui_c.PREVIEW_Y_START + row * (ui_c.SLOT_SIZE + ui_c.SLOT_MARGIN),
                    ui_c.SLOT_SIZE,
                    ui_c.SLOT_SIZE,
                )
            elif location == UnitLocation.SHOP:
                return pygame.Rect(
                    ui_c.SHOP_X_START + index * (ui_c.SLOT_SIZE + ui_c.SLOT_MARGIN),
                    ui_c.SHOP_Y,
                    ui_c.SLOT_SIZE,
                    ui_c.SLOT_SIZE,
                )
            elif location == UnitLocation.INVENTORY and self.warehouse_panel:
                return self.warehouse_panel.get_item_rect(index)
            elif location == UnitLocation.EQUIPPED and base_rect:
                # FIX: Item placement relative to unit rect
                item_x = (
                    base_rect.centerx
                    - (ui_c.MAX_ITEMS_EQUIPPED * (ui_c.ITEM_SLOT_SIZE + 2) / 2.0)
                    + index * (ui_c.ITEM_SLOT_SIZE + 2)
                )
                return pygame.Rect(
                    item_x,
                    base_rect.top - ui_c.ITEM_SLOT_SIZE - 5,
                    ui_c.ITEM_SLOT_SIZE,
                    ui_c.ITEM_SLOT_SIZE,
                )
            # Default or invalid
            return None  # pygame.Rect(0, 0, 0, 0)
        except TypeError:  # e.g., ndex is not a number or tuple
            return None
    def get_artifact_rect(self, index: int) -> pygame.Rect | None:
        if not self.info_panel_rect:
            return None
        line_height = self.get_font("default").get_linesize() + 4
        start_y = self.info_panel_rect.y + 10 + 7 * line_height + 10
        x = self.info_panel_rect.x + 10 + (index % 4) * (ui_c.RELIC_ICON_SIZE + 4)
        y = start_y + (index // 4) * (ui_c.RELIC_ICON_SIZE + 4)
        return pygame.Rect(x, y, ui_c.RELIC_ICON_SIZE, ui_c.RELIC_ICON_SIZE)

    def clear_hover(self):
        self.hovered_rect = None
        self.hovered_button_rect = None

    def clear_selection(self):
        self.selected_item_info = None
        self.selected_unit_info = None

    def _load_image(self, path: str, size: Optional[tuple] = None) -> pygame.Surface:
        """Load an image from disk or return placeholder if missing."""
        try:
            image = pygame.image.load(path).convert_alpha()
        except Exception:
            image = (
                self.placeholder_image.copy()
                if hasattr(self, "placeholder_image")
                else pygame.Surface((32, 32))
            )
            image.fill((255, 0, 255))
        if size:
            image = pygame.transform.smoothscale(image, size)
        return image

    def get_unit_image(self, name: str, size: tuple) -> pygame.Surface:
        if name not in self.unit_images:
            path = os.path.join(ui_c.UNIT_IMAGE_DIR, f"{name}.png")
            self.unit_images[name] = self._load_image(path, size)
        return self.unit_images[name]

    def get_item_image(self, name: str, size: tuple) -> pygame.Surface:
        if name not in self.item_images:
            path = os.path.join(ui_c.ITEM_IMAGE_DIR, f"{name}.png")
            self.item_images[name] = self._load_image(path, size)
        return self.item_images[name]
    def get_artifact_image(self, name: str, size: tuple) -> pygame.Surface:
        if name not in self.artifact_images:
            path = os.path.join(ui_c.ARTIFACT_IMAGE_DIR, f"{name}.png")
            self.artifact_images[name] = self._load_image(path, size)
        return self.artifact_images[name]
    def get_icon_image(self, name: str, size: tuple) -> pygame.Surface:
        if name not in self.icon_images:
            path = os.path.join(ui_c.ICON_IMAGE_DIR, f"{name}.png")
            self.icon_images[name] = self._load_image(path, size)
        return self.icon_images[name]

    def get_ui_image(self, key: str, size: tuple) -> pygame.Surface:
        """Return a scaled UI texture (button or panel)."""
        cache_key = f"{key}_{size[0]}x{size[1]}"
        if cache_key not in self.ui_images:
            path_map = {
                "button": ui_c.BUTTON_IMAGE,
                "panel": ui_c.PANEL_IMAGE,
            }
            path = path_map.get(key, ui_c.PLACEHOLDER_IMAGE)
            self.ui_images[cache_key] = self._load_image(path, size)
        return self.ui_images[cache_key]

    def get_background_image(self, key: str) -> pygame.Surface:
        """Return a background image scaled to the current screen size."""
        size = (self.screen.get_width(), self.screen.get_height())
        cache_key = f"{key}_{size[0]}x{size[1]}"
        if cache_key not in self.background_images:
            path_map = {
                "shop": ui_c.SHOP_BG_IMAGE,
                "map": ui_c.MAP_BG_IMAGE,
                "combat": ui_c.COMBAT_BG_IMAGE,
            }
            path = path_map.get(key, ui_c.PLACEHOLDER_IMAGE)
            self.background_images[cache_key] = self._load_image(path, size)
        return self.background_images[cache_key]

    def rebuild(
        self,
        screen: pygame.Surface,
        fonts: Dict[str, pygame.font.Font],
        layout: LayoutManager,
    ) -> None:
        UIContext.__init__(self, screen, fonts, layout)
    def set_drag_manager(self, mgr):
        self.drag_mgr = mgr
    def draw_drag_preview(self):
        if not (self.drag_mgr and self.drag_mgr.active and self.drag_mgr.preview):
            return
        mx, my = pygame.mouse.get_pos()
        ox, oy = self.drag_mgr.offset
        self.screen.blit(self.drag_mgr.preview, (mx - ox, my - oy))