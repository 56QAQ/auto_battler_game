# engine/status_effects.py
# 状态效果系统 —— 核心实现
from __future__ import annotations

from abc import ABC
from typing import TYPE_CHECKING, Any, Dict, Optional

from data.enums import DamageSource, DamageType, Element
from engine.enums import RemoveReason, StackRule, StatusCategory

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
    def intercept_incoming_damage(
        self,
        dmg: float,
        damage_type: DamageType,
        source_action: DamageSource = DamageSource.ITEM_ABILITY,
    ) -> float:
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
            element=self.params.get("element"),
        )


class BurningDOT(DamageOverTime):
    """Damage over time that also triggers the source unit."""

    name = "BURN_DOT"
    tick_interval = 0.1

    def on_tick(self, dt: float) -> None:
        super().on_tick(dt)
        from data.enums import TriggerTiming
        from engine.game_state import get_game_state

        state = get_game_state()
        if not state:
            return
        source_unit = next(
            (
                u
                for u in state.player_combat_team + state.enemy_combat_team
                if u.id == self.source_id
            ),
            None,
        )
        if source_unit:
            state.queue_trigger(
                source_unit,
                TriggerTiming.ON_DOT_DAMAGE,
                event_target=self.host,
                data={"damage": self.params.get("damage", 0) * self.stacks},
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


class BleedingEffect(DamageOverTime):
    """Accumulated damage over time applied to the host."""

    name = "BLEED_DOT"

    def on_tick(self, dt: float) -> None:
        from engine.game_state import get_game_state

        dmg_per_tick = self.params.get("damage", 0) * self.stacks
        if dmg_per_tick <= 0 or not self.host.is_alive:
            return
        state = get_game_state()
        source_unit = next(
            (
                u
                for u in state.player_combat_team + state.enemy_combat_team
                if u.id == self.source_id
            ),
            None,
        )
        dealt = self.host.take_damage(
            dmg_per_tick,
            self.params.get("dtype"),
            state,
            source_unit,
            source_action=DamageSource.ITEM_ABILITY,
            element=self.params.get("element"),
        )
        self.host.bleed_damage_progress += dealt
        from data.enums import TriggerTiming

        if (
            source_unit
            and source_unit.trigger
            and source_unit.trigger.get("timing_type") == TriggerTiming.BLEED_THRESHOLD
        ):
            thresh = source_unit.current_stats.get("hp", 0) * source_unit.trigger.get(
                "timing_data", {}
            ).get("threshold", 0)
            if self.host.bleed_damage_progress >= thresh:
                self.host.bleed_damage_progress = 0.0
                state.queue_trigger(
                    source_unit,
                    TriggerTiming.BLEED_THRESHOLD,
                    event_target=source_unit,
                    data={},
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

    def intercept_incoming_damage(
        self,
        dmg: float,
        damage_type: DamageType,
        source_action: DamageSource = DamageSource.ITEM_ABILITY,
    ) -> float:

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


class DecayingShieldEffect(ShieldEffect):
    """Shield that decays each second and explodes when removed."""

    name = "DECAY_SHIELD"
    tick_interval = 1.0

    def __init__(
        self,
        host: "Unit",
        source_id: str,
        duration: float,
        *,
        hp: float,
        damage: float,
    ) -> None:

        super().__init__(
            host, source_id, duration, stack_rule=StackRule.UNIQUE, params={"hp": hp}
        )

        self.params["initial"] = hp
        self.params["damage"] = damage

    def on_tick(self, dt: float) -> None:
        decay = self.params.get("initial", 0.0) * 0.2
        self.params["hp"] = max(0.0, self.params.get("hp", 0.0) - decay)
        if self.params["hp"] <= 0:
            self.host._queue_status_removal(self, RemoveReason.CUSTOM_TRIGGER)

    def on_remove(self, reason: RemoveReason) -> None:
        from data.enums import DamageType, Element
        from engine.game_state import get_game_state
        from ui.constants import COMBAT_UNIT_RADIUS

        if reason == RemoveReason.CUSTOM_TRIGGER:
            state = get_game_state()
            if state:
                caster = next(
                    (
                        u
                        for u in state.player_combat_team + state.enemy_combat_team
                        if u.id == self.source_id
                    ),
                    None,
                )
                if caster:
                    damage = self.params.get("damage", 0.0)
                    pool = (
                        state.enemy_combat_team
                        if caster in state.player_combat_team
                        else state.player_combat_team
                    )
                    radius_sq = (COMBAT_UNIT_RADIUS * 2) ** 2
                    for unit in pool:
                        if not unit.is_alive:
                            continue

                        dx = unit.x - self.host.x
                        dy = unit.y - self.host.y

                        if dx * dx + dy * dy <= radius_sq:
                            out = caster.compute_outgoing_damage(
                                damage,
                                DamageType.MAGIC,
                                DamageSource.ITEM_ABILITY,
                                True,
                                unit,
                            )
                            unit.take_damage(
                                out,
                                DamageType.MAGIC,
                                state,
                                caster,
                                source_action=DamageSource.ITEM_ABILITY,
                                is_aoe=True,
                                element=Element.ICE,
                            )
        super().on_remove(reason)


class DoomBrand(StatusEffect):
    """Mark that explodes at a stack threshold."""

    name = "DOOM_BRAND"
    category = StatusCategory.DEBUFF
    tick_interval = None


class DamageRedirectEffect(StatusEffect):
    """Redirect a portion of incoming damage to another unit."""

    name = "DMG_REDIRECT"
    category = StatusCategory.BUFF
    tick_interval = None

    def intercept_incoming_damage(
        self,
        dmg: float,
        damage_type: DamageType,
        source_action: DamageSource = DamageSource.ITEM_ABILITY,
    ) -> float:
        ratio = self.params.get("ratio", 0.0)
        target_id = self.params.get("target_id")
        if dmg <= 0 or not target_id or ratio <= 0:
            return dmg
        from data.enums import DamageType
        from engine.game_state import get_game_state

        state = get_game_state()
        if not state:
            return dmg
        target = next(
            (
                u
                for u in state.player_combat_team + state.enemy_combat_team
                if u.id == target_id and u.is_alive
            ),
            None,
        )
        if not target:
            return dmg
        redirected = dmg * ratio
        self.params["redirected_total"] = (
            self.params.get("redirected_total", 0.0) + redirected
        )
        target.bond_redirected_total += redirected
        target.take_damage(redirected, DamageType.TRUE, state, self.host, element=None)
        return dmg - redirected

    def on_remove(self, reason: RemoveReason) -> None:
        if reason == RemoveReason.HOST_DEAD:
            from data.enums import TriggerTiming
            from engine.game_state import get_game_state

            state = get_game_state()
            if state:
                target_id = self.params.get("target_id")
                target = next(
                    (
                        u
                        for u in state.player_combat_team + state.enemy_combat_team
                        if u.id == target_id and u.is_alive
                    ),
                    None,
                )
                if target:
                    state.queue_trigger(
                        target,
                        TriggerTiming.ON_BONDED_DEATH,
                        event_target=target,
                        data={
                            "redirect_total": self.params.get("redirected_total", 0.0)
                        },
                    )
                    target.bond_target_id = None
                    target.bond_redirected_total = 0.0
        super().on_remove(reason)


class CritHealBuff(StatusEffect):
    """Critical hits heal the host for damage dealt."""

    name = "CRIT_HEAL"
    category = StatusCategory.BUFF
    tick_interval = None

    def __init__(
        self,
        host: "Unit",
        source_id: str,
        duration: float,
        *,
        crit_chance: float,
        crit_damage: float = 0.0,
    ) -> None:
        super().__init__(host, source_id, duration, stack_rule=StackRule.UNIQUE)
        self.params["crit_chance"] = crit_chance
        self.params["crit_damage"] = crit_damage

    def on_apply(self) -> None:
        self.host.add_stat_modifier(
            "critical_chance",
            self.params.get("crit_chance", 0.0),
            self.duration,
            self.name,
            True,
        )
        if self.params.get("crit_damage", 0.0):
            self.host.add_stat_modifier(
                "critical_damage",
                self.params.get("crit_damage", 0.0),
                self.duration,
                self.name,
                True,
            )
        self.host.add_stat_modifier(
            "crit_heal_percent",
            100.0,
            self.duration,
            self.name,
            False,
        )

    def on_remove(self, reason: RemoveReason) -> None:
        self.host.remove_buffs_from_source(self.name)


class IcyPulseDebuff(StatusEffect):
    """Applies periodic ice damage to the host and nearby enemies."""

    name = "ICY_PULSE"
    category = StatusCategory.DEBUFF
    tick_interval = 1.0

    def __init__(
        self, host: "Unit", source_id: str, duration: float, *, damage: float
    ) -> None:
        super().__init__(host, source_id, duration, stack_rule=StackRule.UNIQUE)
        self.params["damage"] = damage

    def on_tick(self, dt: float) -> None:
        from data.enums import DamageType, Element
        from engine.game_state import get_game_state
        from ui.constants import COMBAT_UNIT_RADIUS

        state = get_game_state()
        if not state or not self.host.is_alive:
            return
        caster = next(
            (
                u
                for u in state.player_combat_team + state.enemy_combat_team
                if u.id == self.source_id
            ),
            None,
        )
        if not caster:
            caster = self.host
        dmg = self.params.get("damage", 0.0)
        pool = (
            state.enemy_combat_team
            if caster in state.player_combat_team
            else state.player_combat_team
        )
        radius_sq = (COMBAT_UNIT_RADIUS * 4) ** 2

        targets = [self.host] + [
            u
            for u in pool
            if (u.x - self.host.x) ** 2 + (u.y - self.host.y) ** 2 <= radius_sq
        ]

        for tgt in targets:
            if not tgt.is_alive:
                continue
            outgoing = caster.compute_outgoing_damage(
                dmg,
                DamageType.MAGIC,
                DamageSource.ITEM_ABILITY,
                True,
                tgt,
            )
            tgt.take_damage(
                outgoing,
                DamageType.MAGIC,
                state,
                caster,
                source_action=DamageSource.ITEM_ABILITY,
                is_aoe=True,
                element=Element.ICE,
            )


class ElementalAura(StatusEffect):
    """Base aura applied by elemental damage. Holds the element in params."""

    name = "ELEMENTAL_AURA"
    category = StatusCategory.BUFF
    tick_interval = None

    def __init__(self, host: "Unit", source_id: str, element: Element):
        super().__init__(
            host,
            source_id,
            duration=None,
            stack_rule=StackRule.UNIQUE,
            params={"element": element},
        )


class ChillDebuff(StatusEffect):
    name = "CHILL"
    category = StatusCategory.DEBUFF
    tick_interval = None

    def __init__(self, host: "Unit", source_id: str, duration: float = 3.0):
        super().__init__(host, source_id, duration)

    def on_apply(self) -> None:
        self.host.add_stat_modifier("as", -30, None, self.name, True)
        self.host.add_stat_modifier("move_speed", -30, None, self.name, True)

    def on_remove(self, reason: RemoveReason) -> None:
        self.host.remove_buffs_from_source(self.name)


class IgniteDebuff(StatusEffect):
    name = "IGNITE"
    category = StatusCategory.DEBUFF
    tick_interval = None

    def __init__(self, host: "Unit", source_id: str, duration: float = 3.0):
        super().__init__(host, source_id, duration)

    def on_apply(self) -> None:
        self.host.add_stat_modifier("mr", -30, self.duration, self.name, True)
        self.host.add_stat_modifier("armor", -30, self.duration, self.name, True)

    def on_remove(self, reason: RemoveReason) -> None:
        self.host.remove_buffs_from_source(self.name)


class ShockDebuff(StatusEffect):
    name = "SHOCK"
    category = StatusCategory.DEBUFF
    tick_interval = None

    def __init__(self, host: "Unit", source_id: str, duration: float = 30.0):

        super().__init__(host, source_id, duration)

    def on_apply(self) -> None:
        self.host.add_stat_modifier("accuracy", -30, self.duration, self.name, True)
        self.host.add_stat_modifier("dodge_chance", -30, self.duration, self.name, True)

    def on_remove(self, reason: RemoveReason) -> None:
        self.host.remove_buffs_from_source(self.name)


class SuperconductDebuff(StatusEffect):
    name = "SUPERCONDUCT"
    category = StatusCategory.DEBUFF
    tick_interval = None

    def __init__(self, host: "Unit", source_id: str, duration: float = 8.0):
        super().__init__(host, source_id, duration)

    def on_apply(self) -> None:
        self.host.add_stat_modifier(
            "percentage_damage_reduction", -30, self.duration, self.name, False
        )

    def on_remove(self, reason: RemoveReason) -> None:
        self.host.remove_buffs_from_source(self.name)


class LeechingDOT(DamageOverTime):
    """DOT that heals the caster based on damage dealt."""

    name = "LEECH_DOT"
    tick_interval = 1.0

    def on_tick(self, dt: float) -> None:
        from engine.game_state import get_game_state

        dmg_per_tick = self.params.get("damage", 0) * self.stacks
        if dmg_per_tick <= 0 or not self.host.is_alive:
            return
        state = get_game_state()
        source_unit = next(
            (
                u
                for u in state.player_combat_team + state.enemy_combat_team
                if u.id == self.source_id
            ),
            None,
        )
        dealt = self.host.take_damage(
            dmg_per_tick,
            self.params.get("dtype", DamageType.MAGIC),
            state,
            source_unit,
            source_action=DamageSource.ITEM_ABILITY,
            element=self.params.get("element"),
        )
        if source_unit and dealt > 0:
            source_unit.heal(
                dealt * self.params.get("heal_ratio", 2.0),
                state,
                source_unit,
                source_action=DamageSource.ITEM_ABILITY,
            )


class SpeedShieldEffect(ShieldEffect):
    """Shield that modifies speed while active and optionally decays."""

    name = "SPEED_SHIELD"
    tick_interval = 1.0

    def __init__(
        self,
        host: "Unit",
        source_id: str,
        duration: float,
        *,
        hp: float,
        speed_mod: float,
        decay: bool = True,
    ) -> None:
        super().__init__(
            host, source_id, duration, stack_rule=StackRule.UNIQUE, params={"hp": hp}
        )
        self.params["initial"] = hp
        self.params["speed_mod"] = speed_mod
        self.params["decay"] = decay

    def on_apply(self) -> None:
        mod = self.params.get("speed_mod", 0.0)
        self.host.add_stat_modifier("as", mod, None, self.name, True)
        self.host.add_stat_modifier("move_speed", mod, None, self.name, True)

    def on_tick(self, dt: float) -> None:
        if not self.params.get("decay", True):
            return
        decay = self.params.get("initial", 0.0) * 0.2
        self.params["hp"] = max(0.0, self.params.get("hp", 0.0) - decay)
        if self.params["hp"] <= 0:
            self.host._queue_status_removal(self, RemoveReason.CUSTOM_TRIGGER)

    def on_remove(self, reason: RemoveReason) -> None:
        self.host.remove_buffs_from_source(self.name)
        super().on_remove(reason)


class DamageWardBuff(StatusEffect):
    """Reduces incoming damage of specified types."""

    name = "DAMAGE_WARD"
    category = StatusCategory.BUFF
    tick_interval = None

    def __init__(
        self,
        host: "Unit",
        source_id: str,
        duration: Optional[float],
        *,
        reduction: float,
        types: list[DamageType],
    ) -> None:
        super().__init__(host, source_id, duration, stack_rule=StackRule.UNIQUE)
        self.params["reduction"] = reduction
        self.params["types"] = types

    def intercept_incoming_damage(
        self,
        dmg: float,
        damage_type: DamageType,
        source_action: DamageSource = DamageSource.ITEM_ABILITY,
    ) -> float:
        if damage_type not in self.params.get("types", []):
            return dmg
        reduction = self.params.get("reduction", 0.0)
        if reduction >= 100:
            from engine.game_state import get_game_state

            state = get_game_state()
            if state and dmg > 0:
                self.host.heal(
                    dmg * (reduction - 100) / 100.0,
                    state,
                    self.host,
                    source_action=DamageSource.ITEM_ABILITY,
                )
            return 0.0
        return dmg * (1.0 - reduction / 100.0)


class BasicAttackBlockEffect(StatusEffect):
    """Reduce damage from basic attacks with an internal cooldown."""

    name = "BASIC_BLOCK"
    category = StatusCategory.BUFF
    tick_interval = None

    def __init__(
        self,
        host: "Unit",
        source_id: str,
        *,
        reduction: float,
        cooldown: float,
    ) -> None:
        super().__init__(host, source_id, None, stack_rule=StackRule.UNIQUE)
        self.params["reduction"] = reduction
        self.params["cooldown"] = cooldown
        self.params["last_time"] = -cooldown

    def intercept_incoming_damage(
        self,
        dmg: float,
        damage_type: DamageType,
        source_action: DamageSource = DamageSource.ITEM_ABILITY,
    ) -> float:
        if source_action != DamageSource.BASIC_ATTACK:
            return dmg
        from engine.game_state import get_game_state

        state = get_game_state()
        current = state.combat_timer if state else 0.0
        last = self.params.get("last_time", -self.params.get("cooldown", 0.0))
        if current - last >= self.params.get("cooldown", 0.0):
            self.params["last_time"] = current
        return max(0.0, dmg - self.params.get("reduction", 0.0))


class DashTauntEffect(StatusEffect):
    """Dash forward and taunt enemies when applied."""

    name = "DASH_TAUNT"
    category = StatusCategory.BUFF
    tick_interval = None

    def __init__(self, host: "Unit", source_id: str, *, distance: float) -> None:
        super().__init__(host, source_id, None, stack_rule=StackRule.UNIQUE)
        self.params["distance"] = distance

    def on_apply(self) -> None:
        from engine.game_state import get_game_state

        dist = self.params.get("distance", 0.0)
        if self.host.is_enemy:
            self.host.y += 0.0
        self.host.x += dist if not self.host.is_enemy else -dist
        state = get_game_state()
        if state:
            pool = (
                state.player_combat_team
                if self.host.is_enemy
                else state.enemy_combat_team
            )
            for u in pool:
                if u.is_alive:
                    u.target = self.host


class MeleeBlastEffect(StatusEffect):
    """Damage and stun melee attackers targeting the host."""

    name = "MELEE_BLAST"
    category = StatusCategory.BUFF
    tick_interval = None

    def __init__(
        self,
        host: "Unit",
        source_id: str,
        interval: float | None = None,
    ) -> None:
        super().__init__(host, source_id, None, stack_rule=StackRule.UNIQUE)
        if interval:
            self.tick_interval = interval

    def _blast(self) -> None:
        from data.constants import MELEE_RANGE_THRESHOLD
        from engine.game_state import get_game_state

        state = get_game_state()
        if not state:
            return
        pool = (
            state.player_combat_team if self.host.is_enemy else state.enemy_combat_team
        )
        for u in pool:
            if (
                u.is_alive
                and u.target is self.host
                and u.current_stats.get("range", 50) <= MELEE_RANGE_THRESHOLD
            ):
                dmg = self.host.current_stats.get("ap", 0)
                dealt = u.take_damage(
                    dmg,
                    DamageType.PHYSICAL,
                    state,
                    self.host,
                    source_action=DamageSource.ITEM_ABILITY,
                    is_aoe=False,
                )
                if dealt > 0:
                    st = ActionDenialEffect(u, self.host.id, 1.0)
                    u.add_status(st)

    def on_apply(self) -> None:
        self._blast()

    def on_tick(self, dt: float) -> None:
        if self.tick_interval:
            self._blast()


class MagicWardBuff(DamageWardBuff):
    name = "MAGIC_WARD"

    def __init__(
        self,
        host: "Unit",
        source_id: str,
        duration: Optional[float],
        *,
        reduction: float,
    ) -> None:
        super().__init__(
            host, source_id, duration, reduction=reduction, types=[DamageType.MAGIC]
        )


class AllWardBuff(DamageWardBuff):
    name = "ALL_WARD"

    def __init__(
        self, host: "Unit", source_id: str, duration: float, *, reduction: float
    ) -> None:
        super().__init__(
            host,
            source_id,
            duration,
            reduction=reduction,
            types=[DamageType.MAGIC, DamageType.PHYSICAL, DamageType.TRUE],
        )


class EvasiveWeaknessBuff(StatusEffect):
    """Increase dodge chance but take more physical damage."""

    name = "EVASIVE_WEAK"
    category = StatusCategory.BUFF
    tick_interval = None

    def on_apply(self) -> None:
        self.host.add_stat_modifier("dodge_chance", 35, None, self.name, True)
        self.host.add_stat_modifier(
            "percentage_physical_damage_reduction", 25, None, self.name, False
        )

    def on_remove(self, reason: RemoveReason) -> None:
        self.host.remove_buffs_from_source(self.name)


class PositionShiftEffect(StatusEffect):
    """Move the host to a fixed Y position when applied."""

    name = "SHIFT_Y"
    category = StatusCategory.BUFF
    tick_interval = None

    def __init__(self, host: "Unit", source_id: str, *, y: float) -> None:
        super().__init__(host, source_id, None, stack_rule=StackRule.UNIQUE)
        self.params["y"] = y

    def on_apply(self) -> None:
        self.host.y = self.params.get("y", self.host.y)


class SelfDestructEffect(StatusEffect):
    """Explodes when duration expires, damaging all units."""

    name = "SELF_DESTRUCT"
    category = StatusCategory.DEBUFF
    tick_interval = None

    def __init__(self, host: "Unit", source_id: str, duration: float, damage: float) -> None:
        super().__init__(host, source_id, duration, stack_rule=StackRule.UNIQUE)
        self.params["damage"] = damage

    def on_remove(self, reason: RemoveReason) -> None:
        if reason == RemoveReason.EXPIRED and self.host.is_alive:
            from data.enums import DamageType
            from engine.game_state import get_game_state

            state = get_game_state()
            dmg = self.params.get("damage", 0.0)
            if state:
                for u in state.player_combat_team + state.enemy_combat_team:
                    if u.is_alive:
                        u.take_damage(
                            dmg,
                            DamageType.MAGIC,
                            state,
                            self.host,
                            source_action=DamageSource.ITEM_ABILITY,
                            is_aoe=True,
                        )
                self.host.take_damage(
                    self.host.current_hp,
                    DamageType.TRUE,
                    state,
                    self.host,
                    source_action=DamageSource.ITEM_ABILITY,
                    is_aoe=False,
                )
        self.host.remove_buffs_from_source(self.name)
        super().on_remove(reason)


class DamageStoreBuff(StatusEffect):
    """Reduce damage taken and store the prevented amount."""

    name = "DAMAGE_STORE"
    category = StatusCategory.BUFF
    tick_interval = None

    def __init__(self, host: "Unit", source_id: str) -> None:
        super().__init__(host, source_id, None, stack_rule=StackRule.UNIQUE)
        self.params["stored"] = 0.0

    def on_apply(self) -> None:
        self.host.add_status(AllyShiftBuff(self.host, self.source_id))
        self.host.add_status(WeakAuraSource(self.host, self.source_id))

    def intercept_incoming_damage(
        self,
        dmg: float,
        damage_type: DamageType,
        source_action: DamageSource = DamageSource.ITEM_ABILITY,
    ) -> float:
        prevented = dmg * 0.25
        self.params["stored"] += prevented
        return dmg * 0.75

    def on_remove(self, reason: RemoveReason) -> None:
        self.host.remove_buffs_from_source(AllyShiftBuff.name)
        self.host.remove_buffs_from_source(WeakAuraSource.name)
        super().on_remove(reason)


class AllyShiftBuff(StatusEffect):
    """Adjust stats based on number of living allies."""

    name = "ALLY_SHIFT"
    category = StatusCategory.BUFF
    tick_interval = 0.5

    def on_apply(self) -> None:
        self._apply()

    def on_tick(self, dt: float) -> None:
        self._apply()

    def _apply(self) -> None:
        from engine.game_state import get_game_state

        state = get_game_state()
        if not state:
            return
        team = state.enemy_combat_team if self.host.is_enemy else state.player_combat_team
        count = sum(1 for u in team if u.is_alive and u is not self.host)
        if count == self.params.get("count"):
            return
        self.host.remove_buffs_from_source(self.name)
        self.host.add_stat_modifier("ad", -10 * count, None, self.name, False)
        self.host.add_stat_modifier("ap", -10 * count, None, self.name, False)
        self.host.add_stat_modifier("armor", 10 * count, None, self.name, False)
        self.host.add_stat_modifier("mr", 10 * count, None, self.name, False)
        self.params["count"] = count

    def on_remove(self, reason: RemoveReason) -> None:
        self.host.remove_buffs_from_source(self.name)


class WeakAuraSource(StatusEffect):
    """Apply a global attack/AP debuff while host is alive."""

    name = "WEAK_AURA"
    category = StatusCategory.BUFF
    tick_interval = None

    def on_apply(self) -> None:
        from engine.game_state import get_game_state

        state = get_game_state()
        if not state:
            return
        affected: list[str] = []
        for u in state.player_combat_team + state.enemy_combat_team:
            if u is self.host:
                continue
            u.add_stat_modifier("ad", -25, None, self.name, True)
            u.add_stat_modifier("ap", -25, None, self.name, True)
            affected.append(u.id)
        self.params["affected"] = affected

    def on_remove(self, reason: RemoveReason) -> None:
        from engine.game_state import get_game_state

        state = get_game_state()
        if state:
            for u in state.player_combat_team + state.enemy_combat_team:
                if u.id in self.params.get("affected", []):
                    u.remove_buffs_from_source(self.name)
        super().on_remove(reason)
