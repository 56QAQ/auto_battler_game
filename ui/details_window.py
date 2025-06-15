# ui/details_window.py
from __future__ import annotations

from typing import Dict, Tuple
import math
import pygame
from ui.drawing import draw_button, draw_text
# Map of stat keys to human readable labels
STAT_LABELS: Dict[str, str] = {
    "hp": "HP",
    "ad": "Phys ATK",
    "ap": "Magic ATK",
    "as": "Atk SPD",
    "armor": "Phys DEF",
    "mr": "Magic DEF",
    "range": "Range",
    "percentage_damage_bonus": "Dmg Bonus %",
    "flat_damage_bonus": "Flat Bonus",
    "percentage_damage_reduction": "Dmg Reduc %",
    "flat_damage_reduction": "Flat Reduc",
    "outgoing_healing_bonus": "Heal Out %",
    "incoming_healing_bonus": "Heal In %",
    "physical_lifesteal": "Life Steal",
    "spell_lifesteal": "Spell LS",
    "omnivamp": "Omnivamp",
    "flat_physical_penetration": "Flat Pen (P)",
    "flat_magic_penetration": "Flat Pen (M)",
    "percentage_physical_penetration": "Pen % (P)",
    "percentage_magic_penetration": "Pen % (M)",
    "critical_chance": "Crit %",
    "critical_damage": "Crit Dmg %",
    "dodge_chance": "Dodge %",
    "accuracy": "Accuracy",
}

HEADER_H = 28

