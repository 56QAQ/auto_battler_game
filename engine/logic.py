# engine/logic.py
from __future__ import annotations

import copy
import math
import random
from collections import defaultdict
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union

# 新引入常量
from data.constants import (BENCH_SLOTS, BOARD_COLS, BOARD_ROWS,
                            CAST_ANIM_DURATION, COST_BY_RARITY_MATERIALS,
                            DEATH_ANIM_DURATION, HEAL_ANIM_DURATION,
                            MAX_COMBAT_DURATION, MAX_COMBINED_ITEMS,
                            MAX_ITEMS_EQUIPPED, MAX_ITEMS_INVENTORY,
                            MAX_UNITS_ON_BOARD, OVERTIME_DAMAGE_INTERVAL,
                            OVERTIME_DAMAGE_PERCENT, OVERTIME_START,
                            PASSIVE_XP, SLOT_MARGIN, SLOT_SIZE, ARENA_MAX_Y,COMBAT_ARENA_HEIGHT,ARENA_MAX_X, ARENA_MIN_X, ARENA_MIN_Y,
                            COMBAT_ARENA_WIDTH, COMBAT_ARENA_X, COMBAT_ARENA_Y,
                              )
# Data imports
from data.definitions import (ARTIFACT_DEFINITIONS, ENEMY_TEAM_DEFINITIONS,
                              ITEM_DEFINITIONS, ITEM_RECIPES, NODE_REWARDS,
                              POSSIBLE_EVENT_ARTIFACTS, POSSIBLE_EVENT_ITEMS,
                              SYNERGY_DEFINITIONS, UNIT_DEFINITIONS,)
# 新增 DamageSource
from data.enums import (AbilityEffect, DamageSource, DamageType, StatSource,
                        TriggerTarget, TriggerTiming, Color)
from engine.classes import (Artifact,Item, Player, Shop, Unit,
                            VisualEffect,DamageFloater)
# Engine imports
from engine.enums import AnimationState, EffectType, RemoveReason
from engine.utils import clamp

# Conditional imports
if TYPE_CHECKING:
    from engine.game_state import GameState, SynergyStatus
    from states.enums import UnitLocation

    # FIX: Remove type hint import for Selected*Info
    # from engine.classes import SelectedUnitInfo, SelectedItemInfo # Need type alias from state or define here? Define here.

# Type Aliases needed for logic that aren't in GameState
# From states.enums import UnitLocation - need this
SelectedUnitInfo = Tuple["UnitLocation", Union[int, Tuple[int, int]], Unit]
SelectedItemInfo = Tuple["UnitLocation", Union[int, SelectedUnitInfo], Item]


# -----
def end_combat(*args, **kwargs):
    """
    运行时再导入 `states.state_machine.end_combat`，以避免与
    `states.state_machine` 在解释阶段的循环依赖。
    """
    from states.state_machine import end_combat as _end_combat

    return _end_combat(*args, **kwargs)


# Forward declaration for type hinting. The real implementation appears later.
if TYPE_CHECKING:

    def resolve_trigger(
        unit: Unit,
        timing: TriggerTiming,
        state: "GameState",
        event_target: Optional[Unit],
        event_data: Optional[dict[str, Any]] = None,
    ) -> None: ...


# IMPORTANT: Assign the function to the class attribute to resolve circular dependency
# FIX: Assign the actual function AFTER it is defined, not a lambda. Move import.
# import engine.classes
# engine.classes.resolve_trigger_func = lambda u, t, s, e: resolve_trigger(u,t,s,e)


def resolve_collisions(units: List[Unit]):
    collidable_units = [
        u for u in units if u.is_alive and u.anim_state != AnimationState.DYING
    ]
    for i in range(len(collidable_units)):
        for j in range(i + 1, len(collidable_units)):
            unit_a = collidable_units[i]
            unit_b = collidable_units[j]
            dist_sq = (unit_a.x - unit_b.x) ** 2 + (unit_a.y - unit_b.y) ** 2
            min_dist = unit_a.radius + unit_b.radius
            if (
                dist_sq < min_dist**2 and dist_sq > 0.01
            ):  # avoid divide by zero or near zero
                dist = math.sqrt(dist_sq)
                overlap = min_dist - dist
                nx = (unit_b.x - unit_a.x) / dist
                ny = (unit_b.y - unit_a.y) / dist
                # FIX: Ensure push amount is not excessive
                push_amount = clamp(overlap * 0.55, 0, min_dist * 0.5)
                unit_a.x -= nx * push_amount
                unit_a.y -= ny * push_amount
                unit_b.x += nx * push_amount
                unit_b.y += ny * push_amount
            elif dist_sq <= 0.01 and min_dist > 0:  # Exactly on top, push randomly
                angle = random.uniform(0, 2 * math.pi)
                push_amount = min_dist * 0.55
                unit_a.x -= math.cos(angle) * push_amount
                unit_a.y -= math.sin(angle) * push_amount
                unit_b.x += math.cos(angle) * push_amount
                unit_b.y += math.sin(angle) * push_amount

    for unit in collidable_units:
        unit.x = clamp(unit.x, ARENA_MIN_X, ARENA_MAX_X)
        unit.y = clamp(unit.y, ARENA_MIN_Y, ARENA_MAX_Y)


def update_player_synergies(player: Player):
    player.active_synergies = calculate_active_synergies(player)


def add_item_to_inventory(player: Player, item: Item) -> bool:
    for i in range(MAX_ITEMS_INVENTORY):
        if player.item_inventory[i] is None:
            player.item_inventory[i] = item
            # print(f"DEBUG: Added item {item.name} to inventory slot {i}")
            return True
    print(f"DEBUG: Inventory full, could not add {item.name}")
    return False


