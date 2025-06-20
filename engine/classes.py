# engine/classes.py
# forward declarations
from __future__ import annotations

import math
import random
import uuid
from collections import defaultdict, deque

# FIX: Add Callable to typing imports
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Tuple

from ai.behaviors import BehaviorContext  # NEW
from data.constants import (
    ATTACK_ANIM_DURATION,
    ATTACK_LUNGE_ANGLE,
    BOSS_NODES,
    CAST_ANIM_DURATION,
    DEATH_ANIM_DURATION,
    DEFAULT_MOVE_SPEED,
    FLOATER_LIFESPAN,
    FLOATER_SPEED,
    HARD_NODES,
    HEAL_ANIM_DURATION,
    HIT_ANIM_DURATION,
    HIT_RECOIL_ANGLE,
    IDLE_WOBBLE_ANGLE,
    IDLE_WOBBLE_SPEED,
    LEVEL_PROBABILITIES,
    MAP_DEPTH,
    MAX_ITEMS_EQUIPPED,
    MAX_LEVEL,
    MEDIUM_NODES,
    NODE_TYPE_DISTRIBUTION,
    NODES_PER_LAYER,
    PROJECTILE_SPEED,
    RARITY_COST,
    RARITY_ORDER,
    STARTING_HEALTH,
    UNIT_POOL_SIZE_MULTIPLIER,
    XP_PER_LEVEL,
)

# Data imports
from data.definitions import ARTIFACT_DEFINITIONS, ITEM_DEFINITIONS, UNIT_DEFINITIONS

# 新增 DamageSource
from data.enums import (
    AbilityEffect,
    Color,
    DamageSource,
    DamageType,
    Element,
    ItemType,
    TriggerTarget,
    TriggerTiming,
)

# Engine imports
from engine.enums import AnimationState, EffectType, RemoveReason
from engine.status_effects import (
    ChillDebuff,
    ElementalAura,
    IgniteDebuff,
    ShockDebuff,
    StackRule,
    StatModifierEffect,
    StatusEffect,
    SuperconductDebuff,
)

# from engine.utils import clamp, lerp, normalize_vector
# UI Constants used for positioning/size - ideally pass these in, but for now:
from ui.constants import (
    BENCH_SLOTS,
    BOARD_COLS,
    BOARD_ROWS,
    COMBAT_UNIT_RADIUS,
    MAP_HEIGHT,
    MAP_NODE_RADIUS,
    MAP_WIDTH,
    MAP_X_START,
    MAP_Y_START,
    SHOP_SLOTS,
)

# Conditional type import to avoid circular dependency
if TYPE_CHECKING:
    from engine.game_state import Buff, GameState, SynergyStatus

    # FIX: remove redundant type hint
    # from engine.logic import resolve_trigger # Unit.take_damage needs this

# Need to import logic functions carefully or pass them as args to avoid circularity
# e.g., resolve_trigger -> find_targets -> logic needs GameState -> logic needs Unit
# Solution: Pass state (which includes resolve_trigger reference) or import locally/carefully

# Forward declare logic functions needed by Unit class
# These will be assigned by logic.py or main.py after definition
# FIX: This attribute holds the actual function pointer, assigned by logic.py
resolve_trigger_func: Optional[Callable] = None
resolve_passive_func: Optional[Callable] = None


class Item:
    def __init__(
        self,
        name: str,
        *,
        item_type: ItemType | None = None,
        type: ItemType | None = None,
        color: Color | None = None,
        rarity: str | None = None,
        material_cost: int = 0,
        stats_override: dict | None = None,
    ):
        self.name = name
        # ---------- 旧数据表 ---------- #
        definition = ITEM_DEFINITIONS.get(name)
        if definition and not item_type:
            type_str = definition.get("type", "ARMAMENT")
            self.item_type = ItemType.__members__.get(type_str, ItemType.ARMAMENT)
            self.type = self.item_type
            col = definition.get("color", "WHITE")
            self.color = Color.__members__.get(str(col), Color.WHITE)
            self.rarity = definition.get("rarity", "COMMON")
            self.stats = definition.get("stats", {})
            self.ability = definition.get("ability")
            self.special = definition.get("special")
        else:
            # ---------- 新 Color‑Item 模式 ---------- #
            self.item_type = item_type or ItemType.ARMAMENT
            self.type = self.item_type
            self.color = color or Color.WHITE
            self.rarity = rarity or "COMMON"
            self.stats = stats_override or {}
            self.ability = None
            self.special = None

        self.material_cost = material_cost
        self.description = f"{self.rarity.title()} {self.item_type.value}"
        self.id = str(uuid.uuid4())

    # ---------------- Equip rules ---------------- #
    def can_equip(self, unit: "Unit") -> bool:
        """颜色／专属校验."""
        if self.item_type == ItemType.ARMAMENT:
            return True
        if self.item_type == ItemType.MODULE:
            # 专属：名称前缀匹配（占位实现）
            return self.name.split("_")[-1] == unit.name.replace(" ", "")
        # Disk – 颜色兼容表
        ucol = getattr(unit, "primary_color", Color.WHITE)
        allowed: dict[Color, set[Color]] = {
            Color.WHITE: set(Color),
            Color.RED: {Color.RED, Color.YELLOW, Color.PURPLE, Color.BLACK},
            Color.BLUE: {Color.BLUE, Color.PURPLE, Color.CYAN, Color.BLACK},
            Color.GREEN: {Color.GREEN, Color.YELLOW, Color.CYAN, Color.BLACK},
            Color.PURPLE: {Color.PURPLE, Color.BLACK},
            Color.YELLOW: {Color.YELLOW, Color.BLACK},
            Color.CYAN: {Color.CYAN, Color.BLACK},
            Color.BLACK: {Color.BLACK},
        }
        return self.color in allowed.get(ucol, set())

    def __repr__(self):
        return f"<Item {self.name}>"


class Artifact:
    def __init__(self, name: str):
        self.name = name
        self.definition = ARTIFACT_DEFINITIONS.get(
            name, {"type": "UNKNOWN", "description": "?"}
        )
        self.type = self.definition["type"]
        self.description = self.definition.get("description", "")
        self.id = str(uuid.uuid4())

    def __repr__(self):
        return f"<Artifact {self.name}>"


class DamageFloater:
    def __init__(
        self, x: float, y: float, text: str, color_key: str, lifespan=FLOATER_LIFESPAN
    ):
        # Color Key allows UI to map to actual color
        self.x = x + random.uniform(-5, 5)
        self.y = y + random.uniform(-10, 0)
        self.text = text
        self.color_key = color_key
        self.lifespan = lifespan
        self.timer = 0.0

    def update(self, dt: float):
        self.timer += dt
        self.y -= FLOATER_SPEED * dt

    def is_expired(self) -> bool:
        return self.timer >= self.lifespan

    # draw method moved to ui/


class VisualEffect:
    def __init__(
        self,
        effect_type: EffectType,
        x: float,
        y: float,
        lifespan: float,
        color_key: str,
        target_pos: Optional[Tuple[float, float]] = None,
        size: float = 5.0,
        angle: float = 0.0,
    ):
        from engine.utils import normalize_vector

        self.type = effect_type
        self.x, self.y = x, y
        self.start_x, self.start_y = x, y
        self.target_x, self.target_y = target_pos if target_pos else (x, y)
        self.lifespan = lifespan
        self.timer = 0.0
        self.color_key = color_key  # UI maps key to color
        self.size = size
        self.angle = angle
        self.dx, self.dy, self.dist = 0.0, 0.0, 0.0
        if self.type in [EffectType.PROJECTILE_BASIC, EffectType.PROJECTILE_MAGIC]:
            self.dx, self.dy, self.dist = normalize_vector(
                self.target_x - self.x,
                self.target_y - self.y,
                math.dist((self.x, self.y), (self.target_x, self.target_y)),
            )
            if self.dist > 0:
                # FIX: Ensure lifespan is not zero or negative
                self.lifespan = max(
                    0.01, self.dist / PROJECTILE_SPEED
                )  # Override lifespan based on distance

    def update(self, dt: float):
        from engine.utils import clamp, lerp

        self.timer += dt
        if self.type in [EffectType.PROJECTILE_BASIC, EffectType.PROJECTILE_MAGIC]:
            if self.dist > 0 and self.lifespan > 0:  # FIX: check lifespan > 0
                progress = clamp(self.timer / self.lifespan, 0, 1)
                self.x = lerp(self.start_x, self.target_x, progress)
                self.y = lerp(self.start_y, self.target_y, progress)

    def is_expired(self) -> bool:
        return self.timer >= self.lifespan

    # draw method moved to ui/


