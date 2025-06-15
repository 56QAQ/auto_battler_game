from __future__ import annotations

import pygame

from data.enums import DamageSource
from engine.game_state import GameState
from ui.constants import PANEL_BG, WHITE
from ui.drawing import draw_button, draw_text
from ui.ui_context import UIContext


_PAGE_LABELS = ["Damage Dealt", "Damage Taken", "Healing Done"]
_METRIC_KEYS = ["damage_dealt", "damage_taken", "healing_done"]


class StatsPanel:
    def __init__(self, state: GameState, context: UIContext):
        self.state = state
        self.context = context
        w = context.screen.get_width() - 300
        h = 220
        self.rect = pygame.Rect(
            context.screen.get_width() // 2 - w // 2,
            context.screen.get_height() - h - 10,
            w,
            h,
        )
        self.page = 0
        self.prev_rect = pygame.Rect(self.rect.x + 10, self.rect.y + 10, 30, 20)
        self.next_rect = pygame.Rect(self.rect.right - 40, self.rect.y + 10, 30, 20)

    def handle_event(self, ev: pygame.event.Event) -> bool:
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            if self.prev_rect.collidepoint(ev.pos):
                self.page = (self.page - 1) % len(_PAGE_LABELS)
                return True
            if self.next_rect.collidepoint(ev.pos):
                self.page = (self.page + 1) % len(_PAGE_LABELS)
                return True
            if not self.rect.collidepoint(ev.pos):
                self.context.stats_panel = None
                return True
        return False

    def draw(self) -> None:
        ctx = self.context
        surf = ctx.screen
        pygame.draw.rect(surf, PANEL_BG, self.rect)
        pygame.draw.rect(surf, WHITE, self.rect, 2)
        mouse = pygame.mouse.get_pos()
        draw_button(
            ctx,
            self.prev_rect,
            "<",
            "default",
            self.prev_rect.collidepoint(mouse),
        )
        draw_button(
            ctx,
            self.next_rect,
            ">",
            "default",
            self.next_rect.collidepoint(mouse),
        )
        title = _PAGE_LABELS[self.page]
        draw_text(
            ctx,
            title,
            (self.rect.centerx, self.rect.y + 8),
            "default",
            WHITE,
            align="center",
        )
        metric = _METRIC_KEYS[self.page]
        rows = self.state.combat_stats.sorted_units(metric)
        font = ctx.get_font("small")
        start_y = self.rect.y + 40
        for idx, (_, info) in enumerate(rows[:8]):
            name = info["name"]
            values = info[metric]
            total = sum(values.values())
            text = f"{name[:12]:<12} {int(total):>5}"
            for src in DamageSource:
                text += f" {int(values.get(src.name, 0)):>5}"
            surf.blit(
                font.render(text, True, WHITE),
                (self.rect.x + 20, start_y + idx * font.get_linesize()),
            )