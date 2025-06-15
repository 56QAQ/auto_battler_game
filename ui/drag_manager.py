from __future__ import annotations

from typing import Any, Optional, Tuple
from ui.constants import ITEM_SLOT_SIZE, SLOT_SIZE
import pygame

from states.enums import UnitLocation
from ui.ui_context import UIContext


class DragManager:

    def __init__(self, context: UIContext):
        self.ctx = context
        self.active: bool = False
        self.candidate_info: Optional[Tuple[UnitLocation, Any, Any]] = None
        self.start_pos: Tuple[int, int] | None = None
        self.obj_info: Optional[Tuple[UnitLocation, Any, Any]] = None  # (loc, idx, obj)
        self.preview: Optional[pygame.Surface] = None
        self.offset: Tuple[int, int] = (0, 0)
        self.THRESHOLD: int = 6
    def prepare(self, info: Tuple[UnitLocation, Any, Any], mouse_pos: Tuple[int, int]):
        self.candidate_info = info
        self.start_pos = mouse_pos

    def _activate(self):
        if not self.candidate_info or self.active:
            return
        info = self.candidate_info
        self.candidate_info = None
        self.begin(info, self.start_pos or (0, 0))

    def begin(self, info: Tuple[UnitLocation, Any, Any], mouse_pos: Tuple[int, int]):
        """开始一次拖拽；生成预览 Surface 并记录偏移。"""
        if self.active:
            self.cancel()
        loc, idx, obj = info
        self.active = True
        self.obj_info = info

        # 生成 48×48 的简单缩略图（单位或物品）
        size = (48, 48)
        surf = pygame.Surface(size, pygame.SRCALPHA)
        if loc in [UnitLocation.BOARD, UnitLocation.BENCH, UnitLocation.SHOP]:
            size = (SLOT_SIZE - 2, SLOT_SIZE - 2)
            surf = pygame.Surface(size, pygame.SRCALPHA)
            surf.blit(self.ctx.get_unit_image(obj.name, size), (0, 0))
        else:  # inventory / equipped
            size = (ITEM_SLOT_SIZE - 2, ITEM_SLOT_SIZE - 2)
            surf = pygame.Surface(size, pygame.SRCALPHA)
            surf.blit(self.ctx.get_item_image(obj.name, size), (0, 0))
        pygame.draw.rect(surf, (250, 250, 250), surf.get_rect(), 1)
        self.preview = surf

        mx, my = mouse_pos
        self.offset = (surf.get_width() // 2, surf.get_height() // 2)
        # 清理选中态，防止原槽位仍高亮
        self.ctx.clear_selection()

    def update(self, mouse_pos: Tuple[int, int]):
        """拖拽过程中仅需刷新鼠标坐标；预览绘制在 drawing 内完成。"""
        if self.active:
            return
        if self.candidate_info and self.start_pos:
            dx = mouse_pos[0] - self.start_pos[0]
            dy = mouse_pos[1] - self.start_pos[1]
            if abs(dx) > self.THRESHOLD or abs(dy) > self.THRESHOLD:
                self._activate()
        # Hover 高亮给 input_handler 处理即可

    def end(self):
        """拖拽结束；由 input_handler 根据 mouse_pos 解析实际落点并调用 game logic。"""
        self.active = False
        self.obj_info = None
        self.preview = None
        self.candidate_info = None
        self.start_pos = None

    def cancel(self):
        self.active = False
        self.obj_info = None
        self.preview = None
        self.candidate_info = None
        self.start_pos = None


# Helper：在 UIContext 中挂一份全局实例
_global_mgr: Optional[DragManager] = None


def get_drag_manager(ctx: UIContext) -> DragManager:
    global _global_mgr
    if _global_mgr is None:
        _global_mgr = DragManager(ctx)
    return _global_mgr