class Unit:
    def __init__(
        self,
        name: str,
        definition: Dict,
        level: int = 1,
        unit_id: Optional[str] = None,
        is_enemy: bool = False,
    ):
        self.name = name
        self.id = unit_id if unit_id else str(uuid.uuid4())
        self.definition = definition
        self.rarity = definition["rarity"]
        self.primary_color: Color = definition.get("primary_color", Color.WHITE)
        self.secondary_synergies = definition.get("secondary_synergies", [])
        self.traits = definition.get("traits", [])
        if (
            self.primary_color == Color.WHITE
            and self.traits
            and isinstance(self.traits[0], str)
        ):
            tag = self.traits[0].upper()
            _map = {
                "RED": Color.RED,
                "GREEN": Color.GREEN,
                "BLUE": Color.BLUE,
                "PURPLE": Color.PURPLE,
                "YELLOW": Color.YELLOW,
                "CYAN": Color.CYAN,
                "BLACK": Color.BLACK,
                "WHITE": Color.WHITE,
            }
            self.primary_color = _map.get(tag, Color.WHITE)
        self.trigger = definition.get("trigger", {})
        self.passive = definition.get("passive", {})
        if "timing_type" not in self.passive:
            self.passive["timing_type"] = None
        self.level = level
        self.is_enemy = is_enemy
        self.equipped_items: List[Optional[Item]] = [None] * MAX_ITEMS_EQUIPPED
        self.radius = COMBAT_UNIT_RADIUS

        level_multiplier = 1.8 ** (level - 1)
        self.base_stats = {
            k: v * (level_multiplier if k in ["hp", "ad", "ap"] else 1)
            for k, v in definition["base_stats"].items()
        }
        if "ap" not in self.base_stats:
            self.base_stats["ap"] = 0

        _extended_defaults = {
            "percentage_damage_bonus": 100.0,
            "flat_damage_bonus": 0.0,
            "percentage_damage_reduction": 100.0,
            "flat_damage_reduction": 0.0,
            "flat_basic_attack_damage_reduction": 0.0,
            "outgoing_healing_bonus": 100.0,
            "incoming_healing_bonus": 100.0,
            "physical_lifesteal": 0.0,
            "spell_lifesteal": 0.0,
            "omnivamp": 0.0,
            "flat_physical_penetration": 0.0,
            "flat_magic_penetration": 0.0,
            "percentage_physical_penetration": 0.0,
            "percentage_magic_penetration": 0.0,
            "critical_chance": 5.0,
            "critical_damage": 150.0,
            "dodge_chance": 5.0,
            "accuracy": 0.0,
            "move_speed": DEFAULT_MOVE_SPEED,
        }
        for _k, _v in _extended_defaults.items():
            self.base_stats.setdefault(_k, _v)

        self.current_stats = self.base_stats.copy()
        self.current_hp = self.current_stats["hp"]
        # 以下两容器仅为兼容旧代码，实际已由状态系统接管
        self.applied_buffs: List["Buff"] = []
        self.synergy_artifact_buffs: List[Dict] = []
        # -------- 新增：状态效果挂载点 --------
        # key = status.name  ; value = List[StatusEffect]
        self.statuses: Dict[str, List[StatusEffect]] = defaultdict(list)
        # 待移除队列，避免遍历时修改列表
        self._pending_status_removals: "deque[tuple[StatusEffect, RemoveReason]]" = (
            deque()
        )

        self.x: float = 0.0
        self.y: float = 0.0
        self.target: Optional["Unit"] = None
        self.attack_timer: float = 0.0
        self.trigger_timer: float = 0.0
        self.passive_timer: float = 0.0
        self.magic_damage_progress: float = 0.0
        self.physical_damage_progress: float = 0.0
        self.damage_progress: float = 0.0
        self.damage_taken_progress: float = 0.0
        self.heal_progress: float = 0.0
        self.healed_progress: float = 0.0
        self.is_alive: bool = True
        self.timer_event_tally: int = 0
        self.timer_haste_multiplier: float = 1.0
        # Color keys for UI
        self.base_color_key = "WHITE"
        self.current_color_key = self.base_color_key

        self.anim_state: AnimationState = AnimationState.IDLE
        self.anim_timer: float = random.uniform(0, 5)  # offset idle
        self.rotation_offset: float = 0.0
        self.flash_color_key: Optional[str] = None  # UI maps key
        self._recalculate_stats(0)
        self._last_outgoing_was_crit: bool = False
        self._last_outgoing_missed: bool = False
        # ========== AI runtime fields ========== #
        self.behavior = BehaviorContext(self)  # smart‑AI wrapper
        self.behavior = BehaviorContext(self)  # smart‑AI wrapper
        self._blocked_time: float = 0.0  # for targeting helper
        self.trigger_counts: dict[TriggerTiming, int] = defaultdict(int)
        self.double_heal_stacks: int = 0
        self.double_heal_uses: int = 0
        self.extra_attack_counters: dict[str, int] = {}
        self.purge_counts: dict[str, int] = {}
        self.item_trigger_counts: dict[str, int] = {}
        self.item_trigger_last_time: dict[str, float] = {}
        self.bond_target_id: str | None = None
        self.bond_redirected_total: float = 0.0
        self.bleed_damage_progress: float = 0.0
        self.revive_used: bool = False
        # Last pos for stuck detection handled by BehaviorContext

    def __repr__(self):
        return (
            f"<Unit {self.name} L{self.level} {self.primary_color.name}"
            f" {'E' if self.is_enemy else 'P'}>"
        )

    def get_cost(self) -> int:
        base_cost = RARITY_COST.get(self.rarity, 1)
        if self.level == 1:
            return base_cost
        if self.level == 2:
            return base_cost * 3
        if self.level == 3:
            return base_cost * 9
        return base_cost

    def get_sell_price(self) -> int:
        return max(0, self.get_cost())

    def apply_synergy_artifact_buff(self, buff: Dict, current_time: float = 0):
        for stat, val in buff.items():
            if stat.endswith("_percent"):
                self.add_stat_modifier(stat[:-8], val, None, f"SYNERGY_{stat}", True)
            else:
                self.add_stat_modifier(stat, val, None, f"SYNERGY_{stat}", False)

    # ---------- 新 Buff API（向后兼容旧签名） ----------
    def _create_or_refresh_stat_effect(
        self,
        stat: str,
        value: float,
        duration: Optional[float],
        source_id: str,
        is_percent: bool,
    ):
        existing = None
        for st in self.statuses.get(StatModifierEffect.name, []):
            if (
                isinstance(st, StatModifierEffect)
                and st.source_id == source_id
                and st.params["stat"] == stat
            ):
                existing = st
                break
        if existing:
            existing.duration = duration
            existing.remaining = duration
            if is_percent:
                existing.params["percent"] = value
                existing.params["flat"] = 0.0
            else:
                existing.params["flat"] = value
                existing.params["percent"] = 0.0
            self._recalculate_stats(0)
            return
        params = {
            "stat": stat,
            "flat": 0.0 if is_percent else value,
            "percent": value if is_percent else 0.0,
        }
        effect = StatModifierEffect(
            host=self,
            source_id=source_id,
            duration=duration,
            stacks=1,
            stack_rule=StackRule.UNIQUE,
            params=params,
        )
        self.add_status(effect)

    def add_timed_buff(  # 旧调用保持可用
        self,
        buff_stat: str,
        value: float,
        duration: Optional[float],
        current_time: float,
        source_id: str,
        is_percent: bool,
    ):
        self._create_or_refresh_stat_effect(
            buff_stat, value, duration, source_id, is_percent
        )

    def add_stat_modifier(
        self,
        stat: str,
        value: float,
        duration: Optional[float],
        source_id: str,
        is_percent: bool = False,
    ):
        self._create_or_refresh_stat_effect(
            stat, value, duration, source_id, is_percent
        )

    # 旧接口占位，逻辑已交由状态系统管理
    def _remove_expired_buffs(self, current_time: float) -> bool:
        return False

    def remove_all_buffs(self):
        self.clear_statuses(RemoveReason.DISPEL)
        self._recalculate_stats(0)
        # FIX: ensure HP does not exceed max after buffs removed
        self.current_hp = min(self.current_hp, self.current_stats.get("hp", 1))
        if self.current_hp <= 0 and self.is_alive:
            self.current_hp = self.current_stats.get("hp", 1)  # Use .get for safety
        # 清空新状态体系（可被战斗结束调用）
        self.clear_statuses(RemoveReason.BATTLE_END)

    def remove_buffs_from_source(self, source_id: str) -> None:
        """Remove all status effects originating from the given source."""
        for name in list(self.statuses.keys()):
            for st in list(self.statuses[name]):
                if st.source_id == source_id:
                    self._queue_status_removal(st, RemoveReason.DISPEL)
        self.process_statuses(0.0)

    # ======== Status‑Effect System API ========
    def add_status(self, status: StatusEffect) -> None:
        """将已实例化的 StatusEffect 附加到宿主。"""
        before_count = sum(len(b) for b in self.statuses.values())
        bucket = self.statuses[status.name]
        if status.stack_rule == StackRule.UNIQUE and bucket:
            # 覆盖：移除旧实例
            old = bucket[0]
            self._queue_status_removal(old, RemoveReason.DISPEL)
            bucket.clear()
        bucket.append(status)
        from engine.enums import StatusCategory
        from engine.game_state import get_game_state

        state = get_game_state()
        if state:
            src = next(
                (
                    u
                    for u in state.player_combat_team + state.enemy_combat_team
                    if u.id == status.source_id
                ),
                None,
            )
            if (
                src
                and src.passive
                and src.passive.get("extend_positive_duration")
                and status.duration is not None
                and status.category
                in (
                    StatusCategory.BUFF,
                    StatusCategory.HOT,
                    StatusCategory.SHIELD,
                )
            ):
                extra = float(src.passive.get("extend_positive_duration", 0))
                status.duration += extra
                status.remaining += extra
        status.on_apply()
        if state:
            if before_count >= 3:
                data = {
                    "attack_sum": self.current_stats.get("ad", 0)
                    + self.current_stats.get("ap", 0)
                }
                for u in state.player_combat_team + state.enemy_combat_team:
                    if (
                        u.is_alive
                        and u.trigger
                        and u.trigger.get("timing_type")
                        == TriggerTiming.STATUS_OVERLOAD
                        and u.is_enemy != self.is_enemy
                    ):
                        state.queue_trigger(
                            u,
                            TriggerTiming.STATUS_OVERLOAD,
                            event_target=self,
                            data=data,
                        )

    def _queue_status_removal(self, status: StatusEffect, reason: RemoveReason):
        self._pending_status_removals.append((status, reason))

    def clear_statuses(self, reason: RemoveReason):
        for name in list(self.statuses.keys()):
            for st in list(self.statuses[name]):
                if st.undispellable and reason in (
                    RemoveReason.BATTLE_END,
                    RemoveReason.HOST_DEAD,
                ):
                    continue  # 保留
                self._queue_status_removal(st, reason)
        # 立即处理
        self.process_statuses(0.0)

    def process_statuses(self, dt: float):
        """每帧/回合调用；驱动持续时间、tick、到期移除等"""
        for bucket in list(self.statuses.values()):
            for st in list(bucket):
                if st._update(dt):
                    self._queue_status_removal(st, RemoveReason.EXPIRED)
        # 处理需要在循环外移除的实例
        while self._pending_status_removals:
            st, reason = self._pending_status_removals.popleft()
            if st in self.statuses.get(st.name, []):
                self.statuses[st.name].remove(st)
                st.on_remove(reason)
            if not self.statuses.get(st.name):
                self.statuses.pop(st.name, None)

    # -----------------------------------------
    def _is_action_blocked(self) -> bool:
        """若至少存在一个 ActionDenialEffect，则本回合不能进行攻击/移动等。"""
        for bucket in self.statuses.values():
            for st in bucket:
                if st.blocks_action():
                    return True
        return False

    def _recalculate_stats(self, current_time: float):
        # FIX: Handle division by zero if max hp is 0
        old_max_hp = self.current_stats.get("hp", 0)
        hp_ratio = self.current_hp / old_max_hp if old_max_hp > 0 else 1.0

        temp_stats = self.base_stats.copy()
        percent_buffs = defaultdict(float)
        flat_buffs = defaultdict(float)

        # 装备静态加成
        for item in self.equipped_items:
            if not item:
                continue
            for stat, val in item.stats.items():
                if stat.endswith("_percent"):
                    percent_buffs[stat[:-8]] += val
                else:
                    flat_buffs[stat] += val

        # 状态效果加成
        for bucket in self.statuses.values():
            for st in bucket:
                if isinstance(st, StatModifierEffect):
                    key = st.params["stat"]
                    flat_buffs[key] += st.get_flat()
                    percent_buffs[key] += st.get_percent()

        for stat, value in flat_buffs.items():
            if stat in temp_stats:
                temp_stats[stat] += value
            elif stat not in temp_stats:
                temp_stats[stat] = value
        for key in ["hp", "ad", "as", "ap", "armor", "mr", "range"]:
            if key not in temp_stats:
                temp_stats[key] = self.base_stats.get(key, 0)
        for stat, percent in percent_buffs.items():
            if stat in temp_stats:
                # FIX: ensure base_stat exists for AS calculation
                base_stat_val = self.base_stats.get(stat, 0)
                if stat == "as" and percent < 0:
                    temp_stats[stat] *= 1 + percent / 100.0  # Slows
                elif stat == "as" and percent > 0:
                    temp_stats[stat] += base_stat_val * (
                        percent / 100.0
                    )  # AS increase based on base
                # Apply percent changes to the current value (after flat buffs)
                else:
                    temp_stats[stat] *= 1 + percent / 100.0
        temp_stats["as"] = max(0.1, temp_stats.get("as", 0.1))  # Cap AS slow
        print(temp_stats["as"])
        self.current_stats = temp_stats
        print(self.current_stats["as"])
        # FIX: Recalculate current HP based on new max HP
        new_max_hp = self.current_stats.get("hp", 0)
        self.current_hp = new_max_hp * hp_ratio
        self.current_hp = max(0.001, min(self.current_hp, new_max_hp))  # Clamp

    def reset_combat_state(self):
        self.remove_all_buffs()
        self.trigger_counts.clear()
        self._recalculate_stats(0)
        self.current_hp = self.current_stats.get("hp", 1)  # Use .get
        self.target = None
        self.attack_timer = 0.0
        self.trigger_timer = 0.0
        self.passive_timer = 0.0
        self.double_heal_uses = 0
        self.extra_attack_counters.clear()
        self.item_trigger_counts.clear()
        self.item_trigger_last_time.clear()
        self.revive_used = False
        self.is_alive = True
        self.x, self.y = 0.0, 0.0
        self.anim_state = AnimationState.IDLE
        self.anim_timer = random.uniform(0, 5)
        self.current_color_key = self.base_color_key
        self.timer_event_tally = 0
        self.timer_haste_multiplier = 1.0
        from ai.behaviors import BehaviorState

        self.behavior.state = BehaviorState.IDLE
        self._blocked_time = 0.0
        self.behavior.state = BehaviorState.IDLE
        self._blocked_time = 0.0
        # Re-apply module effects that only exist during combat
        for item in self.equipped_items:
            if not item or getattr(item, "item_type", None) != ItemType.MODULE:
                continue
            for stat, val in item.stats.items():
                self.add_stat_modifier(
                    stat,
                    val,
                    None,
                    item.id,
                    stat.endswith("_percent"),
                )
            if (
                item.ability
                and item.ability.get("effect_type") == AbilityEffect.APPLY_BUFF
            ):
                data = item.ability.get("effect_data", {})
                if "stat" in data and "value" in data:
                    self.add_stat_modifier(
                        data["stat"],
                        data["value"],
                        data.get("duration"),
                        item.id,
                        data.get("is_percent", False),
                    )

    def heal(
        self,
        amount: float,
        state: "GameState | None" = None,
        source: "Unit | None" = None,
        source_action: DamageSource = DamageSource.ITEM_ABILITY,
    ) -> float:
        if not self.is_alive or self.anim_state == AnimationState.DYING or amount <= 0:
            return 0
        # FIX: use .get for safety
        actual_heal = min(amount, self.current_stats.get("hp", 0) - self.current_hp)
        overheal = amount - actual_heal
        if self.passive and self.passive.get("overheal_to_shield") and overheal > 0:
            from engine.status_effects import ShieldEffect

            shield_list = self.statuses.get(ShieldEffect.name, [])
            if shield_list:
                shield = shield_list[0]
                shield.params["hp"] += overheal
                shield.params["accumulated"] += overheal
            else:
                shield = ShieldEffect(
                    host=self,
                    source_id=self.id + "_overheal",
                    duration=None,
                    params={"hp": overheal, "accumulated": overheal},
                )
                self.add_status(shield)
        if actual_heal > 0.1:  # FIX: Check meaningful heal
            self.current_hp += actual_heal
            self.anim_state = AnimationState.HEALED
            self.anim_timer = 0
            self.flash_color_key = "HEAL_FLASH_COLOR"
            if state and source:
                state.combat_stats.record_healing_done(
                    source, actual_heal, source_action
                )
                timing = source.trigger.get("timing_type") if source.trigger else None
                if timing == TriggerTiming.ON_HEAL:
                    source.heal_progress += actual_heal
                    threshold = source.trigger.get("timing_data", {}).get(
                        "threshold", 20
                    )
                    if source.heal_progress >= threshold:
                        source.heal_progress = 0.0
                        state.queue_trigger(
                            source,
                            TriggerTiming.ON_HEAL,
                            event_target=self,
                            data={"heal": actual_heal},
                        )
            if (
                state
                and self.trigger
                and self.trigger.get("timing_type") == TriggerTiming.ON_HEALED
            ):
                self.healed_progress += actual_heal
                threshold = self.trigger.get("timing_data", {}).get("threshold", 20)
                if self.healed_progress >= threshold:
                    self.healed_progress = 0.0
                    state.queue_trigger(
                        self,
                        TriggerTiming.ON_HEALED,
                        event_target=source,
                        data={"heal": actual_heal},
                    )
            if (
                self.passive
                and self.passive.get("revive_percent")
                and self.revive_used
                and self.current_hp >= self.current_stats.get("hp", 0)
            ):
                self.revive_used = False
        return actual_heal

    def _xs(self, key: str, default: float = 0.0) -> float:
        return self.current_stats.get(key, default)

    def compute_outgoing_damage(
        self,
        base_damage: float,
        dmg_type: DamageType,
        source_action: DamageSource,
        is_aoe: bool,
        target: "Unit",
    ) -> float:
        if base_damage <= 0 or not target:
            return 0.0
        self._last_outgoing_was_crit = False
        self._last_outgoing_missed = False
        # --- MISS / DODGE ---------------------------------------------------
        if source_action == DamageSource.BASIC_ATTACK:
            dodge = max(
                0.0,
                min(
                    95.0,
                    target._xs("dodge_chance", 5.0) - self._xs("accuracy", 0.0),
                ),
            )
            if random.random() < dodge / 100.0:
                self._last_outgoing_missed = True
                return 0.0  # 被闪避

            # --- CRIT -------------------------------------------------------
            if random.random() < self._xs("critical_chance", 5.0) / 100.0:
                base_damage *= self._xs("critical_damage", 150.0) / 100.0
                self._last_outgoing_was_crit = True

        base_damage *= self._xs("percentage_damage_bonus", 100.0) / 100.0

        base_damage += self._xs("flat_damage_bonus", 0.0)

        return max(0.0, base_damage)

    def _perform_line_attack(
        self,
        state: "GameState",
        angle: float,
        scatter_rad: float,
        length: float,
        width: float,
    ) -> tuple[float, list["Unit"]]:
        """Deal damage in a line with scatter and return total damage and hits."""
        angle += random.uniform(-scatter_rad, scatter_rad)
        pool = (
            state.enemy_combat_team if not self.is_enemy else state.player_combat_team
        )
        hits: list[Unit] = []
        for unit in pool:
            if not unit.is_alive or unit.anim_state == AnimationState.DYING:
                continue
            if unit.id == self.id:
                continue
            rel_x = unit.x - self.x
            rel_y = unit.y - self.y
            proj = rel_x * math.cos(angle) + rel_y * math.sin(angle)
            if proj < 0 or proj > length:
                continue
            perp = abs(-math.sin(angle) * rel_x + math.cos(angle) * rel_y)
            if perp <= width / 2 + unit.radius:
                hits.append(unit)

        damage_total = 0.0
        for target in hits:
            raw = self.current_stats.get("ad", 0)
            outgoing = self.compute_outgoing_damage(
                raw,
                DamageType.PHYSICAL,
                DamageSource.BASIC_ATTACK,
                True,
                target,
            )
            dmg = target.take_damage(
                outgoing,
                DamageType.PHYSICAL,
                state,
                self,
                source_action=DamageSource.BASIC_ATTACK,
                is_aoe=True,
                element=None,
            )
            self.apply_lifesteal(dmg, DamageType.PHYSICAL)
            damage_total += dmg
            if dmg > 0.1:
                if self._last_outgoing_was_crit:
                    text = f"{dmg:.0f}!"
                    color = "DAMAGE_CRIT_COLOR"
                else:
                    text = f"{dmg:.0f}"
                    color = "DAMAGE_PHYSICAL_COLOR"
                state.damage_floaters.append(
                    DamageFloater(target.x, target.y, text, color)
                )
            else:
                if self._last_outgoing_missed:
                    state.damage_floaters.append(
                        DamageFloater(target.x, target.y, "MISS", "BLACK")
                    )
            noble_proc = False
            for _bucket in self.statuses.values():
                for _st in _bucket:
                    if (
                        isinstance(_st, StatModifierEffect)
                        and _st.source_id == "SYNERGY_NOBLE"
                        and _st.params.get("stat") == "heal_on_hit"
                    ):
                        noble_proc = True
                        break
                if noble_proc:
                    break
            if noble_proc:
                healed = self.heal(10, state, self, DamageSource.ITEM_ABILITY)
                if healed > 0.1:
                    state.damage_floaters.append(
                        DamageFloater(self.x, self.y, f"+{healed:.0f}", "HEAL_COLOR")
                    )
                    state.visual_effects.append(
                        VisualEffect(
                            EffectType.HEAL_AURA,
                            self.x,
                            self.y,
                            HEAL_ANIM_DURATION,
                            "HEAL_COLOR",
                            size=self.radius,
                        )
                    )
        return damage_total, hits

    def _perform_cone_attack(
        self,
        state: "GameState",
        angle: float,
        arc_rad: float,
        length: float,
    ) -> tuple[float, list["Unit"]]:
        """Deal damage in a cone and split evenly across hits."""
        pool = (
            state.enemy_combat_team if not self.is_enemy else state.player_combat_team
        )
        hits: list[Unit] = []
        for unit in pool:
            if not unit.is_alive or unit.anim_state == AnimationState.DYING:
                continue
            if unit.id == self.id:
                continue
            dx = unit.x - self.x
            dy = unit.y - self.y
            dist = math.hypot(dx, dy)
            if dist > length or dist <= 0:
                continue
            ang = math.atan2(dy, dx)
            diff = (ang - angle + math.pi) % (2 * math.pi) - math.pi
            if abs(diff) <= arc_rad / 2 + math.asin(min(unit.radius / dist, 1.0)):
                hits.append(unit)

        damage_total = 0.0
        if hits:
            raw_each = self.current_stats.get("ad", 0) / len(hits)
        else:
            raw_each = 0.0
        for target in hits:
            outgoing = self.compute_outgoing_damage(
                raw_each,
                DamageType.PHYSICAL,
                DamageSource.BASIC_ATTACK,
                True,
                target,
            )
            dmg = target.take_damage(
                outgoing,
                DamageType.PHYSICAL,
                state,
                self,
                source_action=DamageSource.BASIC_ATTACK,
                is_aoe=True,
                element=None,
            )
            self.apply_lifesteal(dmg, DamageType.PHYSICAL)
            damage_total += dmg
            if dmg > 0.1:
                if self._last_outgoing_was_crit:
                    text = f"{dmg:.0f}!"
                    color = "DAMAGE_CRIT_COLOR"
                else:
                    text = f"{dmg:.0f}"
                    color = "DAMAGE_PHYSICAL_COLOR"
                state.damage_floaters.append(
                    DamageFloater(target.x, target.y, text, color)
                )
            else:
                if self._last_outgoing_missed:
                    state.damage_floaters.append(
                        DamageFloater(target.x, target.y, "MISS", "BLACK")
                    )
            noble_proc = False
            for _bucket in self.statuses.values():
                for _st in _bucket:
                    if (
                        isinstance(_st, StatModifierEffect)
                        and _st.source_id == "SYNERGY_NOBLE"
                        and _st.params.get("stat") == "heal_on_hit"
                    ):
                        noble_proc = True
                        break
                if noble_proc:
                    break
            if noble_proc:
                healed = self.heal(10, state, self, DamageSource.ITEM_ABILITY)
                if healed > 0.1:
                    state.damage_floaters.append(
                        DamageFloater(self.x, self.y, f"+{healed:.0f}", "HEAL_COLOR")
                    )
                    state.visual_effects.append(
                        VisualEffect(
                            EffectType.HEAL_AURA,
                            self.x,
                            self.y,
                            HEAL_ANIM_DURATION,
                            "HEAL_COLOR",
                            size=self.radius,
                        )
                    )
        return damage_total, hits

    def _perform_circle_attack(
        self,
        state: "GameState",
        radius: float,
    ) -> tuple[float, list["Unit"]]:
        """Deal damage in a circle around the unit."""
        pool = state.player_combat_team + state.enemy_combat_team
        hits: list[Unit] = []
        for unit in pool:
            if not unit.is_alive or unit.anim_state == AnimationState.DYING:
                continue
            dist_sq = (unit.x - self.x) ** 2 + (unit.y - self.y) ** 2
            if dist_sq <= (radius + unit.radius) ** 2:
                hits.append(unit)

        damage_total = 0.0
        for target in hits:
            raw = self.current_stats.get("ad", 0)
            outgoing = self.compute_outgoing_damage(
                raw,
                DamageType.PHYSICAL,
                DamageSource.BASIC_ATTACK,
                True,
                target,
            )
            dmg = target.take_damage(
                outgoing,
                DamageType.PHYSICAL,
                state,
                self,
                source_action=DamageSource.BASIC_ATTACK,
                is_aoe=True,
                element=None,
            )
            self.apply_lifesteal(dmg, DamageType.PHYSICAL)
            damage_total += dmg
            if dmg > 0.1:
                if self._last_outgoing_was_crit:
                    text = f"{dmg:.0f}!"
                    color = "DAMAGE_CRIT_COLOR"
                else:
                    text = f"{dmg:.0f}"
                    color = "DAMAGE_PHYSICAL_COLOR"
                state.damage_floaters.append(
                    DamageFloater(target.x, target.y, text, color)
                )
            else:
                if self._last_outgoing_missed:
                    state.damage_floaters.append(
                        DamageFloater(target.x, target.y, "MISS", "BLACK")
                    )
        return damage_total, hits

    def take_damage(
        self,
        damage: float,
        damage_type: DamageType,
        state: "GameState",
        source: Optional["Unit"],
        source_action: DamageSource = DamageSource.BASIC_ATTACK,
        is_aoe: bool = False,
        extra_flat_penetration: float = 0.0,
        extra_percent_penetration: float = 0.0,
        *,
        element: Element | None = None,
    ) -> float:

        if not self.is_alive or self.anim_state == AnimationState.DYING:
            return 0.0
        if damage <= 0:
            if source and getattr(source, "_last_outgoing_missed", False):
                self.on_dodge(source, state)
            return 0.0

        # ---- Elemental Aura & Reactions ----
        if element is not None:
            existing = None
            for st in self.statuses.get(ElementalAura.name, []):
                if isinstance(st, ElementalAura):
                    existing = st
                    break
            reaction_multiplier = 1.0
            if existing is None:
                aura = ElementalAura(self, self.id, element)
                self.add_status(aura)
            else:
                prev_elem: Element = existing.params.get("element")
                self._queue_status_removal(existing, RemoveReason.CUSTOM_TRIGGER)
                self.process_statuses(0.0)
                pair = {prev_elem, element}
                if prev_elem == element == Element.ICE:
                    if not self.statuses.get(ChillDebuff.name):
                        self.add_status(ChillDebuff(self, self.id))
                elif prev_elem == element == Element.FIRE:
                    if not self.statuses.get(IgniteDebuff.name):
                        self.add_status(IgniteDebuff(self, self.id))
                elif prev_elem == element == Element.LIGHTNING:
                    if not self.statuses.get(ShockDebuff.name):
                        self.add_status(ShockDebuff(self, self.id))
                elif pair == {Element.LIGHTNING, Element.FIRE}:
                    if state:
                        aoe = self.current_stats.get("hp", 0) * 0.1
                        units = state.player_combat_team + state.enemy_combat_team
                        radius_sq = (COMBAT_UNIT_RADIUS * 2) ** 2
                        for u in units:
                            if not u.is_alive:
                                continue
                            dx = u.x - self.x
                            dy = u.y - self.y
                            if dx * dx + dy * dy <= radius_sq:
                                u.take_damage(
                                    aoe,
                                    DamageType.MAGIC,
                                    state,
                                    source,
                                    source_action=DamageSource.ITEM_ABILITY,
                                    is_aoe=True,
                                    element=None,
                                )
                elif pair == {Element.ICE, Element.FIRE}:
                    reaction_multiplier = 2.0
                elif pair == {Element.ICE, Element.LIGHTNING}:
                    if not self.statuses.get(SuperconductDebuff.name):
                        self.add_status(SuperconductDebuff(self, self.id))
                damage *= reaction_multiplier

        # 先让可拦截的状态（护盾等）修改伤害
        for _bucket in self.statuses.values():
            for _st in _bucket:
                damage = _st.intercept_incoming_damage(damage)
                if damage <= 0:
                    return 0.0

        damage *= self._xs("percentage_damage_reduction", 100.0) / 100.0

        resistance = 0.0
        if damage_type == DamageType.PHYSICAL:
            resistance = self.current_stats.get("armor", 0.0)
            if source:
                resistance -= source._xs("flat_physical_penetration", 0.0)
                resistance *= (
                    1.0 - source._xs("percentage_physical_penetration", 0.0) / 100.0
                )
            resistance -= extra_flat_penetration
            resistance *= 1.0 - extra_percent_penetration / 100.0
        elif damage_type == DamageType.MAGIC:
            resistance = self.current_stats.get("mr", 0.0)
            if source:
                resistance -= source._xs("flat_magic_penetration", 0.0)
                resistance *= (
                    1.0 - source._xs("percentage_magic_penetration", 0.0) / 100.0
                )
            resistance -= extra_flat_penetration
            resistance *= 1.0 - extra_percent_penetration / 100.0
        dmg_mul = 1.0
        if damage_type != DamageType.TRUE:
            if resistance >= 0:
                dmg_mul = 100.0 / (100.0 + resistance)
            elif resistance > -100:
                dmg_mul = 2.0 - 100.0 / (100.0 - resistance)
            else:
                dmg_mul = 2.0
        damage *= dmg_mul

        damage -= self._xs("flat_damage_reduction", 0.0)
        if source_action == DamageSource.BASIC_ATTACK:
            damage -= self._xs("flat_basic_attack_damage_reduction", 0.0)
        if damage <= 0.0:
            return 0.0

        effective_damage = damage
        if effective_damage > 0.1:
            self.anim_state = AnimationState.HIT
            self.anim_timer = 0
            self.flash_color_key = "HIT_FLASH_COLOR"
            if state:
                state.visual_effects.append(
                    VisualEffect(
                        EffectType.HIT_SPARK,
                        self.x,
                        self.y,
                        0.3,
                        "HIT_SPARK_COLOR",
                        size=self.radius * 1.2,
                    )
                )
        if state and self.passive and self.passive.get("bleed_storage_percent"):
            ratio = self.passive.get("bleed_storage_percent", 50) / 100.0
            effective_damage *= 1 - ratio
        self.current_hp -= effective_damage
        died = self.current_hp <= 0

        if state and self.passive and self.passive.get("bleed_storage_percent"):
            converted = effective_damage
            from engine.enums import StackRule
            from engine.status_effects import BleedingEffect

            bucket = self.statuses.get(BleedingEffect.name, [])
            if bucket:
                bleed = bucket[0]
                remaining = bleed.params.get("damage", 0) * (bleed.remaining or 0)
                total = remaining + converted
                bleed.params["damage"] = total / 20.0
                bleed.duration = bleed.remaining = 20.0
            else:
                bleed = BleedingEffect(
                    host=self,
                    source_id=self.id,
                    duration=20.0,
                    stack_rule=StackRule.UNIQUE,
                    params={"damage": converted / 20.0, "dtype": DamageType.TRUE},
                )
                self.add_status(bleed)
        if (
            not died
            and self.passive
            and self.passive.get("accuracy_counter_debuff")
            and state
        ):
            info = self.passive["accuracy_counter_debuff"]
            val = info.get("value", -25)
            dur = info.get("duration", 3.0)
            self.add_stat_modifier(
                "accuracy",
                val,
                dur,
                "ACC_COUNTER_DEBUFF",
                False,
            )
            if source:
                source.add_stat_modifier(
                    "accuracy",
                    val,
                    dur,
                    "ACC_COUNTER_DEBUFF",
                    False,
                )

        if (
            self.trigger
            and self.trigger.get("timing_type") == TriggerTiming.TIMED
            and self.trigger.get("timing_data", {}).get("accelerate_on_hit")
        ):
            self.trigger_timer += self.trigger.get("timing_data", {}).get(
                "accelerate_on_hit", 0.0
            )
        if state:
            state.combat_stats.record_damage_taken(
                self, effective_damage, source_action
            )
            if source:
                state.combat_stats.record_damage_dealt(
                    source, effective_damage, source_action
                )
                state.record_team_damage(source, effective_damage)
                if (
                    source_action == DamageSource.BASIC_ATTACK
                    and self.current_stats.get("range", 50) >= 80
                ):
                    allies = (
                        state.player_combat_team
                        if not self.is_enemy
                        else state.enemy_combat_team
                    )
                    for ally in allies:
                        if (
                            ally.is_alive
                            and ally.id != self.id
                            and ally.trigger
                            and ally.trigger.get("timing_type")
                            == TriggerTiming.ON_ALLY_HIT
                        ):
                            state.queue_trigger(
                                ally,
                                TriggerTiming.ON_ALLY_HIT,
                                event_target=source,
                                data={},
                            )
                timing = source.trigger.get("timing_type") if source.trigger else None
                if timing:
                    progress_attr = None
                    if (
                        timing == TriggerTiming.ON_MAGIC_DAMAGE
                        and damage_type == DamageType.MAGIC
                    ):
                        progress_attr = "magic_damage_progress"
                    elif (
                        timing == TriggerTiming.ON_PHYSICAL_DAMAGE
                        and damage_type == DamageType.PHYSICAL
                    ):
                        progress_attr = "physical_damage_progress"
                    elif timing == TriggerTiming.ON_DAMAGE:
                        progress_attr = "damage_progress"
                    if progress_attr:
                        setattr(
                            source,
                            progress_attr,
                            getattr(source, progress_attr) + effective_damage,
                        )
                        threshold = source.trigger.get("timing_data", {}).get(
                            "threshold", 20
                        )
                        if getattr(source, progress_attr) >= threshold:
                            total = getattr(source, progress_attr)
                            setattr(source, progress_attr, 0.0)
                            state.queue_trigger(
                                source,
                                timing,
                                event_target=self,
                                data={"damage": total},
                            )
        if (
            state
            and self.trigger
            and self.trigger["timing_type"] == TriggerTiming.ON_TAKE_DAMAGE
        ):
            state.queue_trigger(
                self,
                TriggerTiming.ON_TAKE_DAMAGE,
                event_target=source,
                data={"damage": effective_damage},
            )
        if (
            state
            and self.trigger
            and self.trigger["timing_type"] == TriggerTiming.ON_DAMAGE_TAKEN
        ):
            self.damage_taken_progress += effective_damage
            threshold = self.trigger.get("timing_data", {}).get("threshold", 20)
            if self.damage_taken_progress >= threshold:
                self.damage_taken_progress = 0.0
                state.queue_trigger(
                    self,
                    TriggerTiming.ON_DAMAGE_TAKEN,
                    event_target=source,
                    data={"damage": effective_damage},
                )
        if (
            state
            and self.trigger
            and self.trigger["timing_type"] == TriggerTiming.ON_AOE_DAMAGE
            and is_aoe
        ):
            angle = math.atan2(source.y - self.y, source.x - self.x) if source else 0.0
            radius = self.trigger.get("radius", 100)
            pool = state.player_combat_team + state.enemy_combat_team
            targets = []
            for unit in pool:
                if (
                    not unit.is_alive
                    or unit.anim_state == AnimationState.DYING
                    or unit.id == self.id
                ):
                    continue
                dx = unit.x - self.x
                dy = unit.y - self.y
                dist = math.hypot(dx, dy)
                if dist > radius:
                    continue
                diff = (math.atan2(dy, dx) - angle + math.pi) % (2 * math.pi) - math.pi
                if abs(diff) <= math.pi / 2:
                    targets.append(unit)
            state.queue_trigger(
                self,
                TriggerTiming.ON_AOE_DAMAGE,
                event_target=targets,
                data={"damage": effective_damage, "is_aoe": True},
            )
        if (
            state
            and self.passive
            and self.passive["timing_type"] == TriggerTiming.ON_TAKE_DAMAGE
            and resolve_passive_func
        ):
            resolve_passive_func(
                self,
                TriggerTiming.ON_TAKE_DAMAGE,
                state,
                event_target=source,
                event_data={"damage": effective_damage},
            )
        if self.current_hp <= 0:
            self.current_hp = 0
            self.is_alive = False
            self.anim_state = AnimationState.DYING
            self.anim_timer = 0
            # 死亡时移除可消散状态
            self.clear_statuses(RemoveReason.HOST_DEAD)
            if state:
                state.visual_effects.append(
                    VisualEffect(
                        EffectType.DEATH_EFFECT,
                        self.x,
                        self.y,
                        DEATH_ANIM_DURATION,
                        "DEATH_COLOR",
                        size=self.radius,
                    )
                )
                if (
                    self.trigger
                    and self.trigger["timing_type"] == TriggerTiming.ON_DEATH
                ):
                    state.queue_trigger(
                        self,
                        TriggerTiming.ON_DEATH,
                        event_target=source,
                        data={"damage": effective_damage},
                    )
                if (
                    self.passive
                    and self.passive["timing_type"] == TriggerTiming.ON_DEATH
                    and resolve_passive_func
                ):
                    resolve_passive_func(
                        self,
                        TriggerTiming.ON_DEATH,
                        state,
                        event_target=source,
                        event_data={"damage": effective_damage},
                    )
                living = [
                    u
                    for u in state.player_combat_team + state.enemy_combat_team
                    if u.is_alive
                ]
                target_unit = source if source and source.is_alive else None
                for u in living:
                    if (
                        u.trigger
                        and u.trigger.get("timing_type") == TriggerTiming.ON_ANY_DEATH
                    ):
                        count = u.trigger_counts[TriggerTiming.ON_ANY_DEATH]
                        state.queue_trigger(
                            u,
                            TriggerTiming.ON_ANY_DEATH,
                            event_target=target_unit,
                            data={
                                "value": 100 * count,
                                "dead_unit_ad": self.current_stats.get("ad", 0),
                                "dead_unit_hp": self.current_stats.get("hp", 0),
                                "source_unit": source,
                            },
                        )
                        u.trigger_counts[TriggerTiming.ON_ANY_DEATH] += 1
                    if (
                        u.passive
                        and u.passive.get("timing_type") == TriggerTiming.ON_ANY_DEATH
                        and resolve_passive_func
                    ):
                        resolve_passive_func(
                            u,
                            TriggerTiming.ON_ANY_DEATH,
                            state,
                            event_target=target_unit,
                            event_data={
                                "value": 100 * count,
                                "dead_unit_ad": self.current_stats.get("ad", 0),
                                "dead_unit_hp": self.current_stats.get("hp", 0),
                                "source_unit": source,
                            },
                        )
                if (
                    self.passive
                    and self.passive.get("revive_percent")
                    and not self.revive_used
                ):
                    self.revive_used = True
                    self.current_hp = (
                        self.current_stats.get("hp", 0)
                        * self.passive.get("revive_percent", 0)
                        / 100.0
                    )
                    self.is_alive = True
                    self.anim_state = AnimationState.HEALED
                    self.anim_timer = 0
                    self.flash_color_key = "HEAL_FLASH_COLOR"
            for u in state.player_combat_team + state.enemy_combat_team:
                u.remove_buffs_from_source(self.id)
        return effective_damage

    def apply_lifesteal(
        self, dealt: float, dmg_type: DamageType, state: "GameState | None" = None
    ):
        heal_amount = 0.0
        if dealt <= 0:
            return
        if dmg_type == DamageType.PHYSICAL:
            heal_amount += dealt * self._xs("physical_lifesteal", 0.0) / 100.0
        if dmg_type == DamageType.MAGIC:
            heal_amount += dealt * self._xs("spell_lifesteal", 0.0) / 100.0
        heal_amount += dealt * self._xs("omnivamp", 0.0) / 100.0

        if heal_amount <= 0:
            return

        heal_amount *= self._xs("outgoing_healing_bonus", 100.0) / 100.0
        heal_amount *= self._xs("incoming_healing_bonus", 100.0) / 100.0
        self.heal(heal_amount, state, self, DamageSource.BASIC_ATTACK)

    def on_deal_magic_damage(self, target: "Unit", state: "GameState") -> None:
        for item in self.equipped_items:
            if item and getattr(item, "special", None) == "poison_on_magic":
                from engine.status_effects import DamageOverTime

                dot = DamageOverTime(
                    host=target,
                    source_id=self.id,
                    duration=5.0,
                    params={"damage": 4, "dtype": DamageType.TRUE},
                )
                target.add_status(dot)
                break

    def on_dodge(self, attacker: "Unit", state: "GameState") -> None:
        for item in self.equipped_items:
            if item and getattr(item, "special", None) == "counter_on_dodge":
                saved = self.target
                self.target = attacker
                self.attack_target(state)
                self.target = saved
                break

    def find_nearest_target(self, potential_targets: List["Unit"]):
        nearest_target = None
        min_dist_sq = float("inf")
        alive_targets = [
            t
            for t in potential_targets
            if t.is_alive and t.anim_state != AnimationState.DYING and t.id != self.id
        ]
        if not alive_targets:
            self.target = None
            return
        for target in alive_targets:
            dist_sq = (self.x - target.x) ** 2 + (self.y - target.y) ** 2
            if dist_sq < min_dist_sq:
                min_dist_sq = dist_sq
                nearest_target = target
        self.target = nearest_target

    def move_towards_target(self, move_speed: float):
        if (
            not self.target
            or not self.target.is_alive
            or self.anim_state == AnimationState.DYING
        ):
            return
        dx = self.target.x - self.x
        dy = self.target.y - self.y
        dist = math.sqrt(dx**2 + dy**2)
        range_dist = self.current_stats.get("range", 50)  # FIX: .get
        stop_dist = max(range_dist, self.radius + self.target.radius + 2)
        if dist <= stop_dist:
            return
        if dist > 0:
            # FIX: prevent overshooting too much
            move_dist = min(dist - stop_dist * 0.8, move_speed)  # Stop slightly earlier
            if move_dist > 0:
                self.x += (dx / dist) * move_dist
                self.y += (dy / dist) * move_dist

    def attack_target(self, state: "GameState") -> float:
        if (
            not self.target
            or not self.target.is_alive
            or self.anim_state == AnimationState.DYING
        ):
            return 0
        damage_dealt = 0.0
        dx = self.target.x - self.x
        dy = self.target.y - self.y
        dist = math.sqrt(dx**2 + dy**2)
        # FIX: .get
        effective_range = max(
            self.current_stats.get("range", 50), self.radius + self.target.radius + 5
        )
        if dist <= effective_range:
            self.attack_timer += state.delta_time_combat
            # FIX: use .get