# Needs local import or state must be passed
# from states.enums import UnitLocation
def attempt_equip_item(
    player: Player, item_info: SelectedItemInfo, target_unit_info: SelectedUnitInfo
) -> bool:
    return _attempt_equip_item(player, item_info, target_unit_info)


def attempt_unequip_item(
    player: Player, item_info: SelectedItemInfo, target_inv_idx: int
) -> bool:
    return _attempt_unequip_item(player, item_info, target_inv_idx)


def _attempt_equip_item(
    player: Player, item_info: SelectedItemInfo, target_unit_info: SelectedUnitInfo
) -> bool:
    from states.enums import UnitLocation  # Local import

    start_loc, start_idx, item = item_info
    target_loc, target_idx, unit = target_unit_info
    if not item or not unit or start_loc != UnitLocation.INVENTORY:
        return False
    if hasattr(item, "item_type"):
        if any(
            it and getattr(it, "item_type", None) == item.item_type
            for it in unit.equipped_items
        ):
            print("DEBUG: Unit already has this item‑type equipped.")
            return False
        if not item.can_equip(unit):
            print("DEBUG: Color / Module restriction not met.")
            return False
    combined_item_count = sum(
        1 for it in unit.equipped_items if it and getattr(it, "type", "") == "COMBINED"
    )
    for i in range(MAX_ITEMS_EQUIPPED):
        if unit.equipped_items[i] is None:
            if (
                item.item_type == "COMBINED"
                and combined_item_count >= MAX_COMBINED_ITEMS
            ):
                print(
                    f"DEBUG: Cannot equip, limit of {MAX_COMBINED_ITEMS} combined item(s) reached."
                )
                return False
            # Allow component equip even if max combined reached, player might combine later
            unit.equipped_items[i] = item
            player.item_inventory[start_idx] = None
            unit._recalculate_stats(0)
            # print(f"DEBUG: Equipped {item.name} on {unit.name}");
            return True
    print(f"DEBUG: {unit.name} has no free item slots / Cannot combine / Cannot equip.")
    return False


def _attempt_unequip_item(
    player: Player, item_info: SelectedItemInfo, target_inv_idx: int
) -> bool:
    from states.enums import UnitLocation  # Local import

    start_loc, unit_info, item = item_info
    # FIX: Check unit_info is not None
    if start_loc != UnitLocation.EQUIPPED or not item or not unit_info:
        return False
    unit_loc, unit_idx, unit = unit_info
    item_equipped_idx = -1
    for i in range(MAX_ITEMS_EQUIPPED):
        # FIX: check unit.equipped_items[i] is not None
        if unit.equipped_items[i] and unit.equipped_items[i].id == item.id:
            item_equipped_idx = i
            break
    if item_equipped_idx == -1:
        return False
    # Check inventory index bounds
    if not (0 <= target_inv_idx < len(player.item_inventory)):
        return False
    target_item = player.item_inventory[target_inv_idx]
    if target_item:  # Swap logic
        num_other_combined = sum(
            1
            for it in unit.equipped_items
            if it and it.type == "COMBINED" and it.id != item.id
        )
        if item.item_type == "COMBINED" and target_item.item_type == "COMBINED":
            print("DEBUG: Cannot swap two combined items")
            return False
        if (
            target_item.item_type == "COMBINED"
            and num_other_combined >= MAX_COMBINED_ITEMS
        ):
            print("DEBUG: Swap failed, max combined items reached")
            return False
    # Perform swap or move
    player.item_inventory[target_inv_idx] = item
    unit.equipped_items[item_equipped_idx] = target_item
    unit._recalculate_stats(0)
    # print(f"DEBUG: Unequipped/Swapped {item.name} from {unit.name} to inventory {target_inv_idx}");
    return True


def _attempt_combine(player: Player) -> bool:
    all_units = player.get_all_units()
    units_by_name_level = defaultdict(list)
    # FIX: only combine player units
    for unit in all_units:
        if not unit.is_enemy:
            units_by_name_level[(unit.name, unit.level)].append(unit)
    combined = False
    for (name, level), units in units_by_name_level.items():
        if level < 3 and len(units) >= 3:
            print(f"DEBUG: Combining 3x {name} Level {level}")
            # FIX: Ensure definition exists
            if name not in UNIT_DEFINITIONS:
                continue
            units_to_combine = units[:3]
            combined_unit = Unit(name, UNIT_DEFINITIONS[name], level + 1)
            first_bench_slot = -1
            board_pos = None
            units_on_board_count = 0
            items_to_transfer: List[Item] = []
            temp_bench = list(player.bench)
            temp_board = dict(player.board)
            for unit in units_to_combine:
                items_to_transfer.extend([item for item in unit.equipped_items if item])
                for i in range(BENCH_SLOTS):
                    if temp_bench[i] and temp_bench[i].id == unit.id:
                        temp_bench[i] = None
                        if first_bench_slot == -1:
                            first_bench_slot = i
                            break
                for pos, board_unit in temp_board.items():
                    if board_unit and board_unit.id == unit.id:
                        temp_board[pos] = None
                        if board_pos is None:
                            board_pos = pos
                            units_on_board_count += 1
                            break
            player.bench = temp_bench
            player.board = temp_board
            components = sorted(
                [i for i in items_to_transfer if i.type == "COMPONENT"],
                key=lambda x: x.name,
            )
            combined_items = [i for i in items_to_transfer if i.type == "COMBINED"]
            final_items: List[Item] = []
            # Prioritize keeping existing combined items
            num_combined_kept = 0
            for c_item in combined_items:
                if (
                    len(final_items) < MAX_ITEMS_EQUIPPED
                    and num_combined_kept < MAX_COMBINED_ITEMS
                ):
                    final_items.append(c_item)
                    num_combined_kept += 1
                else:
                    add_item_to_inventory(player, c_item)
            # Add remaining components
            for item in components:
                if len(final_items) < MAX_ITEMS_EQUIPPED:
                    final_items.append(item)
                else:
                    add_item_to_inventory(player, item)

            combined_unit.equipped_items[: len(final_items)] = final_items
            combined_unit._recalculate_stats(0)
            placed = False
            if board_pos is not None and units_on_board_count > 0:
                player.board[board_pos] = combined_unit
                placed = True
            else:
                if (
                    first_bench_slot != -1 and player.bench[first_bench_slot] is None
                ):  # FIX: check slot is still empty
                    player.bench[first_bench_slot] = combined_unit
                    placed = True
                else:
                    for i in range(BENCH_SLOTS):
                        if player.bench[i] is None:
                            player.bench[i] = combined_unit
                            placed = True
                            break
            if not placed:
                print(
                    "WARNING: Could not place combined unit! Adding to inventory if possible or deleting."
                )
                # Fallback: try adding to inventory if items, or just lose unit? Add to first bench slot if full?
                # For now, just log warning. A full bench+board state during combine is edge case.

            combined = True
            _attempt_combine(player)
            break  # Restart scan
    if combined:
        update_player_synergies(player)
    return combined


