#ui/warehouse_panel.py

import math

import pygame

from engine.game_state import GameState
from ui.constants import (
    ITEM_SLOT_SIZE,
    PANEL_BG,
    SLOT_MARGIN,
    WAREHOUSE_COLS,
    WAREHOUSE_ROWS,
    WAREHOUSE_Y,
    WHITE,
)
from ui.drawing import draw_button, draw_item_prep
from ui.ui_context import UIContext


class WarehousePanel:
    def __init__(self, state: GameState, context: UIContext) -> None:
        self.state = state
        self.context = context
        w = WAREHOUSE_COLS * (ITEM_SLOT_SIZE + SLOT_MARGIN) + SLOT_MARGIN
        h = WAREHOUSE_ROWS * (ITEM_SLOT_SIZE + SLOT_MARGIN) + 50
        button_bottom = (
            context.warehouse_button_rect.bottom
            if context.warehouse_button_rect
            else WAREHOUSE_Y - 10
        )
        self.rect = pygame.Rect(context.shop_x_start, button_bottom + 10, w, h)
        self.page = 0
        self.prev_rect = pygame.Rect(self.rect.x + 10, self.rect.y + 10, 30, 20)
        self.next_rect = pygame.Rect(self.rect.right - 40, self.rect.y + 10, 30, 20)

    def _page_size(self) -> int:
        return WAREHOUSE_COLS * WAREHOUSE_ROWS

    def _total_pages(self) -> int:
        return max(
            1, math.ceil(len(self.state.player.item_inventory) / self._page_size())
        )

    def handle_event(self, ev: pygame.event.Event) -> bool:
        # if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
        #     start = self.page * self._page_size()
        #     end   = start + self._page_size()
        #     items = self.state.player.item_inventory[start:end]
        #     for local_idx, _ in enumerate(items):
        #         if self.get_item_rect(local_idx).collidepoint(ev.pos):
        #             global_idx = start + local_idx
        #             itm = self.state.player.item_inventory[global_idx]
        #             self.context.selected_item_info = (
        #                 UnitLocation.INVENTORY, global_idx, itm
        #             )
        #             return True
        #     if self.prev_rect.collidepoint(ev.pos):
        #         self.page = (self.page - 1) % self._total_pages()
        #         return True
        #     if self.next_rect.collidepoint(ev.pos):
        #         self.page = (self.page + 1) % self._total_pages()
        #         return True
        #     if not self.rect.collidepoint(ev.pos):
        #         return False
        return False

    def get_item_rect(self, index: int) -> pygame.Rect:
        row = index // WAREHOUSE_COLS
        col = index % WAREHOUSE_COLS
        x = self.rect.x + SLOT_MARGIN + col * (ITEM_SLOT_SIZE + SLOT_MARGIN)
        y = self.rect.y + 40 + row * (ITEM_SLOT_SIZE + SLOT_MARGIN)
        return pygame.Rect(x, y, ITEM_SLOT_SIZE, ITEM_SLOT_SIZE)

    def draw(self) -> None:
        ctx = self.context
        surf = ctx.screen
        pygame.draw.rect(surf, PANEL_BG, self.rect)
        pygame.draw.rect(surf, WHITE, self.rect, 2)
        mouse = pygame.mouse.get_pos()
        draw_button(
            ctx, self.prev_rect, "<", "default", self.prev_rect.collidepoint(mouse)
        )
        draw_button(
            ctx, self.next_rect, ">", "default", self.next_rect.collidepoint(mouse)
        )

        start = self.page * self._page_size()
        end = start + self._page_size()
        items = self.state.player.item_inventory[start:end]
        for idx, item in enumerate(items):
            rect = self.get_item_rect(idx)
            is_selected = (
                ctx.selected_item_info is not None
                and ctx.selected_item_info[0].name == "INVENTORY"
                and ctx.selected_item_info[1] == start + idx
            )
            draw_item_prep(ctx, rect, item, is_selected)