#            print(self.current_stats.get("as",9999))
            attack_interval = 1.0 / max(0.1, self.current_stats.get("as", 0.5))
            # FIX: Allow multiple attacks if timer accumulates a lot (e.g. lag)
            while self.attack_timer >= attack_interval:
                self.attack_timer -= attack_interval
                self.anim_state = AnimationState.ATTACKING
                self.anim_timer = 0
                target_pos = (self.target.x, self.target.y)
                # Check target still alive after potential effects from previous loop iter
                if not self.target or not self.target.is_alive:
                    break
                angle = math.atan2(dy, dx)
                if self.passive and self.passive.get("line_attack"):
                    scatter = math.radians(self.passive.get("scatter_deg", 0))
                    width = self.passive.get("line_width", 20)
                    length = self.passive.get("line_length", 1000)
                    dmg, hits = self._perform_line_attack(
                        state, angle, scatter, length, width
                    )
                    damage_dealt += dmg
                    chain_hits = hits
                elif self.passive and self.passive.get("cone_attack"):
                    arc = math.radians(self.passive.get("cone_arc_deg", 60))
                    length = self.passive.get("cone_length", 100)
                    dmg, hits = self._perform_cone_attack(state, angle, arc, length)
                    damage_dealt += dmg
                    chain_hits = hits
                elif self.passive and self.passive.get("circle_attack"):
                    radius = self.passive.get("circle_radius", 80)
                    dmg, hits = self._perform_circle_attack(state, radius)
                    damage_dealt += dmg
                    chain_hits = hits
                else:
                    is_melee = self.current_stats.get("range", 50) < 80
                    if is_melee:
                        slash_x = self.x + math.cos(angle) * (dist - self.target.radius)
                        slash_y = self.y + math.sin(angle) * (dist - self.target.radius)
                        state.visual_effects.append(
                            VisualEffect(
                                EffectType.SLASH,
                                slash_x,
                                slash_y,
                                0.2,
                                "SLASH_COLOR",
                                target_pos=target_pos,
                                size=self.radius * 1.5,
                                angle=angle,
                            )
                        )
                    else:
                        state.visual_effects.append(
                            VisualEffect(
                                EffectType.PROJECTILE_BASIC,
                                self.x,
                                self.y,
                                1.0,
                                "PROJECTILE_BASIC_COLOR",
                                target_pos=target_pos,
                                size=4,
                            )
                        )

                    raw = self.current_stats.get("ad", 0)
                    outgoing = self.compute_outgoing_damage(
                        raw,
                        DamageType.PHYSICAL,
                        DamageSource.BASIC_ATTACK,
                        False,
                        self.target,
                    )
                    if self.passive and self.passive.get("burning_attack"):
                        from engine.status_effects import BurningDOT

                        dot_damage = outgoing * 0.1
                        bucket = self.target.statuses.get(BurningDOT.name, [])
                        same_source = [
                            st
                            for st in bucket
                            if isinstance(st, BurningDOT) and st.source_id == self.id
                        ]
                        if len(same_source) < 10:
                            dot = BurningDOT(
                                host=self.target,
                                source_id=self.id,
                                duration=None,
                                params={
                                    "damage": dot_damage,
                                    "dtype": DamageType.PHYSICAL,
                                },
                            )
                            self.target.add_status(dot)
                        current_attack_damage = 0.0
                    else:
                        current_attack_damage = self.target.take_damage(
                            outgoing,
                            DamageType.PHYSICAL,
                            state,
                            self,
                            source_action=DamageSource.BASIC_ATTACK,
                            is_aoe=False,
                            element=None,
                        )
                        self.apply_lifesteal(current_attack_damage, DamageType.PHYSICAL)
                        damage_dealt += current_attack_damage
                    chain_hits = [self.target]
                if self.passive and self.passive.get("chain_bounces"):
                    last = self.target
                    for _ in range(self.passive.get("chain_bounces", 0)):
                        pool = (
                            state.enemy_combat_team
                            if not self.is_enemy
                            else state.player_combat_team
                        )
                        candidates = [
                            u for u in pool if u.is_alive and u not in chain_hits
                        ]
                        if not candidates:
                            break
                        next_t = min(
                            candidates,
                            key=lambda u: (u.x - last.x) ** 2 + (u.y - last.y) ** 2,
                        )
                        out = self.compute_outgoing_damage(
                            raw,
                            DamageType.PHYSICAL,
                            DamageSource.BASIC_ATTACK,
                            False,
                            next_t,
                        )
                        dmg = next_t.take_damage(
                            out,
                            DamageType.PHYSICAL,
                            state,
                            self,
                            source_action=DamageSource.BASIC_ATTACK,
                            is_aoe=False,
                            element=None,
                        )
                        self.apply_lifesteal(dmg, DamageType.PHYSICAL)
                        damage_dealt += dmg
                        if dmg > 0.1:
                            state.damage_floaters.append(
                                DamageFloater(
                                    next_t.x,
                                    next_t.y,
                                    f"{dmg:.0f}",
                                    "DAMAGE_PHYSICAL_COLOR",
                                )
                            )
                        chain_hits.append(next_t)
                        last = next_t
                if not (
                    self.passive
                    and (
                        self.passive.get("line_attack")
                        or self.passive.get("cone_attack")
                        or self.passive.get("circle_attack")
                    )
                ):
                    # FIX: only create floater if damage > 0
                    if current_attack_damage > 0.1:
                        if self._last_outgoing_was_crit:
                            floater_text = f"{current_attack_damage:.0f}!"
                            floater_color = "DAMAGE_CRIT_COLOR"
                        else:
                            floater_text = f"{current_attack_damage:.0f}"
                            floater_color = "DAMAGE_PHYSICAL_COLOR"
                        state.damage_floaters.append(
                            DamageFloater(
                                self.target.x,
                                self.target.y,
                                floater_text,
                                floater_color,
                            )
                        )
                    else:
                        if self._last_outgoing_missed:
                            state.damage_floaters.append(
                                DamageFloater(
                                    self.target.x,
                                    self.target.y,
                                    "MISS",
                                    "BLACK",
                                )
                            )
                    noble_proc = False
                    for _bucket in self.statuses.values():
                        for _st in _bucket:
                            if (
                                isinstance(_st, StatModifierEffect)
                                and _st.source_id == "SYNERGY_NOBLE"
                                and _st.params.get("stat") == "heal_on_hit"
                            ):
                                noble_proc = True
                                break
                        if noble_proc:
                            break
                    if noble_proc:
                        healed = self.heal(10, state, self, DamageSource.ITEM_ABILITY)
                        if healed > 0.1:  # FIX: check meaningful heal
                            state.damage_floaters.append(
                                DamageFloater(
                                    self.x, self.y, f"+{healed:.0f}", "HEAL_COLOR"
                                )
                            )
                            state.visual_effects.append(
                                VisualEffect(
                                    EffectType.HEAL_AURA,
                                    self.x,
                                    self.y,
                                    HEAL_ANIM_DURATION,
                                    "HEAL_COLOR",
                                    size=self.radius,
                                )
                            )
                # FIX: Call resolve_trigger_func with keyword argument
                data = {}
                if self.trigger and self.trigger["timing_type"] == TriggerTiming.ON_HIT:
                    ev_tgt = (
                        chain_hits
                        if self.trigger.get("target_type")
                        in (
                            TriggerTarget.EVENT_TARGETS,
                            TriggerTarget.SELF_AND_EVENT_TARGETS,
                        )
                        else self.target
                    )
                    aoe_flag = (
                        True
                        if self.passive
                        and (
                            self.passive.get("line_attack")
                            or self.passive.get("cone_attack")
                            or self.passive.get("circle_attack")
                        )
                        else len(chain_hits) > 1
                    )
                    data = {"aoe": aoe_flag}
                    if self.target:
                        data["missing_hp"] = (
                            self.target.current_stats.get("hp", 0)
                            - self.target.current_hp
                        )
                    if self.passive and self.passive.get("cone_attack"):
                        data["value"] = self.current_stats.get("ad", 0) / max(
                            len(chain_hits), 1
                        )
                    state.queue_trigger(
                        self,
                        TriggerTiming.ON_HIT,
                        event_target=ev_tgt,
                        data=data,
                    )
                if (
                    self.passive
                    and self.passive["timing_type"] == TriggerTiming.ON_HIT
                    and resolve_passive_func
                ):
                    resolve_passive_func(
                        self,
                        TriggerTiming.ON_HIT,
                        state,
                        event_target=self.target,
                        event_data=data,
                    )
        return damage_dealt

    def combat_update(self, potential_targets: List["Unit"], state: "GameState"):
        """Overridden: delegate high‑level decisions to AI behaviour tree."""
        # 1) keep legacy animations
        self.update_animation(state.delta_time_combat)
        dt = state.delta_time_combat * getattr(self, "timer_haste_multiplier", 1.0)
        # 2) still run timed triggers exactly as before (no change)
        if self.trigger and self.trigger["timing_type"] == TriggerTiming.TIMED:
            interval = self.trigger.get("timing_data", {}).get("interval", 999.0)
            accel_pct = self.trigger.get("timing_data", {}).get(
                "accelerate_per_negative", 0.0
            )
            speed = 1.0
            if accel_pct:
                from engine.enums import StatusCategory

                all_units = state.player_combat_team + state.enemy_combat_team
                neg_count = 0
                for u in all_units:
                    for bucket in u.statuses.values():
                        neg_count += sum(
                            1
                            for st in bucket
                            if st.category
                            in (
                                StatusCategory.DEBUFF,
                                StatusCategory.DOT,
                                StatusCategory.ACTION_BLOCK,
                            )
                        )
                speed += accel_pct * neg_count
            accel_tally = self.trigger.get("timing_data", {}).get(
                "accelerate_per_tally"
            )
            if accel_tally:
                speed += accel_tally * getattr(self, "timer_event_tally", 0)
            self.trigger_timer += dt * speed
            while self.trigger_timer >= interval and interval > 0:
                target = None
                t_type = self.trigger.get("target_type")
                if t_type == TriggerTarget.NEAREST_ALLY:
                    threshold = self.trigger.get("hp_threshold", 1.0)
                    pool = (
                        state.player_combat_team
                        if not self.is_enemy
                        else state.enemy_combat_team
                    )
                    candidates = [
                        u
                        for u in pool
                        if u.is_alive
                        and u.anim_state != AnimationState.DYING
                        and u.current_stats.get("hp", 0) > 0
                        and u.current_hp / u.current_stats["hp"] < threshold
                    ]
                    if not candidates:
                        break
                    target = min(
                        candidates,
                        key=lambda u: (u.x - self.x) ** 2 + (u.y - self.y) ** 2,
                    )
                elif t_type == TriggerTarget.ALL_NEGATIVE_ENEMIES:
                    from engine.enums import StatusCategory

                    pool = (
                        state.enemy_combat_team
                        if not self.is_enemy
                        else state.player_combat_team
                    )
                    target = [
                        u
                        for u in pool
                        if u.is_alive
                        and any(
                            st.category
                            in (
                                StatusCategory.DEBUFF,
                                StatusCategory.DOT,
                                StatusCategory.ACTION_BLOCK,
                            )
                            for bucket in u.statuses.values()
                            for st in bucket
                        )
                    ]
                self.trigger_timer -= interval
                state.queue_trigger(
                    self, TriggerTiming.TIMED, event_target=target, data={}
                )
        if (
            self.passive
            and self.passive["timing_type"] == TriggerTiming.TIMED
            and resolve_passive_func
        ):
            self.passive_timer += dt
            interval = self.passive.get("timing_data", {}).get("interval", 999.0)
            while self.passive_timer >= interval and interval > 0:
                self.passive_timer -= interval
                resolve_passive_func(
                    self,
                    TriggerTiming.TIMED,
                    state,
                    event_target=None,
                    event_data={},
                )
        if self.trigger and "all_allies_below_hp" in self.trigger:
            threshold = self.trigger.get("all_allies_below_hp", 1.0)
            pool = (
                state.player_combat_team
                if not self.is_enemy
                else state.enemy_combat_team
            )
            allies = [
                u for u in pool if u.is_alive and u.anim_state != AnimationState.DYING
            ]
            if allies:
                below = [
                    u
                    for u in allies
                    if u.current_stats.get("hp", 0) > 0
                    and u.current_hp / u.current_stats["hp"] < threshold
                ]
                if len(below) == len(allies) and not self._allies_low_triggered:
                    targets = [u for u in allies if u.id != self.id]
                    state.queue_trigger(
                        self,
                        self.trigger.get("timing_type", TriggerTiming.TIMED),
                        event_target=targets,
                        data={},
                    )
                    self._allies_low_triggered = True
                elif len(below) != len(allies):
                    self._allies_low_triggered = False
        # 3) hand the rest to behaviour context (handles blocking / kiting / attack etc.)
        saved_dt = state.delta_time_combat
        state.delta_time_combat = dt
        self.behavior.update(potential_targets, state)
        state.delta_time_combat = saved_dt

    def update_animation(self, dt: float):
        from engine.utils import clamp

        self.anim_timer += dt
        self.rotation_offset = 0.0

        if self.anim_state == AnimationState.IDLE:
            self.current_color_key = self.base_color_key
            self.rotation_offset = (
                math.sin(self.anim_timer * IDLE_WOBBLE_SPEED) * IDLE_WOBBLE_ANGLE
            )
        elif self.anim_state == AnimationState.ATTACKING:
            progress = clamp(self.anim_timer / ATTACK_ANIM_DURATION, 0, 1)
            self.current_color_key = self.base_color_key
            self.rotation_offset = math.sin(progress * math.pi) * ATTACK_LUNGE_ANGLE
            if progress >= 1.0:
                self.anim_state = AnimationState.IDLE
        elif self.anim_state == AnimationState.HIT:
            progress = clamp(self.anim_timer / HIT_ANIM_DURATION, 0, 1)
            # UI will lerp color: self.color = lerp_color(self.flash_color, self.base_color, progress)
            self.rotation_offset = math.sin(progress * math.pi) * HIT_RECOIL_ANGLE
            if progress >= 1.0:
                self.anim_state = AnimationState.IDLE
                self.current_color_key = self.base_color_key
        elif self.anim_state in [AnimationState.HEALED, AnimationState.CASTING]:
            duration = (
                HEAL_ANIM_DURATION
                if self.anim_state == AnimationState.HEALED
                else CAST_ANIM_DURATION
            )
            progress = clamp(self.anim_timer / duration, 0, 1)
            # UI will lerp color: self.color = lerp_color(self.flash_color, self.base_color, progress)
            if progress >= 1.0:
                self.anim_state = AnimationState.IDLE
                self.current_color_key = self.base_color_key
        elif self.anim_state == AnimationState.DYING:
            progress = clamp(self.anim_timer / DEATH_ANIM_DURATION, 0, 1)
            # UI lerps color and size

    # draw_combat method moved to ui/


