# ui/details_window.py
from __future__ import annotations

from typing import Dict, Tuple

import pygame

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


class DetailsWindow:

    def __init__(self, unit, context, width=300, height=700):
        self.unit = unit
        screen_w, _ = context.screen.get_size()
        self.rect = pygame.Rect(screen_w - width - 10, 10, width, height)
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

        # Trigger information
        y += fnt.get_linesize()
        context.screen.blit(fnt.render("Trigger:", True, (240, 240, 235)), (body_x, y))
        y += fnt.get_linesize()
        trig = getattr(self.unit, "trigger", None)
        if trig:
            for k, v in trig.items():
                context.screen.blit(
                    fnt.render(f"{k}: {v}", True, (200, 200, 200)), (body_x, y)
                )
                y += fnt.get_linesize()
        else:
            context.screen.blit(fnt.render("None", True, (200, 200, 200)), (body_x, y))
            y += fnt.get_linesize()
        y += fnt.get_linesize()
        context.screen.blit(fnt.render("Passive:", True, (240, 240, 235)), (body_x, y))
        y += fnt.get_linesize()
        passive = getattr(self.unit, "passive", None)
        ability_name = passive.get("ability", {}).get("name") if passive else None
        if ability_name:
            context.screen.blit(
                fnt.render(ability_name, True, (200, 200, 200)), (body_x, y)
            )
            y += fnt.get_linesize()
        else:
            context.screen.blit(fnt.render("None", True, (200, 200, 200)), (body_x, y))
            y += fnt.get_linesize()

        # Description
        desc = self.unit.definition.get("description", "No description.")
        y += fnt.get_linesize()
        for ln in str(desc).split("\n"):
            context.screen.blit(fnt.render(ln, True, (180, 180, 180)), (body_x, y))
            y += fnt.get_linesize()