def add_unit_to_bench(player: Player, unit: Unit) -> bool:
    for i in range(BENCH_SLOTS):
        if player.bench[i] is None:
            player.bench[i] = unit
            _attempt_combine(player)
            return True
    print("DEBUG: Bench is full!")
    return False


def calculate_active_synergies(player: Player) -> "SynergyStatus":
    # FIX: Check if SynergyStatus needs importing (it doesn't if TYPE_CHECKING)
    # from engine.game_state import SynergyStatus # local import
    trait_counts = defaultdict(int)
    synergy_status: SynergyStatus = {}
    unique_units_on_board: Dict[str, Unit] = {}
    # FIX: Check if player.board exists/is iterable
    if hasattr(player, "board") and player.board:
        for unit in player.board.values():
            if unit and unit.name not in unique_units_on_board:
                unique_units_on_board[unit.name] = unit
    contributing_units = defaultdict(list)
    for name, unit in unique_units_on_board.items():
        for trait in unit.traits:
            trait_counts[trait] += 1
            contributing_units[trait].append(name)
        color_trait = unit.primary_color.name.title()
        trait_counts[color_trait] += 1
        contributing_units[color_trait].append(name)
        if unit.primary_color == Color.YELLOW:
            trait_counts[Color.RED.name.title()] += 1
            trait_counts[Color.GREEN.name.title()] += 1
            contributing_units[Color.RED.name.title()].append(name)
            contributing_units[Color.GREEN.name.title()].append(name)
        if unit.primary_color == Color.PURPLE:
            trait_counts[Color.RED.name.title()] += 1
            trait_counts[Color.BLUE.name.title()] += 1
            contributing_units[Color.RED.name.title()].append(name)
            contributing_units[Color.BLUE.name.title()].append(name)
        if unit.primary_color == Color.CYAN:
            trait_counts[Color.GREEN.name.title()] += 1
            trait_counts[Color.BLUE.name.title()] += 1
            contributing_units[Color.GREEN.name.title()].append(name)
            contributing_units[Color.BLUE.name.title()].append(name)
    all_present_traits = sorted(list(trait_counts.keys()))
    for trait in all_present_traits:
        if trait in SYNERGY_DEFINITIONS:
            count = trait_counts[trait]
            definition = SYNERGY_DEFINITIONS[trait]
            active_level_index = -1
            # FIX: ensure 'thresholds' exists
            thresholds = definition.get("thresholds", [])
            for i in range(len(thresholds) - 1, -1, -1):
                if count >= thresholds[i]:
                    active_level_index = i
                    break
            synergy_status[trait] = {
                "count": count,
                "level_index": active_level_index,
                "units": sorted(contributing_units.get(trait, [])),
            }
    return synergy_status


def apply_synergy_buffs(
    team: List[Unit], active_synergies: "SynergyStatus", current_time: float
):
    for trait, status in active_synergies.items():
        level_index = status["level_index"]
        if level_index == -1:
            continue
        definition = SYNERGY_DEFINITIONS.get(trait)
        # FIX: ensure definition and effects list exists and index is valid
        if (
            not definition
            or "effects" not in definition
            or level_index >= len(definition["effects"])
        ):
            continue
        buff = definition["effects"][level_index]
        target_mode = definition.get("targets")
        if definition.get("type") == "STAT_BOOST":
            for unit in team:
                should_apply = (target_mode == "ALL_ALLIES") or (
                    target_mode == "TRAIT" and trait in unit.traits
                )
                if should_apply:
                    unit.apply_synergy_artifact_buff(buff, current_time)
        elif definition.get("type") == "ABILITY" and trait == "Noble":
            targets: List[Unit] = []
            if target_mode == "RANDOM_ALLIES" and team:  # FIX: Check team is not empty
                num_targets = min(len(team), buff.get("units", 1))
                if len(team) > 0:
                    targets = random.sample(team, num_targets)
            for unit in targets:
                stat_buff = {"armor": buff.get("armor", 0), "mr": buff.get("mr", 0)}
                unit.apply_synergy_artifact_buff(stat_buff, current_time)
                unit.add_timed_buff(
                    "heal_on_hit",
                    buff.get("heal_on_hit", 0),
                    None,
                    current_time,
                    "SYNERGY_NOBLE",
                    False,
                )
        elif definition.get("type") == "ABILITY" and trait == "Cyan":
            regen = buff.get("regen", 0)
            dodge = buff.get("dodge_chance", 0)
            from engine.status_effects import HealOverTime

            for unit in team:
                unit.apply_synergy_artifact_buff({"dodge_chance": dodge}, current_time)
                if regen > 0:
                    hot = HealOverTime(
                        unit, "SYNERGY_CYAN", None, params={"heal": regen}
                    )
                    unit.add_status(hot)