class Player:
    def __init__(self):
        self.health: int = STARTING_HEALTH
        self.gold: int = 0
        from data.constants import STARTING_CRYSTAL, STARTING_MATERIALS

        self.materials: dict[str, int] = STARTING_MATERIALS.copy()
        self.crystals: int = STARTING_CRYSTAL
        self.level: int = 1
        self.xp: int = 0
        self.bench: List[Optional[Unit]] = [None] * BENCH_SLOTS
        self.board: Dict[Tuple[int, int], Optional[Unit]] = {}
        self.active_synergies: "SynergyStatus" = {}
        self.item_inventory: List[Item] = []
        self.artifacts: List[Artifact] = []
        self._init_board()

    def _init_board(self):
        for r in range(BOARD_ROWS):
            for c in range(BOARD_COLS):
                self.board[(r, c)] = None

    def xp_to_next_level(self) -> int:
        if self.level >= MAX_LEVEL:
            return 0
        # FIX: Access XP_PER_LEVEL safely
        return XP_PER_LEVEL[self.level] if self.level < len(XP_PER_LEVEL) else 999

    def gain_xp(self, amount: int):
        if self.level >= MAX_LEVEL:
            return
        self.xp += amount
        # FIX: Check index safety
        while (
            self.level < MAX_LEVEL
            and self.level < len(XP_PER_LEVEL)
            and self.xp >= self.xp_to_next_level()
        ):
            self.xp -= self.xp_to_next_level()
            self.level += 1
            print(f"DEBUG: Player leveled up to {self.level}!")

    def can_pay_materials(self, bundle: dict[str, int]) -> bool:
        return all(self.materials.get(k, 0) >= v for k, v in bundle.items())

    def pay_materials(self, bundle: dict[str, int]):
        for k, v in bundle.items():
            self.materials[k] = max(0, self.materials.get(k, 0) - v)

    def get_all_units(self) -> List[Unit]:
        units = [u for u in self.bench if u]
        units.extend([u for u in self.board.values() if u])
        return units

    def get_board_units(self) -> List[Unit]:
        return [u for u in self.board.values() if u]

    def has_artifact(self, artifact_type: str) -> List[Artifact]:
        return [a for a in self.artifacts if a.type == artifact_type]


