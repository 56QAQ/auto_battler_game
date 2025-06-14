#ui/crafting_window.py
import pygame
from typing import Dict

from data.enums import ItemType
from engine.crafting import craft, dismantle, can_craft
from ui.constants import PANEL_BG, WHITE, RED, GREEN, BLUE, YELLOW
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
        if 20 < rely < 50:
            # sliders (toggle +1 modulo 4)
            if 20 <= relx < 120:
                self.sliders["RED"] = (self.sliders["RED"] + 1) % 4
            elif 160 <= relx < 260:
                self.sliders["GREEN"] = (self.sliders["GREEN"] + 1) % 4
            elif 300 <= relx < 400:
                self.sliders["BLUE"] = (self.sliders["BLUE"] + 1) % 4
            return True
        # craft buttons
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
        return False

    def _do_craft(self, item_type: ItemType, mats: Dict[str, int]):
        player = self.state.player
        if not player.can_pay_materials(mats):
            return
        player.pay_materials(mats)
        new_item = craft(item_type, mats)
        from engine.logic import add_item_to_inventory

        add_item_to_inventory(player, new_item)

    # ------------ draw ---------------- #
    def draw(self):
        ctx = self.context
        s = ctx.screen
        pygame.draw.rect(s, PANEL_BG, self.rect)
        pygame.draw.rect(s, WHITE, self.rect, 2)
        font = ctx.get_font("default")
        # sliders
        lx = self.rect.x + 20
        ly = self.rect.y + 20
        for i, (clr, col) in enumerate(
            [("RED", RED), ("GREEN", GREEN), ("BLUE", BLUE)]
        ):
            pygame.draw.rect(s, col, (lx + i * 140, ly, 100, 24))
            text = font.render(f"{clr}:{self.sliders[clr]}", True, WHITE)
            s.blit(text, (lx + i * 140 + 8, ly + 2))
        # buttons
        by = self.rect.y + 60
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