def apply_artifact_buffs(
    team: List[Unit], artifacts: List[Artifact], current_time: float
):
    # FIX: ensure artifact has definition and stats
    global_buffs = [
        a.definition.get("stats", {})
        for a in artifacts
        if a and a.definition and a.type == "GLOBAL_STAT_BUFF"
    ]
    if global_buffs:
        for unit in team:
            for buff in global_buffs:
                unit.apply_synergy_artifact_buff(buff, current_time)


def remove_synergy_buffs(team: List[Unit]):
    for unit in team:
        unit.remove_all_buffs()


def _material_cost_bundle(unit: Unit) -> dict[str, int]:
    """Return a dict like {'RED':2,'GREEN':2} representing purchase price."""
    from data.enums import Color

    total = COST_BY_RARITY_MATERIALS[unit.rarity]
    col: Color = getattr(unit, "primary_color", Color.WHITE)
    if col == Color.WHITE:
        return {}
    bundle: dict[str, int] = {"RED": 0, "GREEN": 0, "BLUE": 0}
    if col in (Color.RED, Color.GREEN, Color.BLUE):
        bundle[col.value] = total
    elif col == Color.YELLOW:  # R+G
        bundle["RED"] = total // 2
        bundle["GREEN"] = total - bundle["RED"]
    elif col == Color.PURPLE:  # R+B
        bundle["RED"] = total // 2
        bundle["BLUE"] = total - bundle["RED"]
    elif col == Color.CYAN:  # B+G
        bundle["BLUE"] = total // 2
        bundle["GREEN"] = total - bundle["BLUE"]
    elif col == Color.BLACK:  # R+G+B
        share = total // 3
        bundle = {"RED": share, "GREEN": share, "BLUE": total - 2 * share}
    return bundle


def buy_unit_from_shop(player: Player, shop: Shop, slot_index: int) -> bool:
    if not (0 <= slot_index < len(shop.slots)):
        return False
    unit = shop.slots[slot_index]
    if not unit:
        return False
    # White units are free
    if unit.traits and unit.traits[0] == "WHITE":
        bundle = {}
    else:
        bundle = _material_cost_bundle(unit)
        if not player.can_pay_materials(bundle):
            return False
    # transact
    bought = shop.buy(slot_index)
    if not bought:
        return False
    if bundle:
        player.pay_materials(bundle)
    return add_unit_to_bench(player, bought)


def handle_sell_unit(player: Player, shop: Shop, info: SelectedUnitInfo) -> bool:
    from states.enums import UnitLocation  # Local import

    location, index, unit = info
    if not unit:
        return False
    price = unit.get_sell_price()
    # FIX: check index bounds / key existence
    if location == UnitLocation.BENCH and 0 <= index < len(player.bench):
        player.bench[index] = None
    elif location == UnitLocation.BOARD and index in player.board:
        player.board[index] = None
    else:
        return False  # Invalid location or index
    for item in unit.equipped_items:
        if item:
            add_item_to_inventory(player, item)
    player.gold += price
    # FIX: Only return player units to pool
    if not unit.is_enemy:
        shop.return_to_pool(unit.name)
    print(f"DEBUG: Sold {unit.name} (L{unit.level}) for {price} gold.")
    update_player_synergies(player)
    return True


def handle_unit_placement(
    player: Player,
    selected: SelectedUnitInfo,
    target_pos: Union[int, Tuple[int, int]],
    target_loc: "UnitLocation",
) -> bool:
    from states.enums import UnitLocation  # Local import

    start_loc, start_idx, unit = selected
    move_occurred = False
    # FIX: Ensure unit exists
    if not unit:
        return False
    board_units_count = len([u for u in player.board.values() if u])
    max_units = MAX_UNITS_ON_BOARD(player.level)
    target_unit = None
    # FIX: Check index/key validity
    if target_loc == UnitLocation.BENCH and 0 <= target_pos < len(player.bench):
        target_unit = player.bench[target_pos]
    elif target_loc == UnitLocation.BOARD:
        target_unit = player.board.get(target_pos)

    # FIX: Prevent moving to self
    if start_loc == target_loc and start_idx == target_pos:
        return False

    if start_loc == UnitLocation.BENCH and target_loc == UnitLocation.BOARD:
        # Check start index is valid
        if not (0 <= start_idx < len(player.bench)):
            return False
        if target_unit is None:
            if board_units_count < max_units:
                player.board[target_pos] = unit
                player.bench[start_idx] = None
                move_occurred = True
            else:
                print(
                    f"DEBUG: Board is full ({board_units_count}/{max_units}). Cannot move to empty slot."
                )
        # Swap: bench -> board, board -> bench
        elif target_unit.id != unit.id:
            player.board[target_pos] = unit
            player.bench[start_idx] = target_unit
            move_occurred = True
    elif start_loc == UnitLocation.BOARD and target_loc == UnitLocation.BENCH:
        # Check start index is valid
        if start_idx not in player.board:
            return False
        # Check target index is valid
        if not (0 <= target_pos < len(player.bench)):
            return False
        if target_unit is None:
            player.bench[target_pos] = unit
            player.board[start_idx] = None
            move_occurred = True
        # Swap: board -> bench, bench -> board
        elif target_unit.id != unit.id:
            # Check if board would exceed limit if target_unit moves there
            if board_units_count - 1 + 1 <= max_units:
                player.bench[target_pos] = unit
                player.board[start_idx] = target_unit
                move_occurred = True
            else:
                print(
                    f"DEBUG: Board is full ({board_units_count}/{max_units}). Cannot swap."
                )

    elif (
        start_loc == UnitLocation.BENCH
        and target_loc == UnitLocation.BENCH
        and start_idx != target_pos
    ):
        # Check both indices are valid
        if 0 <= start_idx < len(player.bench) and 0 <= target_pos < len(player.bench):
            player.bench[start_idx], player.bench[target_pos] = (
                player.bench[target_pos],
                player.bench[start_idx],
            )
            move_occurred = True
    elif (
        start_loc == UnitLocation.BOARD
        and target_loc == UnitLocation.BOARD
        and start_idx != target_pos
    ):
        # Check both indices are valid
        if start_idx in player.board:  # target_pos might not be in board (empty slot)
            player.board[start_idx], player.board[target_pos] = player.board.get(
                target_pos
            ), player.board.get(start_idx)
            move_occurred = True
    if move_occurred:
        update_player_synergies(player)
    return move_occurred