_PAGE_LABELS = ["Stats", "Status Effects"]
class DetailsWindow:

    def __init__(self, unit, context, width=300, height=700):
        self.unit = unit
        screen_w, _ = context.screen.get_size()
        self.rect = pygame.Rect(screen_w - width - 10, 10, width, height)
        self.dragging = False
        self._drag_off = (0, 0)
        self.page = 0
        self.prev_rect = pygame.Rect(0, 0, 30, 20)
        self.next_rect = pygame.Rect(0, 0, 30, 20)
        self._update_nav_rects()

    def _update_nav_rects(self) -> None:
        self.prev_rect.update(self.rect.x + 10, self.rect.y + HEADER_H + 6, 30, 20)
        self.next_rect.update(self.rect.right - 40, self.rect.y + HEADER_H + 6, 30, 20)

    def _total_pages(self, context) -> int:
        fnt = context.get_font("small")
        body_h = self.rect.h - HEADER_H - 40
        max_lines = max(1, body_h // fnt.get_linesize())
        status_count = sum(len(bucket) for bucket in self.unit.statuses.values())
        pages = math.ceil(status_count / max_lines) if status_count else 1
        return 1 + pages
    # ------------- event ------------- #
    def handle_event(self, event, context):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            context.details_window = None
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.prev_rect.collidepoint(event.pos):
                self.page = (self.page - 1) % self._total_pages(context)
                return
            if self.next_rect.collidepoint(event.pos):
                self.page = (self.page + 1) % self._total_pages(context)
                return
            if self.rect.collidepoint(event.pos):
                # header drag or ❌
                hx = self.rect.x + self.rect.w - HEADER_H
                if pygame.Rect(hx, self.rect.y, HEADER_H, HEADER_H).collidepoint(
                    event.pos
                ):
                    context.details_window = None
                elif pygame.Rect(
                    self.rect.x, self.rect.y, self.rect.w, HEADER_H
                ).collidepoint(event.pos):
                    self.dragging = True
                    self._drag_off = (
                        event.pos[0] - self.rect.x,
                        event.pos[1] - self.rect.y,
                    )
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.dragging = False
        elif event.type == pygame.MOUSEMOTION and self.dragging:
            self.rect.x = event.pos[0] - self._drag_off[0]
            self.rect.y = event.pos[1] - self._drag_off[1]
            self._update_nav_rects()
    # ------------- draw ------------- #
    def draw(self, context):
        srf = context.screen
        self._update_nav_rects()
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

        mouse = pygame.mouse.get_pos()
        draw_button(
            context,
            self.prev_rect,
            "<",
            "small",
            self.prev_rect.collidepoint(mouse),
        )
        draw_button(
            context,
            self.next_rect,
            ">",
            "small",
            self.next_rect.collidepoint(mouse),
        )
        draw_text(
            context,
            _PAGE_LABELS[self.page],
            (self.rect.centerx, self.prev_rect.y + 2),
            "small",
            (240, 240, 235),
            align="center",
        )

        body_x = self.rect.x + 10
        y = self.rect.y + HEADER_H + 40
        fnt = context.get_font("small")

        def _line(label, val):
            nonlocal y
            txt = f"{label:<14}{val:>7}"
            context.screen.blit(fnt.render(txt, True, (240, 240, 235)), (body_x, y))
            y += fnt.get_linesize()

        if self.page == 0:
            cs = self.unit.current_stats
            for key in STAT_LABELS:
                if key not in cs:
                    continue
                label = STAT_LABELS[key]
                val = cs[key]
                if key == "hp":
                    val_str = f"{int(self.unit.current_hp)}/{int(val)}"
                else:
                    val_str = f"{int(val)}"
                _line(label, val_str)

            # simple bio
            y += 6
            bio_lines = [
                "Traits: " + ", ".join(self.unit.traits),
                f"Level {self.unit.level} • Rarity {self.unit.rarity}",
            ]
            for ln in bio_lines:
                context.screen.blit(fnt.render(ln, True, (200, 200, 200)), (body_x, y))
                y += fnt.get_linesize()

            y += fnt.get_linesize()
            context.screen.blit(
                fnt.render("Trigger:", True, (240, 240, 235)), (body_x, y)
            )
            y += fnt.get_linesize()
            trig = getattr(self.unit, "trigger", None)
            if trig:
                for k, v in trig.items():
                    context.screen.blit(
                        fnt.render(f"{k}: {v}", True, (200, 200, 200)), (body_x, y)
                    )
                    y += fnt.get_linesize()
            else:
                context.screen.blit(
                    fnt.render("None", True, (200, 200, 200)), (body_x, y)
                )
                y += fnt.get_linesize()
            y += fnt.get_linesize()

            context.screen.blit(
                fnt.render("Passive:", True, (240, 240, 235)), (body_x, y)
            )
            y += fnt.get_linesize()
            passive = getattr(self.unit, "passive", None)
            ability_name = passive.get("ability", {}).get("name") if passive else None
            if ability_name:
                context.screen.blit(
                    fnt.render(ability_name, True, (200, 200, 200)), (body_x, y)
                )
                y += fnt.get_linesize()
            else:
                context.screen.blit(
                    fnt.render("None", True, (200, 200, 200)), (body_x, y)
                )
                y += fnt.get_linesize()
            # Description
            desc = self.unit.definition.get("description", "No description.")
            y += fnt.get_linesize()
            for ln in str(desc).split("\n"):
                context.screen.blit(fnt.render(ln, True, (180, 180, 180)), (body_x, y))
                y += fnt.get_linesize()
        else:
            statuses = [st for bucket in self.unit.statuses.values() for st in bucket]
            body_h = self.rect.h - HEADER_H - 40
            max_lines = max(1, body_h // fnt.get_linesize())
            start = (self.page - 1) * max_lines
            end = start + max_lines
            page_statuses = statuses[start:end]
            if not page_statuses:
                context.screen.blit(
                    fnt.render("None", True, (200, 200, 200)), (body_x, y)
                )
            for st in page_statuses:
                dur = "∞" if st.remaining is None else f"{st.remaining:.0f}s"
                line = f"{st.name} x{st.stacks} {dur}"
                context.screen.blit(
                    fnt.render(line, True, (200, 200, 200)), (body_x, y)
                )
                y += fnt.get_linesize()