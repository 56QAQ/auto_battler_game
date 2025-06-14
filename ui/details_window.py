#ui/details_window.py
from __future__ import annotations
import pygame
from typing import Tuple

HEADER_H = 28


class DetailsWindow:
    """点击单位后弹出的详情面板（可拖动 / Esc 关闭）。"""

    def __init__(self, unit, pos: Tuple[int, int], width=260, height=340):
        self.unit = unit
        self.rect = pygame.Rect(pos[0], pos[1], width, height)
        self.dragging = False
        self._drag_off = (0, 0)

    # ------------- event ------------- #
    def handle_event(self, event, context):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            context.details_window = None
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                # header drag or ❌
                hx = self.rect.x + self.rect.w - HEADER_H
                if pygame.Rect(hx, self.rect.y, HEADER_H, HEADER_H).collidepoint(
                    event.pos
                ):
                    context.details_window = None
                elif pygame.Rect(self.rect.x, self.rect.y, self.rect.w, HEADER_H).collidepoint(
                    event.pos
                ):
                    self.dragging = True
                    self._drag_off = (event.pos[0] - self.rect.x, event.pos[1] - self.rect.y)
            else:
                # click outside
                context.details_window = None
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.dragging = False
        elif event.type == pygame.MOUSEMOTION and self.dragging:
            self.rect.x = event.pos[0] - self._drag_off[0]
            self.rect.y = event.pos[1] - self._drag_off[1]

    # ------------- draw ------------- #
    def draw(self, context):
        srf = context.screen
        pygame.draw.rect(srf, (45, 48, 60), self.rect)
        pygame.draw.rect(srf, (200, 200, 210), self.rect, 2)

        # header
        hdr = pygame.Rect(self.rect.x, self.rect.y, self.rect.w, HEADER_H)
        pygame.draw.rect(srf, (70, 75, 90), hdr)
        context.screen.blit(
            context.get_font("default").render(self.unit.name, True, (240, 240, 235)),
            (hdr.x + 6, hdr.y + 5),
        )
        # close button
        pygame.draw.rect(
            srf,
            (140, 60, 60),
            (hdr.right - HEADER_H, hdr.y, HEADER_H, HEADER_H),
        )
        context.screen.blit(
            context.get_font("default").render("X", True, (240, 240, 235)),
            (hdr.right - HEADER_H // 2 - 6, hdr.y + 4),
        )

        # --- body (live stats) ---
        body_x = self.rect.x + 10
        y = self.rect.y + HEADER_H + 10
        fnt = context.get_font("small")

        def _line(label, val):
            nonlocal y
            txt = f"{label:<14}{val:>7}"
            context.screen.blit(fnt.render(txt, True, (240, 240, 235)), (body_x, y))
            y += fnt.get_linesize()

        cs = self.unit.current_stats
        _line("HP", f"{int(self.unit.current_hp)}/{int(cs['hp'])}")
        _line("Phys ATK", int(cs["ad"]))
        _line("Phys DEF", int(cs["armor"]))
        _line("Magic ATK", int(cs["ap"]))
        _line("Magic DEF", int(cs["mr"]))
        _line("Dmg Bonus %", int(cs.get("percentage_damage_bonus", 100)))
        _line("Dmg Reduc %", int(cs.get("percentage_damage_reduction", 100)))

        # simple bio
        y += 6
        bio_lines = [
            "Traits: " + ", ".join(self.unit.traits),
            f"Level {self.unit.level} • Rarity {self.unit.rarity}",
        ]
        for ln in bio_lines:
            context.screen.blit(fnt.render(ln, True, (200, 200, 200)), (body_x, y))
            y += fnt.get_linesize()