def calculate_base_value(
    unit: Unit, trigger: Dict, event_data: Optional[dict[str, Any]] = None
) -> float:
    if not trigger or "base_value_source" not in trigger:
        return 0.0  # FIX: check key
    source = trigger["base_value_source"]
    multiplier = trigger.get("base_value_multiplier", 1.0)
    flat = trigger.get("base_value_flat", 0.0)
    if source == StatSource.FLAT:
        return flat
    if source == StatSource.CURRENT_HP:
        return unit.current_hp * multiplier + flat
    if source == StatSource.EVENT and event_data is not None:
        key = trigger.get("event_key", "value")
        return event_data.get(key, 0.0) * multiplier + flat
    stat_key = source.value
    return unit.current_stats.get(stat_key, 0) * multiplier + flat


def find_targets(
    source_unit: Unit,
    target_type: TriggerTarget,
    state: "GameState",
    event_target: Optional[Union[Unit, List[Unit]]],
) -> List[Unit]:
    # FIX: Check target_type is valid
    if not target_type:
        return []
    if (
        not source_unit.is_alive
        and source_unit.anim_state != AnimationState.DYING
        and target_type not in [TriggerTarget.SELF, TriggerTarget.RANDOM_ENEMY]
    ):
        return []
    potential_enemies = (
        state.enemy_combat_team
        if not source_unit.is_enemy
        else state.player_combat_team
    )
    alive_enemies = [
        u
        for u in potential_enemies
        if u.is_alive and u.anim_state != AnimationState.DYING
    ]
    if target_type == TriggerTarget.SELF:
        return [source_unit]
    if target_type == TriggerTarget.ATTACK_TARGET:
        return (
            [event_target]
            if event_target
            and event_target.is_alive
            and event_target.anim_state != AnimationState.DYING
            else []
        )
    if target_type == TriggerTarget.EVENT_TARGETS:
        if not event_target:
            return []
        if isinstance(event_target, Iterable) and not isinstance(event_target, Unit):
            return [u for u in event_target if getattr(u, "is_alive", False)]
        if getattr(event_target, "is_alive", False):
            return [event_target]
        return []
    if not alive_enemies:
        return []
    if target_type == TriggerTarget.NEAREST_ENEMY:
        temp_target = source_unit.target
        source_unit.find_nearest_target(alive_enemies)
        res = [source_unit.target] if source_unit.target else []
        source_unit.target = temp_target
        return res
    if target_type == TriggerTarget.RANDOM_ENEMY:
        return [random.choice(alive_enemies)]
    if target_type == TriggerTarget.LOWEST_HP_ENEMY:
        # FIX: Avoid division by zero, handle units with 0 max hp
        valid_enemies = [u for u in alive_enemies if u.current_stats.get("hp", 0) > 0]
        if not valid_enemies:
            return []
        lowest_hp_unit = min(
            valid_enemies, key=lambda u: u.current_hp / u.current_stats["hp"]
        )
        return [lowest_hp_unit]
    return []