class Shop:
    def __init__(self):
        self.pool: Dict[str, int] = self._initialize_pool()
        self.slots: List[Optional[Unit]] = [None] * SHOP_SLOTS

    def _initialize_pool(self) -> Dict[str, int]:
        pool = {}
        for name, definition in UNIT_DEFINITIONS.items():
            rarity = definition["rarity"]
            if rarity in UNIT_POOL_SIZE_MULTIPLIER:
                pool[name] = UNIT_POOL_SIZE_MULTIPLIER[rarity]
        return pool

    def refresh(self, player_level: int):
        for unit in self.slots:
            if unit:
                self.return_to_pool(unit.name)
        self.slots = [None] * SHOP_SLOTS
        probabilities = LEVEL_PROBABILITIES.get(player_level, LEVEL_PROBABILITIES[1])
        rarities_available = [
            r for r, prob in zip(RARITY_ORDER, probabilities) if prob > 0
        ]
        weights = [prob for prob in probabilities if prob > 0]
        if not rarities_available or sum(weights) == 0:
            return  # FIX: check weights sum

        for i in range(SHOP_SLOTS):
            if sum(self.pool.values()) == 0:
                break
            try:  # FIX: handle empty sequences in random.choices/choice
                chosen_rarity = random.choices(
                    rarities_available, weights=weights, k=1
                )[0]
            except IndexError:
                continue
            units_of_rarity = [
                n
                for n, count in self.pool.items()
                if count > 0
                and UNIT_DEFINITIONS.get(n, {}).get("rarity") == chosen_rarity
            ]
            chosen_unit_name = None
            if not units_of_rarity:
                # FIX: Fallback logic if a rarity has 0 units left
                available_units = [
                    n
                    for n, count in self.pool.items()
                    if count > 0
                    and UNIT_DEFINITIONS.get(n, {}).get("rarity") in rarities_available
                ]
                if not available_units:
                    continue
                try:
                    chosen_unit_name = random.choice(available_units)
                except IndexError:
                    continue
            else:
                try:
                    chosen_unit_name = random.choice(units_of_rarity)
                except IndexError:
                    continue

            if (
                chosen_unit_name
                and chosen_unit_name in self.pool
                and self.pool[chosen_unit_name] > 0
            ):
                self.pool[chosen_unit_name] -= 1
                self.slots[i] = Unit(
                    chosen_unit_name, UNIT_DEFINITIONS[chosen_unit_name]
                )

    def buy(self, slot_index: int) -> Optional[Unit]:
        if 0 <= slot_index < SHOP_SLOTS and self.slots[slot_index]:
            unit = self.slots[slot_index]
            self.slots[slot_index] = None
            return unit
        return None

    def return_to_pool(self, unit_name: str):
        if unit_name in self.pool:
            self.pool[unit_name] += 1


