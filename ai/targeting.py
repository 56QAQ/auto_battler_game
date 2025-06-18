#ai/targeting.py


from __future__ import annotations

from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from engine.classes import Unit

# tunables ---------------------------------------------------- #
_SWITCH_CD = 0.7          # s – time being blocked before change

def _threat(unit: "Unit", enemy: "Unit") -> float:
    """
    Higher == more appetising target.
    Crude heuristic: recent damage dealt (not tracked yet) -> fallback to HP%.
    """
    # prioritise low HP
    hp_ratio = enemy.current_hp / max(1.0, enemy.current_stats.get("hp", 1))
    distance = ((unit.x - enemy.x) ** 2 + (unit.y - enemy.y) ** 2) ** 0.5
    reach = unit.current_stats.get("range", 50)
    if reach == 0:
        distance_factor = 0.1
    else: distance_factor = max(0.1, distance / reach)
    return (1.0 - hp_ratio) * 2.0 + 1.0 / distance_factor


def acquire_target_if_needed(unit: "Unit", enemies: List["Unit"], dt: float) -> None:
    """
    Decide whether to keep current target or switch.
    """
    # Sanity‑filter list
    live = [e for e in enemies if e and e.is_alive]
    if not live:
        unit.target = None
        return

    # initial pick
    if unit.target is None or not unit.target.is_alive:
        unit.target = max(live, key=lambda e: _threat(unit, e))
        setattr(unit, "_blocked_time", 0.0)           # type: ignore
        return
    dist = ((unit.x - unit.target.x) ** 2 + (unit.y - unit.target.y) ** 2) ** 0.5
    if dist <= unit.current_stats.get("range", 50):
        setattr(unit, "_blocked_time", 0.0)
        return
    # evaluate blocking/stuck
    blocked: float = getattr(unit, "_blocked_time", 0.0) + dt
    if blocked >= _SWITCH_CD:
        # retarget to something else (highest threat except current)
        alt = sorted(live, key=lambda e: _threat(unit, e), reverse=True)
        if alt and alt[0] is not unit.target:
            unit.target = alt[0]
            blocked = 0.0
    setattr(unit, "_blocked_time", blocked)           # type: ignore