def execute_ability(
    ability: Dict,
    source: Unit,
    targets: List[Unit],
    base_value: float,
    state: "GameState",
):
    # FIX: Check required keys in ability dict
    if (
        not targets
        or not ability
        or "effect_type" not in ability
        or "effect_data" not in ability
    ):
        return
    effect_type = ability["effect_type"]
    data = ability["effect_data"]
    current_time = state.combat_timer
    if source.is_alive and source.anim_state != AnimationState.DYING:
        source.anim_state = AnimationState.CASTING
        source.anim_timer = 0
        source.flash_color_key = "CAST_FLASH_COLOR"
        state.visual_effects.append(
            VisualEffect(
                EffectType.CAST_AURA,
                source.x,
                source.y,
                CAST_ANIM_DURATION,
                "CAST_FLASH_COLOR",
                size=source.radius * 1.1,
            )
        )
    if effect_type == AbilityEffect.DEAL_DAMAGE:
        damage = base_value * data.get("scale_factor", 0) + data.get("flat_value", 0)
        if damage <= 0.1:
            return
        dtype = data.get("damage_type", DamageType.TRUE)  # FIX: default dtype
        color_map = {
            DamageType.PHYSICAL: "DAMAGE_PHYSICAL_COLOR",
            DamageType.MAGIC: "DAMAGE_MAGIC_COLOR",
            DamageType.TRUE: "DAMAGE_TRUE_COLOR",
        }
        color_key = color_map.get(dtype, "WHITE")
        for target in targets:
            if not (target.is_alive and target.anim_state != AnimationState.DYING):
                continue
            state.visual_effects.append(
                VisualEffect(
                    EffectType.PROJECTILE_MAGIC,
                    source.x,
                    source.y,
                    1.0,
                    "PROJECTILE_MAGIC_COLOR",
                    target_pos=(target.x, target.y),
                    size=6,
                )
            )
            outgoing = source.compute_outgoing_damage(
                damage,
                dtype,
                DamageSource.ITEM_ABILITY,
                data.get("is_aoe", False),
                target,
            )
            dmg_dealt = target.take_damage(
                outgoing,
                dtype,
                state,
                source,
                source_action=DamageSource.ITEM_ABILITY,
                is_aoe=data.get("is_aoe", False),
            )
            if dmg_dealt > 0.1:
                state.damage_floaters.append(
                    DamageFloater(target.x, target.y, f"{dmg_dealt:.0f}", color_key)
                )
            source.apply_lifesteal(dmg_dealt, dtype, state)
    elif effect_type == AbilityEffect.APPLY_BUFF:
        # FIX: Check required keys in data
        if all(k in data for k in ["stat", "value", "duration"]):
            stat, value, duration, is_percent = (
                data["stat"],
                data["value"],
                data["duration"],
                data.get("is_percent", False),
            )
            for target in targets:
                if target.is_alive and target.anim_state != AnimationState.DYING:
                    target.add_timed_buff(
                        stat, value, duration, current_time, source.id, is_percent
                    )
                    if "dot" in data:
                        from engine.status_effects import DamageOverTime

                        dot = DamageOverTime(
                            host=target,
                            source_id=source.id,
                            duration=duration,
                            params={"damage": data["dot"], "dtype": DamageType.TRUE},
                        )
                        target.add_status(dot)
                    state.visual_effects.append(
                        VisualEffect(
                            EffectType.BUFF_AURA,
                            target.x,
                            target.y,
                            0.4,
                            "BUFF_COLOR",
                            size=target.radius,
                        )
                    )
                    val_str = f"{value:+.0f}%" if is_percent else f"{value:+.0f}"
                    state.damage_floaters.append(
                        DamageFloater(
                            target.x, target.y - 10, f"{stat} {val_str}", "BUFF_COLOR"
                        )
                    )
    elif effect_type == AbilityEffect.HEAL:
        heal_amount = base_value * data.get("scale_factor", 0) + data.get(
            "flat_value", 0
        )
        heal_amount *= source._xs("outgoing_healing_bonus", 100.0) / 100.0
        if heal_amount <= 0.1:
            return
        for target in targets:
            if target.is_alive and target.anim_state != AnimationState.DYING:
                healed = target.heal(
                    heal_amount * target._xs("incoming_healing_bonus", 100.0) / 100.0,
                    state,
                    source,
                    source_action=DamageSource.ITEM_ABILITY,
                )
                if healed > 0.1:
                    state.visual_effects.append(
                        VisualEffect(
                            EffectType.HEAL_AURA,
                            target.x,
                            target.y,
                            HEAL_ANIM_DURATION,
                            "HEAL_COLOR",
                            size=target.radius,
                        )
                    )
                    state.damage_floaters.append(
                        DamageFloater(
                            target.x, target.y, f"+{healed:.0f}", "HEAL_COLOR"
                        )
                    )


def resolve_trigger(
    unit: Unit,
    timing: TriggerTiming,
    state: "GameState",
    event_target: Optional[Unit],
    event_data: Optional[dict[str, Any]] = None,
):
    # FIX: Check unit.trigger is not None and has 'timing_type'
    if (
        not unit.trigger
        or "timing_type" not in unit.trigger
        or unit.trigger["timing_type"] != timing
    ):
        return
    items_with_abilities = [
        item for item in unit.equipped_items if item and item.ability
    ]
    # FIX: This design means only units with items equipped can use their triggers.
    # The trigger defines the condition (timing, target, value source), the item defines the effect.
    if not items_with_abilities:
        return
    base_value = calculate_base_value(unit, unit.trigger, event_data)
    # FIX: Check 'target_type' exists
    if "target_type" not in unit.trigger:
        return
    targets = find_targets(unit, unit.trigger["target_type"], state, event_target)
    if not targets:
        return
    for item in items_with_abilities:
        execute_ability(item.ability, unit, targets, base_value, state)


def resolve_passive(
    unit: Unit, timing: TriggerTiming, state: "GameState", event_target: Optional[Unit]
):
    if (
        not unit.passive
        or "timing_type" not in unit.passive
        or unit.passive["timing_type"] != timing
    ):
        return
    ability = unit.passive.get("ability")
    if not ability:
        return
    base_value = calculate_base_value(unit, unit.passive)
    if "target_type" not in unit.passive:
        return
    targets = find_targets(unit, unit.passive["target_type"], state, event_target)
    if not targets:
        return
    execute_ability(ability, unit, targets, base_value, state)


# FIX: Assign the actual function directly to the class attribute AFTER definition
import engine.classes  # noqa: E402

engine.classes.resolve_trigger_func = resolve_trigger
engine.classes.resolve_passive_func = resolve_passive
# ----------------------------------------------------


