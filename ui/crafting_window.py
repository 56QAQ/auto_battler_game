# ui/crafting_window.py
import pygame
from typing import Dict, List, Optional

from data.enums import ItemType
from engine.crafting import (
    craft,
    dismantle,
    can_craft,
    preview_rarity_distribution,
)
from data.constants import DISMANTLE_REFUND_RATIO
from ui.constants import (
    PANEL_BG,
    WHITE,
    RED,
    GREEN,
    BLUE,
    YELLOW,
    RARITY_COLORS,
    GRAY,
)
from ui.drawing import draw_button
from ui.ui_context import UIContext


class CraftingWindow:
    """
    极简实现：左侧材料滑杆，右侧按钮：
        [Craft Armament]  [Craft Disk]  [Craft Module]
        [Dismantle (选中物品)]
    """

    def __init__(self, state, context: UIContext):
        self.state = state
        self.context = context
        sw, sh = context.screen.get_size()
        self.rect = pygame.Rect(sw // 2 - 220, sh // 2 - 160, 440, 320)
        self.sliders = {"RED": 1, "GREEN": 1, "BLUE": 0}
        self.mode = "CRAFT"  # or "DISMANTLE"
        self.item_rects: List[pygame.Rect] = []
        # Pre-computed button rects for easier hit detection
        self.close_rect = pygame.Rect(self.rect.right - 26, self.rect.y + 4, 20, 20)
        self.tab_rects = {
            "CRAFT": pygame.Rect(self.rect.x + 20, self.rect.y, 100, 20),
            "DISMANTLE": pygame.Rect(self.rect.x + 140, self.rect.y, 100, 20),
        }
        self.slider_rects = {
            "RED": pygame.Rect(self.rect.x + 20, self.rect.y + 30, 100, 24),
            "GREEN": pygame.Rect(self.rect.x + 160, self.rect.y + 30, 100, 24),
            "BLUE": pygame.Rect(self.rect.x + 300, self.rect.y + 30, 100, 24),
        }
        self.craft_arm_rect = pygame.Rect(self.rect.x + 20, self.rect.y + 70, 160, 30)
        self.craft_disk_rect = pygame.Rect(self.rect.x + 200, self.rect.y + 70, 160, 30)
        self.craft_mod_rect = pygame.Rect(self.rect.x + 100, self.rect.y + 120, 240, 30)
    # ------------ input --------------- #
    def handle_click(self, ev: pygame.event.Event) -> bool:
        if ev.type != pygame.MOUSEBUTTONDOWN or ev.button != 1:
            return False
        if not self.rect.collidepoint(ev.pos):
            self.context.crafting_window = None
            return True
        # Very coarse button zones
        if self.close_rect.collidepoint(ev.pos):
            self.context.crafting_window = None
            return True
        for mode, rect in self.tab_rects.items():
            if rect.collidepoint(ev.pos):
                self.mode = mode
                return True
        if self.mode == "CRAFT":
            for color, rect in self.slider_rects.items():
                if rect.collidepoint(ev.pos):
                    self.sliders[color] = (self.sliders[color] + 1) % 4
                    return True
            mats = {k: v for k, v in self.sliders.items() if v}
            if self.craft_arm_rect.collidepoint(ev.pos) and can_craft(mats):
                self._do_craft(ItemType.ARMAMENT, mats)
                return True
            if self.craft_disk_rect.collidepoint(ev.pos) and can_craft(mats):
                self._do_craft(ItemType.DISK, mats)
                return True
            if self.craft_mod_rect.collidepoint(ev.pos) and can_craft(mats):
                self._do_craft(ItemType.MODULE, mats)
                return True
        else:  # dismantle mode
            for idx, rect in enumerate(self.item_rects):
                if rect.collidepoint(ev.pos):
                    self._do_dismantle(idx)
                    return True
        return False

    def _do_craft(self, item_type: ItemType, mats: Dict[str, int]):
        player = self.state.player
        if not player.can_pay_materials(mats):
            return
        player.pay_materials(mats)
        new_item = craft(item_type, mats)
        from engine.logic import add_item_to_inventory

        add_item_to_inventory(player, new_item)

    def _do_dismantle(self, index: int):
        player = self.state.player
        if not (0 <= index < len(player.item_inventory)):
            return
        item = player.item_inventory[index]
        if not item:
            return
        refund = dismantle(item)
        if refund:
            for k, v in refund.items():
                player.materials[k] = player.materials.get(k, 0) + v
        player.item_inventory[index] = None

    # ------------ draw ---------------- #
    def draw(self):
        ctx = self.context
        s = ctx.screen
        pygame.draw.rect(s, PANEL_BG, self.rect)
        pygame.draw.rect(s, WHITE, self.rect, 2)
        mouse_pos = pygame.mouse.get_pos()
        font = ctx.get_font("default")
        draw_button(
            ctx,
            self.close_rect,
            "X",
            "default",
            self.close_rect.collidepoint(mouse_pos),
        )

        # --- tab headers ---
        for mode, rect in self.tab_rects.items():
            color = YELLOW if self.mode == mode else BLUE
            is_hov = rect.collidepoint(mouse_pos)
            pygame.draw.rect(s, color if not is_hov else WHITE, rect)
            text_col = PANEL_BG if not is_hov else BLUE
            s.blit(
                font.render(mode.capitalize(), True, text_col), (rect.x + 6, rect.y + 2)
            )

        if self.mode == "CRAFT":
            # sliders
            for clr, rect in self.slider_rects.items():
                color = {"RED": RED, "GREEN": GREEN, "BLUE": BLUE}[clr]
                is_hov = rect.collidepoint(mouse_pos)
                pygame.draw.rect(s, color, rect)
                if is_hov:
                    pygame.draw.rect(s, WHITE, rect, 2)
                text = font.render(f"{clr}:{self.sliders[clr]}", True, WHITE)
                s.blit(text, (rect.x + 8, rect.y + 2))

            draw_button(
                ctx,
                self.craft_arm_rect,
                "Craft Armament",
                "default",
                self.craft_arm_rect.collidepoint(mouse_pos),
            )
            draw_button(
                ctx,
                self.craft_disk_rect,
                "Craft Disk",
                "default",
                self.craft_disk_rect.collidepoint(mouse_pos),
            )
            draw_button(
                ctx,
                self.craft_mod_rect,
                "Craft Module",
                "default",
                self.craft_mod_rect.collidepoint(mouse_pos),
            )

            total = sum(self.sliders.values())
            refund = int(total * DISMANTLE_REFUND_RATIO)
            info_text = f"Total {total}  Refund {refund}"
            info_y = self.craft_mod_rect.bottom + 10
            s.blit(font.render(info_text, True, WHITE), (self.rect.x + 20, info_y))

            # rarity preview bar
            dist = preview_rarity_distribution(total)
            bar_rect = pygame.Rect(
                self.rect.x + 20, self.rect.bottom - 30, self.rect.w - 40, 12
            )
            seg_w = bar_rect.width // len(dist) if dist else bar_rect.width
            x = bar_rect.x
            for rar in ["COMMON", "UNCOMMON", "RARE", "EPIC"]:
                ratio = dist.get(rar, 0.0)
                fill_w = int(seg_w * ratio)
                if fill_w > 0:
                    pygame.draw.rect(
                        s,
                        RARITY_COLORS.get(rar, WHITE),
                        (x, bar_rect.y, fill_w, bar_rect.height),
                    )
                pygame.draw.rect(s, WHITE, (x, bar_rect.y, seg_w, bar_rect.height), 1)
                x += seg_w
        else:
            # dismantle list
            self.item_rects = []
            start_y = self.rect.y + 30
            for idx, item in enumerate(self.state.player.item_inventory):
                rect = pygame.Rect(
                    self.rect.x + 20, start_y + idx * 36, self.rect.w - 40, 30
                )
                self.item_rects.append(rect)
                pygame.draw.rect(s, BLUE, rect, 1)
                if item:
                    color = RARITY_COLORS.get(getattr(item, "rarity", "COMMON"), WHITE)
                    s.blit(
                        font.render(item.name, True, color), (rect.x + 4, rect.y + 6)
                    )
                    refund = dismantle(item)
                    rtxt = " ".join(f"{v}{k[0]}" for k, v in refund.items()) or "0"
                    s.blit(
                        font.render(rtxt, True, YELLOW), (rect.right - 60, rect.y + 6)
                    )
                else:
                    s.blit(font.render("--", True, GRAY), (rect.x + 4, rect.y + 6))