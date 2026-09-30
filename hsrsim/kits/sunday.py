"""Sunday (星期日) — Harmony / Imaginary. Immediate action + DMG/CRIT Rate Skill, The Beatified (CRIT DMG) ultimate.

Options:
  target:   name of the ally receiving the Skill and Ultimate (default: first other slot)
  rotation: "skill" (default) Skill whenever SP allows, "basic" never uses the Skill
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..entities import Character, Enemy, Entity, Summon
from ..enums import ActionKind, Path
from ..modifiers import Modifier, Stacking, Tick
from . import register
from .base import Kit

PERCENT = 100.0  # E6 "every 1% of excess CRIT Rate increases CRIT DMG by 2%": per-percent conversion
CRIT_RATE_CAP = 1.0  # E6 "... exceeds 100%" (literal)
BEATIFIED_SP = 1  # Skill "After using Skill on The Beatified, recovers 1 Skill Point" (literal)


def _real_summons(ally: Character) -> list[Summon]:
    # approximation: countdown units (Robin, Firefly ...) are Summons in the engine but not summons in game
    return [s for s in ally.summons if s.alive and "Countdown" not in s.name]


@register
class Sunday(Kit):
    char_id = "1313"
    ult_targets_ally = True
    default_opts = {"target": None}

    def setup(self) -> None:
        self.first_ult = True
        self.technique_pending = False
        if self.e(1):
            self.on(E.BEFORE_HIT, self._e1_summon)
        if self.e(4):
            self.on(
                E.TURN_START, lambda ev: ev.entity is self.char and self.battle.gain_energy(self.char, self.ep(4, 0))
            )

    def on_battle_start(self) -> None:
        if self.trace(2):
            self.battle.gain_energy(self.char, self.tp(2, 0))

    def technique(self) -> None:
        self.technique_pending = True

    # ------------------------------------------------------------ helpers
    def _use_technique(self, ally: Character) -> None:
        if not self.technique_pending:
            return
        self.technique_pending = False
        p = self.sk("technique")["params"][0]
        self.buff(ally, Modifier("The Glorious Mysteries", stats={S.DMG_PCT: p[0]}, duration=int(p[1])))

    def _e6_convert(self, mod: Modifier, key: str, ent: Entity) -> float:
        return max(0.0, ent.stat(S.CRIT_RATE) - CRIT_RATE_CAP) * PERCENT * self.ep(6, 1)

    def _talent(self, ally: Character) -> None:
        dur = int(self.p("talent", 1)) + (int(self.ep(6, 2)) if self.e(6) else 0)
        mod = Modifier(
            "The Sorrowing Body",
            stats={S.CRIT_RATE: self.p("talent", 0)},
            duration=dur,
            stacking=Stacking.STACK if self.e(6) else Stacking.REFRESH,
            max_stacks=int(self.ep(6, 0)) if self.e(6) else 1,
        )
        if self.e(6):
            mod.dyn = self._e6_convert
            mod.dyn_keys = frozenset({S.CRIT_DMG})
        self.buff(ally, mod)

    def _e1_summon(self, ev: E.Ev) -> None:
        a = ev.hit.attacker
        if isinstance(a, Summon) and "Countdown" not in a.name and a.owner.has_mod("Millennium's Quietus"):
            # the owner's DEF ignore is inherited by owner/sync summons; top it up to the summon value
            ev.hit.add(S.DEF_IGNORE, self.ep(1, 2) - self.ep(1, 1))

    def beatified(self) -> Character | None:
        for c in self.allies():
            if c.has_mod("The Beatified"):
                return c
        return None

    # ------------------------------------------------------------- policy
    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        if self.opts.get("rotation", "skill") == "skill" and self.can_skill():
            self.skill(target)
        else:
            self.basic(target)

    # ------------------------------------------------------------ actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        self.simple_basic(target)

    def skill(self, target: Enemy | None) -> None:
        ally = self.main_dps()
        summons = _real_summons(ally)
        with self.action(ActionKind.SKILL, "skill", ally):
            if self.trace(3):
                for m in [m for m in ally.debuffs if m.dispellable][: int(self.tp(3, 0))]:
                    self.battle.remove_modifier(m)
            dmg = self.p("skill", 1) + (self.p("skill", 3) if summons else 0.0)
            self.buff(
                ally, Modifier("Benison of Paper and Rites", stats={S.DMG_PCT: dmg}, duration=int(self.p("skill", 2)))
            )
            self._talent(ally)
            if self.e(1):
                self.buff(
                    ally,
                    Modifier("Millennium's Quietus", stats={S.DEF_IGNORE: self.ep(1, 1)}, duration=int(self.ep(1, 0))),
                )
            if ally is not self.char and ally.has_mod("The Beatified"):
                self.battle.gain_sp(BEATIFIED_SP, self.char)
            self._use_technique(ally)
        if ally is not self.char and ally.path != Path.HARMONY:
            self.battle.advance(ally, self.p("skill", 0))
            for s in summons:
                self.battle.advance(s, self.p("skill", 0))

    def ult(self, target: Enemy | None) -> None:
        ally = self.main_dps()
        with self.action(ActionKind.ULT, "ult", ally):
            gain = self.p("ult", 0) * ally.max_energy
            if self.trace(1):
                gain = max(gain, self.tp(1, 0))
            self.battle.gain_energy(ally, gain, fixed=True)
            if ally is not self.char:
                for c in self.allies():
                    if c is not ally:
                        self.battle.remove_named(c, "The Beatified")
                # approximation: snapshot of Sunday's CRIT DMG at cast (summons inherit it from their owner)
                # not modelled: The Beatified is dispelled when Sunday is knocked down
                stats = {S.CRIT_DMG: self.p("ult", 1) * self.char.stat(S.CRIT_DMG) + self.p("ult", 3)}
                if self.e(2):
                    stats[S.DMG_PCT] = self.ep(2, 0)
                self.buff(
                    ally,
                    Modifier(
                        "The Beatified",
                        stats=stats,
                        duration=int(self.p("ult", 2)),
                        tick=Tick.SOURCE_TURN_START,
                        key="The Beatified",
                    ),
                )
            if self.e(6):
                self._talent(ally)
            self._use_technique(ally)
        if self.e(2) and self.first_ult:
            self.battle.gain_sp(int(self.ep(2, 1)), self.char)
        self.first_ult = False