def setup_combat_team(player: Player, is_enemy: bool) -> List[Unit]:
    team = []
    # FIX: Adjust y_base calculation
    y_base = (
        COMBAT_ARENA_Y + 40
        if not is_enemy
        else COMBAT_ARENA_Y + COMBAT_ARENA_HEIGHT - SLOT_SIZE * BOARD_ROWS - 40
    )
    x_base = (
        COMBAT_ARENA_X
        + (COMBAT_ARENA_WIDTH - BOARD_COLS * (SLOT_SIZE + SLOT_MARGIN)) / 2.0
    )
    source_board = player.board
    if not source_board:
        return []
    for pos, unit in source_board.items():
        if unit:
            row, col = pos
            combat_unit = copy.deepcopy(unit)
            combat_unit.reset_combat_state()
            # FIX: Calculate row correctly for enemy
            actual_row = row if not is_enemy else (BOARD_ROWS - 1 - row)
            # FIX: Center unit in slot
            combat_unit.x = x_base + col * (SLOT_SIZE + SLOT_MARGIN) + SLOT_SIZE / 2.0
            combat_unit.y = (
                y_base + actual_row * (SLOT_SIZE + SLOT_MARGIN) + SLOT_SIZE / 2.0
            )
            combat_unit.is_enemy = is_enemy
            combat_unit.base_color_key = "ENEMY_COLOR" if is_enemy else "ALLY_COLOR"
            combat_unit.current_color_key = combat_unit.base_color_key
            team.append(combat_unit)
    return team


def calculate_enemy_positions(enemy_units: List[Unit]) -> list[tuple[int, int]]:
    """Return board positions for enemy preview and spawning."""
    positions: list[tuple[int, int]] = []
    front_row_idx = 0
    back_row_idx = 0
    for unit in enemy_units:
        is_melee = unit.current_stats.get("range", 50) < 80
        row = BOARD_ROWS - 1 if is_melee else 0
        col = front_row_idx if is_melee else back_row_idx
        if is_melee:
            front_row_idx = (front_row_idx + 1) % BOARD_COLS
        else:
            back_row_idx = (back_row_idx + 1) % BOARD_COLS
        positions.append((row, col))
    return positions


def setup_enemy_combat_team(enemy_units: List[Unit]) -> List[Unit]:
    team = []
    # FIX: Adjust y_base calculation
    y_base = COMBAT_ARENA_Y + COMBAT_ARENA_HEIGHT - SLOT_SIZE * BOARD_ROWS - 40
    x_base = (
        COMBAT_ARENA_X
        + (COMBAT_ARENA_WIDTH - BOARD_COLS * (SLOT_SIZE + SLOT_MARGIN)) / 2.0
        + (SLOT_SIZE + SLOT_MARGIN) / 2
    )
    if not enemy_units:
        return []
    positions = calculate_enemy_positions(enemy_units)
    for unit, (row, col) in zip(enemy_units, positions):
        combat_unit = copy.deepcopy(unit)
        combat_unit.reset_combat_state()
        # FIX: Center unit in slot
        combat_unit.x = x_base + col * (SLOT_SIZE + SLOT_MARGIN) + SLOT_SIZE / 2.0
        combat_unit.y = y_base + row * (SLOT_SIZE + SLOT_MARGIN) + SLOT_SIZE / 2.0
        combat_unit.is_enemy = True
        combat_unit.base_color_key = "ENEMY_COLOR"
        combat_unit.current_color_key = "ENEMY_COLOR"
        team.append(combat_unit)
    return team


# -------------------- 难度 / 进度 动态加成 --------------------
def _get_enemy_scaling(
    nodes_cleared: int, difficulty: str
) -> tuple[float, float, float]:
    """返回 (HP乘数, 额外伤害%, 额外减伤%)"""
    coeff = {"easy": 0.08, "medium": 0.13, "hard": 0.20}.get(difficulty, 0.13)
    factor = 1.0 + coeff * (nodes_cleared**0.65)
    # HP × factor；伤害、减伤用百分比（在 Unit 里以 100 为基准的字段）
    return factor, 100.0 + (factor - 1.0) * 100.0, 100.0 + (factor - 1.0) * 50.0


def create_enemy_units(enemy_data: List[Dict], state: "GameState") -> List[Unit]:
    enemies: List[Unit] = []
    if not enemy_data:
        return enemies
    hp_mul, dmg_bonus_pct, dmg_reduc_pct = _get_enemy_scaling(
        state.nodes_cleared, state.difficulty_level
    )
    for data in enemy_data:
        name = data.get("name")
        level = data.get("level", 1)
        if name and name in UNIT_DEFINITIONS:
            u = Unit(name, UNIT_DEFINITIONS[name], level=level, is_enemy=True)
            # 应用加成
            u.current_stats["hp"] *= hp_mul
            u.current_hp = u.current_stats["hp"]
            u.current_stats["percentage_damage_bonus"] *= dmg_bonus_pct / 100.0
            u.current_stats["percentage_damage_reduction"] *= dmg_reduc_pct / 100.0
            enemies.append(u)
    return enemies


def apply_artifact_effect(player: Player, artifact: Artifact):
    # FIX: check artifact and definition validity
    if not artifact or not artifact.definition:
        return
    print(f"DEBUG: Applying Artifact: {artifact.name}")
    if artifact.type == "ITEM_GRANT":
        item_name = artifact.definition.get("item")
        if item_name in ITEM_DEFINITIONS:
            add_item_to_inventory(player, Item(item_name))
    elif artifact.type == "XP_GRANT":
        player.gain_xp(artifact.definition.get("value", 0))
    elif artifact.type == "GOLD_GRANT":
        player.gold += artifact.definition.get("value", 0)