class MapNode:
    def __init__(
        self,
        node_id: int,
        layer: int,
        index_in_layer: int,
        node_type: str,
        x: float,
        y: float,
        radius: float,
    ):
        self.node_id = node_id
        self.layer = layer
        self.index = index_in_layer
        self.node_type = node_type
        self.x, self.y, self.radius = x, y, radius  # No pygame.Rect
        self.next_nodes: List[int] = []
        self.visited = False
        self.completed = False
        self.enemy_team_key: Optional[str] = None
        try:  # FIX: Handle empty lists in random.choice
            if "COMBAT_EASY" in node_type and ["EASY_1", "EASY_2"]:
                self.enemy_team_key = random.choice(["EASY_1", "EASY_2"])
            elif "COMBAT_MEDIUM" in node_type and MEDIUM_NODES:
                self.enemy_team_key = random.choice(MEDIUM_NODES)
            elif "COMBAT_HARD" in node_type and HARD_NODES:
                self.enemy_team_key = random.choice(HARD_NODES)
            elif "BOSS" in node_type and BOSS_NODES:
                self.enemy_team_key = random.choice(BOSS_NODES)
        except IndexError:
            pass

    def collidepoint(self, pos: Tuple[float, float]) -> bool:
        # Basic circle collision
        dist_sq = (self.x - pos[0]) ** 2 + (self.y - pos[1]) ** 2
        return dist_sq <= self.radius**2


