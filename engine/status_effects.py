# engine/status_effects.py
# 状态效果系统 —— 核心实现
from __future__ import annotations
import math
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, TYPE_CHECKING, List

from engine.enums import StatusCategory, StackRule, RemoveReason

if TYPE_CHECKING:
    from engine.classes import Unit


class StatusEffect(ABC):
    """
    抽象基类：所有具体状态效果需实现 `on_apply` 与 `on_tick`。
    派生类可覆写 hook 以响应宿主受击/攻击等事件。
    """

    ## ---- 公共接口 ------------------------------------------------------ ##
    name: str = "BASE_STATUS"
    category: StatusCategory = StatusCategory.BUFF
    tick_interval: float = 1.0  # 若无需周期触发，可设为 None

    def __init__(
        self,
        host: "Unit",
        source_id: str,
        duration: Optional[float] = None,
        stacks: int = 1,
        undispellable: bool = False,
        stack_rule: StackRule = StackRule.UNLIMITED,
        params: Optional[Dict[str, Any]] = None,
    ):
        self.host = host
        self.source_id = source_id
        self.duration = duration
        self.remaining = duration
        self.stacks = max(1, stacks)
        self.undispellable = undispellable
        self.stack_rule = stack_rule
        self.params = params or {}
        self._tick_timer = 0.0

    # ---- 生命周期 ----
    def on_apply(self) -> None:
        """首次附加到宿主时调用"""

    def on_remove(self, reason: RemoveReason) -> None:
        """被移除时调用"""

    def on_tick(self, dt: float) -> None:
        """每经过 `tick_interval` 调用；默认空实现"""

    # ---- 宿主钩子（可选覆写） ----
    def intercept_incoming_damage(self, dmg: float) -> float:
        """可以修改或吸收即将受到的伤害；返回修改后数值"""
        return dmg

    def blocks_action(self) -> bool:
        """若返回 True，则宿主无法攻击/施法/移动"""
        return False

    # ---- 内部驱动 ----
    def _update(self, dt: float) -> bool:
        """
        由 `Unit.process_statuses` 调用。
        返回 True 表示效果已到期，需要从宿主列表里移除。
        """
        if self.duration is not None:
            self.remaining -= dt
            if self.remaining <= 0:
                return True

        if self.tick_interval:
            self._tick_timer += dt
            while self._tick_timer >= self.tick_interval:
                self._tick_timer -= self.tick_interval
                self.on_tick(self.tick_interval)
        return False


# --------------------------------------------------------------------- #
#                    ---- 具体效果示例子类 ----                          #
# --------------------------------------------------------------------- #

class DamageOverTime(StatusEffect):
    name = "DOT"
    category = StatusCategory.DOT

    def on_tick(self, dt: float):
        dmg_per_tick = self.params.get("damage", 0) * self.stacks
        if dmg_per_tick > 0 and self.host.is_alive:
            # TRUE 伤害避免重复计算抗性
            self.host.take_damage(dmg_per_tick, self.params.get("dtype"), None, None)


class HealOverTime(StatusEffect):
    name = "HOT"
    category = StatusCategory.HOT

    def on_tick(self, dt: float):
        heal = self.params.get("heal", 0) * self.stacks
        if heal > 0 and self.host.is_alive:
            self.host.heal(heal)


class StatModifierEffect(StatusEffect):
    """
    用于属性增减（基于新体系重写旧 Buff）。
    params: { "stat": "ad", "flat": 20, "percent": 0 }
    """

    name = "STAT_MOD"
    category = StatusCategory.BUFF

    def on_apply(self):
        self.host._recalculate_stats(0)  # 立即刷新

    def on_remove(self, reason: RemoveReason):
        self.host._recalculate_stats(0)


class ActionDenialEffect(StatusEffect):
    """冰冻 / 晕眩 / 石化等"""

    name = "STUN"
    category = StatusCategory.ACTION_BLOCK

    def blocks_action(self) -> bool:
        return True


class ShieldEffect(StatusEffect):
    """
    吸收一次伤害后消失；`params = {"hp": 100}`
    """

    name = "SHIELD"
    category = StatusCategory.SHIELD

    def intercept_incoming_damage(self, dmg: float) -> float:
        capacity = self.params.setdefault("hp", 0)
        if capacity <= 0:
            return dmg  # 已被耗尽
        absorbed = min(dmg, capacity)
        self.params["hp"] -= absorbed
        dmg -= absorbed
        # 护盾耗尽则移除
        if self.params["hp"] <= 0:
            self.host._queue_status_removal(self, RemoveReason.CUSTOM_TRIGGER)
        return dmg