def give_node_rewards(state: "GameState", node_type: str, player_won: bool = True):
    reward_def = NODE_REWARDS.get(
        node_type, {"gold": 1, "xp": 0, "items": [], "artifacts": []}
    )
    gold_reward = 0
    xp_reward = PASSIVE_XP  # Always give passive XP
    # Only give node-specific rewards (gold, items, artifacts) on win, or for SHOP/EVENT
    if player_won or node_type in ["SHOP", "EVENT"]:
        gold_reward += reward_def.get("gold", 0)
        xp_reward += reward_def.get("xp", 0)
        if player_won:  # Apply GOLD_ON_WIN artifacts only if it was a combat win
            for art in state.player.has_artifact("GOLD_ON_WIN"):
                if art and art.definition:
                    gold_reward += art.definition.get("value", 0)  # FIX check
        item_rewards = reward_def.get("items", [])
        if item_rewards:  # FIX: check list is not empty
            try:
                item_name = random.choice(item_rewards)
            except IndexError:
                item_name = None
            if item_name and item_name in ITEM_DEFINITIONS:
                add_item_to_inventory(state.player, Item(item_name))
        art_rewards = reward_def.get("artifacts", [])
        if art_rewards:  # FIX: check list is not empty
            available_arts = [
                a
                for a in art_rewards
                if not any(pa and pa.name == a for pa in state.player.artifacts)
            ]  # FIX check pa
            if available_arts:
                try:
                    art_name = random.choice(available_arts)
                except IndexError:
                    art_name = None
                if art_name:
                    new_art = Artifact(art_name)
                    state.player.artifacts.append(new_art)
                    apply_artifact_effect(state.player, new_art)
        print(
            f"DEBUG: Awarded {gold_reward} gold, {xp_reward} xp for {node_type} ({'Win' if player_won else 'Loss'})"
        )
    else:  # Loss scenario
        print(
            f"DEBUG: Awarded {gold_reward} gold, {xp_reward} xp for {node_type} ({'Win' if player_won else 'Loss'})"
        )

    state.player.gold += gold_reward
    state.player.gain_xp(xp_reward)
    # FIX: Scavenger synergy gold check
    scav_status = state.player.active_synergies.get("Scavenger")
    if player_won and scav_status and scav_status["level_index"] != -1:
        definition = SYNERGY_DEFINITIONS.get("Scavenger")
        effect = definition["effects"][scav_status["level_index"]]
        if random.random() < effect.get("gold_chance", 0):
            gold_found = effect.get("gold", 0)
            state.player.gold += gold_found
            print(f"DEBUG: Scavenger found {gold_found} gold!")


def run_combat_tick(state: "GameState", delta_time: float):
    state.combat_timer += delta_time
    state.delta_time_combat = delta_time
    if state.combat_timer < 0.5:
        return  # Initial pause
    for floater in state.damage_floaters:
        floater.update(delta_time)
    state.damage_floaters = [f for f in state.damage_floaters if not f.is_expired()]
    for effect in state.visual_effects:
        effect.update(delta_time)
    state.visual_effects = [e for e in state.visual_effects if not e.is_expired()]

    # FIX: Keep units in list while dying animation plays
    state.player_combat_team = [
        u
        for u in state.player_combat_team
        if u.is_alive or (not u.is_alive and u.anim_timer < DEATH_ANIM_DURATION)
    ]
    state.enemy_combat_team = [
        u
        for u in state.enemy_combat_team
        if u.is_alive or (not u.is_alive and u.anim_timer < DEATH_ANIM_DURATION)
    ]

    player_alive = [u for u in state.player_combat_team if u.is_alive]
    enemy_alive = [u for u in state.enemy_combat_team if u.is_alive]

    # FIX: Check if combat end condition met BEFORE updates
    # Check for draw (no units left at all)
    if not state.player_combat_team and not state.enemy_combat_team:
        end_combat(state, player_won=True, damage_taken=0)
        return
    # Check for player loss (no alive, and no more dying animations)
    if not player_alive and not any(
        u.anim_state == AnimationState.DYING for u in state.player_combat_team
    ):
        damage = sum([u.level for u in enemy_alive]) * 2 + (
            5 if state.combat_timer > OVERTIME_START else 0
        )
        end_combat(
            state,
            player_won=False,
            damage_taken=damage,
            overtime_loss=state.combat_timer > OVERTIME_START,
        )
        return
    # Check for player win (no alive, and no more dying animations)
    if not enemy_alive and not any(
        u.anim_state == AnimationState.DYING for u in state.enemy_combat_team
    ):
        end_combat(state, player_won=True, damage_taken=0)
        return

    is_overtime = state.combat_timer > OVERTIME_START
    # Process buffs and overtime damage ONLY for alive units
    all_units_processing = player_alive + enemy_alive
    for unit in all_units_processing:
        unit.process_statuses(delta_time)

    if is_overtime:
        state.overtime_damage_timer += delta_time
        if state.overtime_damage_timer >= OVERTIME_DAMAGE_INTERVAL:
            state.overtime_damage_timer -= OVERTIME_DAMAGE_INTERVAL
            # FIX: Calculate damage percent correctly, cap
            damage_percent = min(
                0.9, OVERTIME_DAMAGE_PERCENT * (state.combat_timer - OVERTIME_START + 1)
            )
            print(f"DEBUG: OVERTIME DAMAGE TICK: {damage_percent*100:.1f}% Max HP")
            for unit in all_units_processing:
                ot_damage = unit.current_stats.get("hp", 0) * damage_percent  # FIX .get
                dmg_dealt = unit.take_damage(ot_damage, DamageType.TRUE, state, None)
                if dmg_dealt > 0.1:
                    state.damage_floaters.append(
                        DamageFloater(
                            unit.x, unit.y, f"{dmg_dealt:.0f}!", "OVERTIME_COLOR"
                        )
                    )

    # Include dying units in processing just for animation updates
    all_units_animation = state.player_combat_team + state.enemy_combat_team
    random.shuffle(all_units_animation)  # Shuffle order
    for unit in all_units_animation:
        # Only find targets and move/attack if alive
        targets = []
        if unit.is_alive:
            targets = enemy_alive if not unit.is_enemy else player_alive
        unit.combat_update(targets, state)  # update always runs animation logic
    # Resolve collisions only among alive units
    resolve_collisions(all_units_processing)
    state.process_triggers()