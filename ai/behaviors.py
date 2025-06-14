#ai/behaviors.py
# Combat‑AI ―― behaviour/state machine layer
# Author: refactor batch #1  (2025‑06‑14)
from __future__ import annotations

import enum
import math
from typing import List, Optional, TYPE_CHECKING

from ai import navigation as nav
from ai import targeting as tgt

if TYPE_CHECKING:                                   # Avoid heavy imports at runtime
    from engine.classes import Unit
    from engine.game_state import GameState


# ------------------------------------------------------------ #
#               ----  Public enums / dataclasses ----          #
# ------------------------------------------------------------ #

class BehaviorState(enum.Enum):
    IDLE   = 0
    CHASE  = 1
    ATTACK = 2
    KITE   = 3
    RETREAT = 4
    STUNNED = 5
    DEAD    = 6


class BehaviorContext:
    """
    A lightweight state‑machine wrapper that lives on each Unit.
    It owns no game data – it *delegates* to navigation/targeting helpers.
    """

    __slots__ = ("host", "state", "_stuck_timer", "_last_pos", "_blocked_time")

    # ── Stuck‑detection tuning ──
    # We only treat a unit as “stuck” when **trying to chase** yet barely moved. A
    # ranged carry that is calmly attacking should never be nudged.
    _STUCK_THRESHOLD_DIST = 1.0      # px (movement considered “no progress”)
    _STUCK_THRESHOLD_TIME = 0.50     # s (how long without progress before nudge)

    def __init__(self, host: "Unit"):
        self.host: Unit = host
        self.state: BehaviorState = BehaviorState.IDLE
        self._stuck_timer: float = 0.0
        self._last_pos: tuple[float, float] = (host.x, host.y)
        self._blocked_time: float = 0.0     # path blocked duration

    # -------------------------------------------------------- #
    #                   ---- update entry ----                 #
    # -------------------------------------------------------- #
    def update(self, potential_targets: List["Unit"], gs: "GameState") -> None:
        """Main per‑frame entry (called from Unit.combat_update)."""
        dt = gs.delta_time_combat
        host = self.host

        # ----- death / stun gates -------------------------------------- #
        if not host.is_alive or host.anim_state.value == "DYING":
            self.state = BehaviorState.DEAD
            return
        if host._is_action_blocked():
            self.state = BehaviorState.STUNNED
            return

        # ----- refresh / validate target ------------------------------ #
        tgt.acquire_target_if_needed(host, potential_targets, dt)

        # ----- decision logic ----------------------------------------- #
        if host.target is None:
            self.state = BehaviorState.IDLE
        else:
            dist_sq = (host.x - host.target.x) ** 2 + (host.y - host.target.y) ** 2
            ideal_range = host.current_stats.get("range", 50)
            melee = ideal_range < 80
            in_range = dist_sq <= max(ideal_range ** 2,
                                      (host.radius + host.target.radius + 5) ** 2)

            if not melee and nav.should_kite(host, host.target):
                self.state = BehaviorState.KITE
            elif in_range:
                self.state = BehaviorState.ATTACK
            else:
                self.state = BehaviorState.CHASE

        # ----- execute ------------------------------------------------- #
        if self.state == BehaviorState.ATTACK:
            host.attack_target(gs)
        elif self.state == BehaviorState.CHASE:
            nav.move_towards(host, host.target, dt)
        elif self.state == BehaviorState.KITE:
            nav.kite_away(host, host.target, dt)
        elif self.state in (BehaviorState.IDLE, BehaviorState.STUNNED):
            # no‑op other than maybe animation which Unit handles
            pass

        # ----- anti‑stuck bookkeeping --------------------------------- #
        self._detect_and_recover_stuck(dt)

    # -------------------------------------------------------- #
    #                     ---- helpers ----                    #
    # -------------------------------------------------------- #
    def _detect_and_recover_stuck(self, dt: float):
        """Track host position; if hardly moved, trigger unstuck manoeuvre."""
        # Only evaluate “stuck” when **actively chasing** a target.
        if self.state != BehaviorState.CHASE:
            self._stuck_timer = 0.0
            self._last_pos = (self.host.x, self.host.y)
            return

        host = self.host
        dx = host.x - self._last_pos[0]
        dy = host.y - self._last_pos[1]
        progressed = abs(dx) + abs(dy) >= self._STUCK_THRESHOLD_DIST
        if progressed:
            self._stuck_timer = 0.0
            self._last_pos = (host.x, host.y)
            return

        self._stuck_timer += dt
        if self._stuck_timer >= self._STUCK_THRESHOLD_TIME:
            # invoke navigation random nudge + force re‑acquire next frame
            nav.nudge_random(host)
            self._stuck_timer = 0.0
            host.target = None   # force re‑target

# ------------------------------------------------------------ #
#      (Nothing below is imported outside this module)         #
# ------------------------------------------------------------ #