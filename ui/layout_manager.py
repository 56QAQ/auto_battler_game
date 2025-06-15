#ui/layout_manager.py

from __future__ import annotations

from dataclasses import dataclass

import pygame as pg

from ui import constants as ui_c


@dataclass
class LayoutManager:
    """Compute and store UI layout rectangles for a given resolution."""

    width: int
    height: int

    def __post_init__(self) -> None:
        self.update(self.width, self.height)

    def update(self, width: int, height: int) -> None:
        """Recalculate layout constants and rectangles."""
        self.width = width
        self.height = height
        ui_c.update_resolution(width, height)
        offset = ui_c.SLOT_SIZE + 20
        self.refresh_shop_button_rect = pg.Rect(
            ui_c.SHOP_X_START,
            ui_c.SHOP_Y + offset,
            100,
            ui_c.BUTTON_HEIGHT,
        )
        self.buy_xp_button_rect = pg.Rect(
            ui_c.SHOP_X_START + 110,
            ui_c.SHOP_Y + offset,
            100,
            ui_c.BUTTON_HEIGHT,
        )
        self.start_combat_button_rect = pg.Rect(
            ui_c.SCREEN_WIDTH - 160,
            ui_c.SCREEN_HEIGHT - 60,
            150,
            ui_c.BUTTON_HEIGHT,
        )
        self.map_button_rect = pg.Rect(
            ui_c.SCREEN_WIDTH - 360,
            220,
            150,
            ui_c.BUTTON_HEIGHT,
        )
        self.craft_button_rect = pg.Rect(
            ui_c.SCREEN_WIDTH - 160,
            20,
            150,
            ui_c.BUTTON_HEIGHT,
        )
        self.warehouse_button_rect = pg.Rect(
            ui_c.SHOP_X_START,
            ui_c.WAREHOUSE_Y - ui_c.BUTTON_HEIGHT - 10,
            150,
            ui_c.BUTTON_HEIGHT,
        )
        self.stats_toggle_button_rect = pg.Rect(
            ui_c.SCREEN_WIDTH - 60,
            ui_c.SCREEN_HEIGHT // 2 - 20,
            50,
            ui_c.BUTTON_HEIGHT,
        )
        self.sell_area_rect = pg.Rect(
            ui_c.SHOP_X_START
            + ui_c.SHOP_SLOTS * (ui_c.SLOT_SIZE + ui_c.SLOT_MARGIN)
            + 20,
            ui_c.SHOP_Y,
            80,
            ui_c.SLOT_SIZE,
        )
        self.start_menu_button_rect = pg.Rect(
            ui_c.SCREEN_WIDTH // 2 - 100,
            ui_c.SCREEN_HEIGHT // 2,
            200,
            60,
        )
        self.restart_button_rect = pg.Rect(
            ui_c.SCREEN_WIDTH // 2 - 100,
            ui_c.SCREEN_HEIGHT - 100,
            200,
            60,
        )
        self.main_menu_button_rect = pg.Rect(
            ui_c.SCREEN_WIDTH // 2 - 100,
            ui_c.SCREEN_HEIGHT - 170,
            200,
            60,
        )
        self.settings_button_rect = pg.Rect(
            ui_c.SCREEN_WIDTH - 160,
            80,
            150,
            ui_c.BUTTON_HEIGHT,
        )
        self.settings_back_button_rect = pg.Rect(
            ui_c.SCREEN_WIDTH // 2 - 100,
            ui_c.SCREEN_HEIGHT - 80,
            200,
            60,
        )
        self.settings_abandon_button_rect = pg.Rect(
            ui_c.SCREEN_WIDTH // 2 - 100,
            ui_c.SCREEN_HEIGHT - 150,
            200,
            60,
        )
        self.volume_down_rect = pg.Rect(
            ui_c.SCREEN_WIDTH // 2 - 130,
            ui_c.SCREEN_HEIGHT // 2 - 20,
            40,
            ui_c.BUTTON_HEIGHT,
        )
        self.volume_up_rect = pg.Rect(
            ui_c.SCREEN_WIDTH // 2 + 90,
            ui_c.SCREEN_HEIGHT // 2 - 20,
            40,
            ui_c.BUTTON_HEIGHT,
        )
        self.resolution_rect = pg.Rect(
            ui_c.SCREEN_WIDTH // 2 - 100,
            ui_c.SCREEN_HEIGHT // 2 + 40,
            200,
            ui_c.BUTTON_HEIGHT,
        )
        self.difficulty_button_rects = [
            pg.Rect(
                ui_c.SCREEN_WIDTH // 2 - 100,
                ui_c.SCREEN_HEIGHT // 2 - 70 + i * 70,
                200,
                60,
            )
            for i in range(3)
        ]
        self.synergy_panel_rect = pg.Rect(
            ui_c.SYNERGY_PANEL_X,
            ui_c.SYNERGY_PANEL_Y,
            200,
            ui_c.SCREEN_HEIGHT - ui_c.SYNERGY_PANEL_Y - 10,
        )
        self.info_panel_rect = pg.Rect(
            ui_c.INFO_PANEL_X,
            ui_c.INFO_PANEL_Y,
            200,
            ui_c.SYNERGY_PANEL_Y - ui_c.INFO_PANEL_Y - 10,
        )
        self.event_choice_rect = ui_c.EVENT_CHOICE_RECT
        self.map_y_start = ui_c.MAP_Y_START
        self.shop_x_start = ui_c.SHOP_X_START
        self.shop_y = ui_c.SHOP_Y
        self.inventory_x_start = self.shop_x_start
        self.inventory_y = ui_c.WAREHOUSE_Y
        self.combat_arena_rect = pg.Rect(
            ui_c.COMBAT_ARENA_X,
            ui_c.COMBAT_ARENA_Y,
            ui_c.COMBAT_ARENA_WIDTH,
            ui_c.COMBAT_ARENA_HEIGHT,
        )