class GameMap:
    def __init__(self) -> None:
        self.nodes: Dict[int, MapNode] = {}
        self.start_node_id: int = 0
        self.map_width: float = MAP_WIDTH
        self.map_height: float = MAP_HEIGHT
        self.map_x_start: float = MAP_X_START
        self.map_y_start: float = MAP_Y_START
        self.node_radius: float = MAP_NODE_RADIUS
        self._generate_map()

    def _generate_map(self) -> None:
        node_id_counter = 0
        prev_layer_node_ids: List[int] = []
        node_types = list(NODE_TYPE_DISTRIBUTION.keys())
        node_weights = list(NODE_TYPE_DISTRIBUTION.values())
        layer_width = self.map_width / (MAP_DEPTH + 1.0)

        for layer in range(MAP_DEPTH):
            num_nodes = NODES_PER_LAYER[layer] if layer < len(NODES_PER_LAYER) else 1
            current_layer_node_ids: List[int] = []
            layer_height = self.map_height / (num_nodes + 1.0)
            x = self.map_x_start + layer * layer_width + layer_width

            for i in range(num_nodes):
                y = self.map_y_start + i * layer_height + layer_height / 2.0
                node_type = "EVENT"
                if layer == 0:
                    node_type = "COMBAT_EASY"
                elif layer == MAP_DEPTH - 1:
                    node_type = "BOSS"
                elif layer == MAP_DEPTH // 2:
                    node_type = random.choice(["SHOP", "EVENT", "COMBAT_HARD"])
                elif node_types and sum(node_weights) > 0:
                    try:
                        node_type = random.choices(
                            node_types, weights=node_weights, k=1
                        )[0]
                    except ValueError:
                        node_type = "COMBAT_EASY"

                node = MapNode(
                    node_id_counter,
                    layer,
                    i,
                    node_type,
                    x,
                    y,
                    self.node_radius,
                )
                if layer == 0:
                    self.start_node_id = node_id_counter
                    node.visited = False

                self.nodes[node_id_counter] = node
                current_layer_node_ids.append(node_id_counter)

                if layer > 0 and prev_layer_node_ids:
                    potential_parents: List[int] = []
                    min_idx = max(0, i - 1)
                    max_idx = min(len(prev_layer_node_ids) - 1, i + 1)
                    if layer == 1:
                        min_idx = 0
                        max_idx = 0
                    for parent_idx in range(min_idx, max_idx + 1):
                        if parent_idx < len(prev_layer_node_ids):
                            potential_parents.append(prev_layer_node_ids[parent_idx])
                    if not potential_parents:
                        potential_parents = prev_layer_node_ids
                    num_connections = random.randint(1, min(2, len(potential_parents)))
                    if layer == 1:
                        num_connections = 1
                    parents = random.sample(
                        potential_parents,
                        k=min(num_connections, len(potential_parents)),
                    )
                    for parent_id in parents:
                        self.nodes[parent_id].next_nodes.append(node_id_counter)

                node_id_counter += 1

            if layer > 0:
                for pid in prev_layer_node_ids:
                    if not self.nodes[pid].next_nodes:
                        chosen_child = random.choice(current_layer_node_ids)
                        self.nodes[pid].next_nodes.append(chosen_child)

            prev_layer_node_ids = current_layer_node_ids

        if (
            MAP_DEPTH > 1
            and node_id_counter > 0
            and (node_id_counter - 1) in self.nodes
        ):
            boss_node = self.nodes[node_id_counter - 1]
            penultimate_layer_ids = [
                nid for nid, node in self.nodes.items() if node.layer == MAP_DEPTH - 2
            ]
            for parent_id in penultimate_layer_ids:
                if (
                    parent_id in self.nodes
                    and boss_node.node_id not in self.nodes[parent_id].next_nodes
                ):
                    self.nodes[parent_id].next_nodes.append(boss_node.node_id)

    def get_node(self, node_id: int) -> Optional[MapNode]:
        return self.nodes.get(node_id)

    def is_node_reachable(self, target_node_id: int, current_node_id: int) -> bool:
        current_node = self.get_node(current_node_id)
        if not current_node:
            return False
        return target_node_id in current_node.next_nodes

    def rescale(
        self,
        width: float,
        height: float,
        x_start: float,
        y_start: float,
        node_radius: float,
    ) -> None:
        """Rescale node positions to match new map dimensions."""
        x_ratio = width / self.map_width
        y_ratio = height / self.map_height
        for node in self.nodes.values():
            node.x = x_start + (node.x - self.map_x_start) * x_ratio
            node.y = y_start + (node.y - self.map_y_start) * y_ratio
            node.radius = node_radius
        self.map_width = width
        self.map_height = height
        self.map_x_start = x_start
        self.map_y_start = y_start
        self.node_radius = node_radius
