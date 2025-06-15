# engine/status_effects.py
# 状态效果系统 —— 核心实现
from __future__ import annotations
import math
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, TYPE_CHECKING, List

from engine.enums import StatusCategory, StackRule, RemoveReason
from data.enums import DamageSource
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

    def on_tick(self, dt: float) -> None:
        from engine.game_state import get_game_state
        dmg_per_tick = self.params.get("damage", 0) * self.stacks
        if dmg_per_tick > 0 and self.host.is_alive:
            # TRUE 伤害避免重复计算抗性
            state = get_game_state()
            source_unit = next(
                (
                    u
                    for u in state.player_combat_team + state.enemy_combat_team
                    if u.id == self.source_id
                ),
                None,
            )
            self.host.take_damage(
                dmg_per_tick,
                self.params.get("dtype"),
                state,
                source_unit,
                source_action=DamageSource.ITEM_ABILITY,
            )


class HealOverTime(StatusEffect):
    name = "HOT"
    category = StatusCategory.HOT

    def on_tick(self, dt: float) -> None:
        from engine.game_state import get_game_state
        heal = self.params.get("heal", 0) * self.stacks
        if heal > 0 and self.host.is_alive:
            state = get_game_state()
            source_unit = next(
                (
                    u
                    for u in state.player_combat_team + state.enemy_combat_team
                    if u.id == self.source_id
                ),
                None,
            )
            self.host.heal(
                heal,
                state,
                source_unit,
                source_action=DamageSource.ITEM_ABILITY,
            )


class StatModifierEffect(StatusEffect):
    """
    用于属性增减（基于新体系重写旧 Buff）。
    params: { "stat": "ad", "flat": 20, "percent": 0 }
    """

    name = "STAT_MOD"
    category = StatusCategory.BUFF

    def __init__(
        self,
        host: "Unit",
        source_id: str,
        duration: Optional[float],
        stacks: int = 1,
        undispellable: bool = False,
        stack_rule: StackRule = StackRule.UNLIMITED,
        params: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            host, source_id, duration, stacks, undispellable, stack_rule, params
        )
        if "stat" not in self.params:
            raise ValueError("StatModifierEffect requires 'stat'")

        # 兼容旧 value/is_percent 写法
        if (
            "value" in self.params
            and "flat" not in self.params
            and "percent" not in self.params
        ):
            if self.params.get("is_percent", False):
                self.params["percent"] = self.params["value"]
                self.params["flat"] = 0.0
            else:
                self.params["flat"] = self.params["value"]
                self.params["percent"] = 0.0

        self.params.setdefault("flat", 0.0)
        self.params.setdefault("percent", 0.0)

    # ---- 提供给 Unit 统计 ----
    def get_flat(self) -> float:
        return self.params["flat"] * self.stacks

    def get_percent(self) -> float:
        return self.params["percent"] * self.stacks

    def on_apply(self):
        self.host._recalculate_stats(0)

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
        super().__init__(
            host, source_id, duration, stacks, undispellable, stack_rule, params
        )
        self.params.setdefault("hp", 0.0)
        self.params.setdefault("accumulated", self.params["hp"])
        
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
        return dmg

    def on_remove(self, reason: RemoveReason) -> None:
        if reason == RemoveReason.CUSTOM_TRIGGER:
            from data.enums import TriggerTiming
            from engine.game_state import get_game_state

            state = get_game_state()
            if state:
                state.queue_trigger(
                    self.host,
                    TriggerTiming.ON_SHIELD_BROKEN,
                    event_target=None,
                    data={"shield": self.params.get("accumulated", 0.0)},
                )
        super().on_remove(reason)