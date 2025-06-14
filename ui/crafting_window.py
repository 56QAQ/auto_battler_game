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

    # ------------ input --------------- #
    def handle_click(self, ev: pygame.event.Event) -> bool:
        if ev.type != pygame.MOUSEBUTTONDOWN or ev.button != 1:
            return False
        if not self.rect.collidepoint(ev.pos):
            self.context.crafting_window = None
            return True
        # Very coarse button zones
        bx, by = ev.pos
        mx, my = self.rect.topleft
        relx, rely = bx - mx, by - my
        # tab switch
        if 0 <= rely < 20:
            if 20 <= relx < 120:
                self.mode = "CRAFT"
                return True
            if 140 <= relx < 240:
                self.mode = "DISMANTLE"
                return True
        if self.mode == "CRAFT" and 20 < rely < 50:
            # sliders (toggle +1 modulo 4)
            if 20 <= relx < 120:
                self.sliders["RED"] = (self.sliders["RED"] + 1) % 4
            elif 160 <= relx < 260:
                self.sliders["GREEN"] = (self.sliders["GREEN"] + 1) % 4
            elif 300 <= relx < 400:
                self.sliders["BLUE"] = (self.sliders["BLUE"] + 1) % 4
            return True
        if self.mode == "CRAFT":
            mats = {k: v for k, v in self.sliders.items() if v}
            if 40 < rely < 80 and can_craft(mats):
                if 20 <= relx < 200:
                    self._do_craft(ItemType.ARMAMENT, mats)
                elif 220 <= relx < 420:
                    self._do_craft(ItemType.DISK, mats)
                return True
            if 100 < rely < 140 and 100 <= relx < 340:
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
        font = ctx.get_font("default")

        # --- tab headers ---
        for i, (label, mode) in enumerate(
            [("Craft", "CRAFT"), ("Dismantle", "DISMANTLE")]
        ):
            rect = pygame.Rect(self.rect.x + 20 + i * 120, self.rect.y, 100, 20)
            color = YELLOW if self.mode == mode else BLUE
            pygame.draw.rect(s, color, rect)
            s.blit(font.render(label, True, PANEL_BG), (rect.x + 6, rect.y + 2))

        if self.mode == "CRAFT":
            # sliders
            lx = self.rect.x + 20
            ly = self.rect.y + 30
            for i, (clr, col) in enumerate(
                [("RED", RED), ("GREEN", GREEN), ("BLUE", BLUE)]
            ):
                pygame.draw.rect(s, col, (lx + i * 140, ly, 100, 24))
                text = font.render(f"{clr}:{self.sliders[clr]}", True, WHITE)
                s.blit(text, (lx + i * 140 + 8, ly + 2))

            # craft buttons
            by = self.rect.y + 70
            for idx, (txt, w) in enumerate(
                [("Craft Armament", 160), ("Craft Disk", 160)]
            ):
                bx = self.rect.x + 20 + idx * 180
                pygame.draw.rect(s, YELLOW, (bx, by, w, 30))
                s.blit(font.render(txt, True, PANEL_BG), (bx + 8, by + 4))
            pygame.draw.rect(s, YELLOW, (self.rect.x + 100, by + 50, 240, 30))
            s.blit(
                font.render("Craft Module", True, PANEL_BG),
                (self.rect.x + 108, by + 54),
            )

            total = sum(self.sliders.values())
            refund = int(total * DISMANTLE_REFUND_RATIO)
            info_text = f"Total {total}  Refund {refund}"
            s.blit(font.render(info_text, True, WHITE), (self.rect.x + 20, by + 90))

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