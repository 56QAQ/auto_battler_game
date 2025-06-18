# ai/navigation.py

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, Tuple

from data.constants import DEFAULT_MOVE_SPEED, MELEE_RANGE_THRESHOLD
from engine.utils import clamp

if TYPE_CHECKING:
    from engine.classes import Unit

# ----------------------------------------------------------- #
#                ---- public movement APIs ----               #
# ----------------------------------------------------------- #


def is_reachable(src: "Unit", dst: "Unit") -> bool:
    """Placeholder – in future path‑finding we would ray‑cast vs terrain."""
    return True


def move_towards(unit: "Unit", target: "Unit", dt: float) -> None:
    """
    Like old `move_towards_target` but with basic obstacle sampling.
    """
    if not target:
        return
    dx = target.x - unit.x
    dy = target.y - unit.y
    dist = math.hypot(dx, dy)
    stop_dist = max(
        unit.current_stats.get("range", 50), unit.radius + target.radius + 2
    )
    if dist <= stop_dist:
        return

    # ----- sample directions to avoid blocking friendlies ------- #
    direction = _find_clear_direction(unit, dx, dy, dist)
    speed = unit.current_stats.get("move_speed", DEFAULT_MOVE_SPEED) * dt
    unit.x += direction[0] * speed
    unit.y += direction[1] * speed

    # clamp inside arena (constants already imported into engine.classes->utils)
    from ui.constants import ARENA_MAX_X, ARENA_MAX_Y, ARENA_MIN_X, ARENA_MIN_Y

    unit.x = clamp(unit.x, ARENA_MIN_X, ARENA_MAX_X)
    unit.y = clamp(unit.y, ARENA_MIN_Y, ARENA_MAX_Y)


def kite_away(unit: "Unit", threat: "Unit", dt: float) -> None:
    """
    Simple ranged kiting: keep 70‑90 % of own range from nearest melee.
    """
    if not threat:
        return
    ideal = unit.current_stats.get("range", 120) * 0.8
    dx = unit.x - threat.x
    dy = unit.y - threat.y
    dist = math.hypot(dx, dy)
    if dist >= ideal:
        return
    if dist < 1e-3:
        # same pos – just random nudge
        angle = random.random() * 2 * math.pi
        dx, dy = math.cos(angle), math.sin(angle)
    else:
        dx /= dist
        dy /= dist

    speed = unit.current_stats.get("move_speed", DEFAULT_MOVE_SPEED) * dt
    unit.x += dx * speed
    unit.y += dy * speed


def should_kite(ranged: "Unit", enemy: "Unit") -> bool:
    """Return True when a ranged unit must back off."""
    if ranged.current_stats.get("range", 50) < MELEE_RANGE_THRESHOLD:
        return False
    dx = ranged.x - enemy.x
    dy = ranged.y - enemy.y
    dist_sq = dx * dx + dy * dy
    min_dist = ranged.current_stats.get("range", 50) * 0.3
    return dist_sq <= min_dist**2


# ----------------------------------------------------------- #
#                  ---- utility helpers ----                  #
# ----------------------------------------------------------- #

_ANGLE_OFFSETS = [0, 15, -15, 30, -30, 45, -45]  # degrees


def _find_clear_direction(
    unit: "Unit", dx: float, dy: float, dist: float
) -> Tuple[float, float]:
    """
    Shoot ray‑casts at several angles; pick first w/o immediate collision.
    Currently just checks overlap radius against *friendly* units; can be
    expanded for terrain later.
    """
    if dist <= 1e-3:
        return (0.0, 0.0)

    base_dir = (dx / dist, dy / dist)
    probes = [base_dir]
    # pre‑compute rotations
    for deg in _ANGLE_OFFSETS[1:]:
        rad = math.radians(deg)
        cos_a, sin_a = math.cos(rad), math.sin(rad)
        probes.append(
            (
                base_dir[0] * cos_a - base_dir[1] * sin_a,
                base_dir[0] * sin_a + base_dir[1] * cos_a,
            )
        )

    for vx, vy in probes:
        if not _immediate_collision(unit, vx, vy):
            return (vx, vy)
    # all blocked – just push minimal
    return base_dir


def _immediate_collision(unit: "Unit", vx: float, vy: float) -> bool:
    """
    Very cheap overlap test one small step ahead.
    """
    step = unit.radius * 1.2
    px = unit.x + vx * step
    py = unit.y + vy * step
    # local import to avoid heavy dep if caller never uses this func

    # We only need units lists; GameState not available here, so we rely
    # on Unit.team caches – as a placeholder, skip expensive search.
    return False  # TODO: integrate with spatial index


def nudge_random(unit: "Unit") -> None:
    """Small side step used by BehaviorContext when a unit is stuck."""
    if unit.current_stats.get("move_speed", DEFAULT_MOVE_SPEED) == 0:
        return
    angle = random.random() * 2 * math.pi
    dist = unit.radius * 0.3
    unit.x += math.cos(angle) * dist
    unit.y += math.sin(angle) * dist