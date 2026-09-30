"""Himeko • Nova (姬子•启行) — Erudition / Fire. "Starblazer" Assist Skill, Navigator's Semaphore team DMG buff,
multi-part Ultimate (Hyperluminal Particle Beam / Orbital Annihilation Pulse / Final Hit).

Assist Skill (no engine concept yet) — approximation: it is modelled as Himeko • Nova's own Skill action
(``ActionKind.SKILL``, damage tags ``skill`` + ``assist``, ATK of Himeko • Nova, no Skill Point cost), which the
Talent states ("Using Assist Skill is considered as Himeko • Nova using her Skill"). Assist Skill uses are tracked per
character. Teammates only use it when listed in ``assist_users``: their turn action is then replaced by the Assist
Skill while they have a use left (their own kit decides otherwise).

Options:
  ``assist_users``: names of teammates that use the Assist Skill as their turn action when available (default none).
  ``protocol``: special effect gained when a Trailblaze Companions teammate uses the Assist Skill: "verdict"
      (default) or "decimation" (the data does not say which companion grants which).

Policy: Skill when Navigator's Semaphore is missing or about to expire (and Skill Points allow), else the Assist
Skill, else Basic ATK.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

from .. import events as E
from .. import stats as S
from ..entities import Character, Enemy
from ..enums import ActionKind, DmgTag
from ..modifiers import Modifier, Tick
from . import register
from .base import Kit

ASSIST_ID = "151022"
VERDICT_ID = "151025"
DECIMATION_ID = "151026"
BEAM_ID = "151008"
PULSE_ID = "151009"
FINAL_ID = "151014"
ASSIST = "assist"  # damage tag of Assist Skill hits
BEAMS = 6  # "can launch Hyperluminal Particle Beam against enemies 6 times" (literal in the Ultimate text)
SEMAPHORE = "Navigator's Semaphore"
E6_SE_PER_ASSIST = 1  # E6: "Himeko • Nova gains 1 Source Energy" per Assist Skill (literal)
E6_SE_PER_BEAM = 1  # E6: "When launching Hyperluminal Particle Beam ... additionally gains 1 Source Energy" (literal)
# Trailblaze Companions (data has no such tag): March 7th, Dan Heng, Himeko, Welt, Imbibitor Lunae,
# March 7th (Hunt), Sunday, Evernight, Dan Heng • Permansor Terrae, Himeko • Nova and every Trailblazer.
COMPANIONS = frozenset(
    {"1001", "1002", "1003", "1004", "1213", "1224", "1313", "1413", "1414", "1510"}
    | {str(8001 + i) for i in range(10)}
)


@register
class HimekoNova(Kit):
    char_id = "1510"
    default_opts: ClassVar[dict[str, Any]] = {"assist_users": [], "protocol": "verdict"}

    def setup(self) -> None:
        self.se = 0  # Source Energy
        self.uses: dict[int, int] = {}
        self.free_left = self._free_limit()
        self.protocols: set[str] = set()
        self.verdict_ults = 0
        self.decimation_charge = 0
        self.ult_only: set[int] = set()
        self.wrapped: set[int] = set()
        self.tech = False
        stats = {S.CRIT_DMG: self.p("talent", 0), S.RES_PEN: self.p("talent", 1)}
        if self.e(4):
            # approximation: the team-wide RES PEN is permanent (it starts with the first Assist Skill in the game)
            stats[S.RES_PEN] += self.ep(4, 0)
            self.passive("Let No Skyward Hand Stay Unheld", {S.RES_PEN: self.p("talent", 1)}, scope=self.teammate_scope)
        self.passive("Of Fire and Far Faring", stats)
        if self.e(2):
            factor = self.ep(2, 0) - 1.0
            self.passive(
                "The Colors We Never Strike", {f"{S.FINAL_DMG}:{DmgTag.ULT}": factor, f"{S.FINAL_DMG}:{ASSIST}": factor}
            )
        if self.e(6):
            # approximation: the Assist Skill DMG bonus is treated as permanent (it is re-triggered by every use)
            self.passive(
                "Ours Is the Oath to Sail Starward",
                {f"{S.RES_PEN}:Fire": self.ep(6, 0), f"{S.DMG_PCT}:{ASSIST}": self.ep(6, 2)},
            )
        self.on(E.TURN_START, self._turn_start)
        self.on(E.ULT_USED, self._verdict)
        self.on(E.ATTACK_END, self._decimation)
        self.on(E.WAVE_START, self._on_wave)

    def on_battle_start(self) -> None:
        for c in self.allies():  # the Territory grants every ally character 1 Assist Skill use
            self.uses[c.uid] = 1
        for name in self.opts.get("assist_users") or []:
            c = self.battle.character(name)
            if c is not self.char and c.kit is not None and c.uid not in self.wrapped:
                self.wrapped.add(c.uid)
                setattr(c.kit, "take_turn", self._wrap_turn(c, c.kit.take_turn))  # noqa: B010

    def technique(self) -> None:
        self.tech = True
        self.battle.queue_action(lambda: self.skill(None, free=True), self.char, "Starcharter Cruise", priority=5)

    def _on_wave(self, ev: E.Ev) -> None:
        if self.tech and ev.wave > 0:
            self.battle.queue_action(lambda: self.skill(None, free=True), self.char, "Starcharter Cruise", priority=5)

    # ---------------------------------------------------------- Assist uses
    def cap(self) -> int:
        return 2 if self.e(2) else 1  # "The cap of Assist Skill uses increases to 2" (literal, E2)

    def _free_limit(self) -> int:
        rec = self.sk(ASSIST_ID)
        return int(rec["params"][self.level_of(rec) - 1][7]) + (int(self.ep(1, 0)) if self.e(1) else 0)

    def recover(self, c: Character, n: int) -> None:
        self.uses[c.uid] = min(self.cap(), self.uses.get(c.uid, 0) + n)

    def _turn_start(self, ev: E.Ev) -> None:
        c = ev.entity
        if not isinstance(c, Character):
            return
        if c is self.char and self.trace(1) and self.uses.get(c.uid, 0) >= self.cap():
            self.battle.gain_energy(self.char, self.tp(1, 0))
        if self.char.has_mod(SEMAPHORE):
            self.recover(c, 2 if self.e(2) else 1)

    def _wrap_turn(self, c: Character, orig: Callable[[], None]) -> Callable[[], None]:
        def turn() -> None:
            if c.uid in self.ult_only:  # the extra turn from "Hark! The Express's Pulse Roars": Ultimate only
                self.ult_only.discard(c.uid)
                return
            target = self.battle.default_target()
            if self.char.alive and target is not None and self.uses.get(c.uid, 0) >= 1:
                self.uses[c.uid] -= 1
                self.assist(c, target)
            else:
                orig()

        return turn

    # -------------------------------------------------------------- Assist
    def assist(self, user: Character, target: Enemy | None, launched: bool = False) -> None:
        """One Assist Skill: ``user`` uses it (or Himeko • Nova launches it for free when ``launched``)."""
        rec = self.sk(ASSIST_ID)
        lv = rec["params"][self.level_of(rec) - 1]
        by_self = user is self.char
        if by_self:
            aoe, n, rnd = lv[3], int(lv[4]), lv[5]
            if self.e(1):
                n += int(self.ep(1, 3))
        else:
            aoe, n, rnd = lv[0], int(lv[1]), lv[2]
        tough = rec["toughness"]
        with self.action(ActionKind.SKILL, rec, target, tags=(DmgTag.SKILL, ASSIST), sp=0, label=rec["name"]) as act:
            act.data["assist_user"] = user
            act.data["no_charge"] = launched
            act.aoe(aoe, toughness=tough[1], main_target=target, ignore_weakness=True)
            act.bounce(None, n, rnd, toughness=tough[0], ignore_weakness=True)
        if not by_self:
            self.battle.gain_energy(user, self.p("talent", 2))
        if self.e(6):
            self.add_se(E6_SE_PER_ASSIST)
        if not by_self and not launched and user.char_id in COMPANIONS:
            proto = str(self.opts.get("protocol") or "verdict")
            if proto in ("verdict", "decimation"):
                self.protocols.add(proto)
                self._apply_protocols()
        if not by_self and not launched and self.trace(2) and (user.char_id in COMPANIONS or self.e(2)):
            if user.uid in self.wrapped:
                self.ult_only.add(user.uid)
            self.battle.queue_extra_turn(user)

    def _apply_protocols(self) -> None:
        if "verdict" in self.protocols and not self.char.has_mod("Companion Protocol: Verdict"):
            rec = self.sk(VERDICT_ID)
            lv = rec["params"][self.level_of(rec) - 1]
            self.passive("Companion Protocol: Verdict", {S.DMG_PCT: lv[7], f"{S.DMG_PCT}:{DmgTag.ULT}": lv[9]})
        if "decimation" in self.protocols and not self.char.has_mod("Companion Protocol: Decimation"):
            rec = self.sk(DECIMATION_ID)
            lv = rec["params"][self.level_of(rec) - 1]
            self.passive(
                "Companion Protocol: Decimation",
                {S.CRIT_DMG: lv[7], f"{S.CRIT_DMG}:{DmgTag.SKILL}": lv[9]},
                scope=self.ally_scope,
            )

    def _launch_free(self) -> None:
        if self.free_left <= 0:
            return
        self.free_left -= 1
        self.battle.queue_action(
            lambda: self.assist(self.char, self.pick_target(), launched=True), self.char, "Companion Protocol"
        )

    def _verdict(self, ev: E.Ev) -> None:
        if "verdict" not in self.protocols or not isinstance(ev.entity, Character) or ev.entity is self.char:
            return
        rec = self.sk(VERDICT_ID)
        need = int(rec["params"][self.level_of(rec) - 1][8]) - (int(self.ep(1, 2)) if self.e(1) else 0)
        self.verdict_ults += 1
        if self.verdict_ults >= need:
            self.verdict_ults = 0
            self._launch_free()

    def _decimation(self, ev: E.Ev) -> None:
        act = ev.attack
        if "decimation" not in self.protocols or not act.attacked or act.data.get("no_charge"):
            return
        if not isinstance(act.owner, Character):
            return
        rec = self.sk(DECIMATION_ID)
        need = int(rec["params"][self.level_of(rec) - 1][8]) - (int(self.ep(1, 1)) if self.e(1) else 0)
        self.decimation_charge += len(act.attacked)
        if self.decimation_charge >= need:
            self.decimation_charge = 0
            self._launch_free()

    # -------------------------------------------------------------- policy
    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        sem = self.char.get_mod(SEMAPHORE)
        if (
            self.opts.get("rotation", "skill") == "skill"
            and self.can_skill()
            and (sem is None or (sem.duration or 0) <= 1)
        ):
            self.skill(target)
        elif self.trace(1) or self.uses.get(self.char.uid, 0) >= 1:
            if not self.trace(1):
                self.uses[self.char.uid] -= 1
            self.assist(self.char, target)
        else:
            self.basic(target)

    # ------------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.BASIC, "basic", target) as act:
            act.hit(target, self.p("basic", 0), toughness=self.toughness("basic"), ignore_weakness=True)

    def skill(self, target: Enemy | None, free: bool = False) -> None:
        with self.action(ActionKind.SKILL, "skill", sp=0 if free else None):
            for c in self.allies():
                self.uses[c.uid] = self.cap()
            self.buff_self(
                Modifier(
                    SEMAPHORE,
                    stats={S.DMG_PCT: self.p("skill", 0)},
                    duration=int(self.p("skill", 1)),
                    tick=Tick.SOURCE_TURN_START,
                    scope=self.ally_scope,
                    key=SEMAPHORE,
                )
            )

    # ------------------------------------------------------------ Ultimate
    def se_cap(self) -> int:
        rec = self.sk(BEAM_ID)
        return int(self.ep(6, 1)) if self.e(6) else int(rec["params"][self.level_of(rec) - 1][2])

    def add_se(self, n: int) -> None:
        self.se = min(self.se_cap(), self.se + n)

    def ult(self, target: Enemy | None) -> None:
        beam, pulse, final = self.sk(BEAM_ID), self.sk(PULSE_ID), self.sk(FINAL_ID)
        blv = beam["params"][self.level_of(beam) - 1]
        flv = final["params"][self.level_of(final) - 1]
        with self.action(ActionKind.ULT, "ult", target) as act:
            if self.trace(3):
                self.add_se(int(self.tp(3, 0)))
            beams = BEAMS
            # policy: fire "Orbital Annihilation Pulse" whenever Source Energy is full, otherwise a Beam
            while beams > 0 and self.enemies():
                if self.se >= self.se_cap():
                    self._pulse(act, pulse, target)
                else:
                    act.aoe(blv[0], toughness=beam["toughness"][1], main_target=target, ignore_weakness=True)
                    self.add_se(int(blv[1]) + (E6_SE_PER_BEAM if self.e(6) else 0))
                    beams -= 1
            if self.enemies() and self.se >= 1:
                self._pulse(act, pulse, target)
            act.bounce(None, int(flv[0]), flv[1], toughness=final["toughness"][0], ignore_weakness=True)
        self.free_left = self._free_limit()

    def _pulse(self, act: Any, rec: dict[str, Any], target: Enemy | None) -> None:
        lv = rec["params"][self.level_of(rec) - 1]
        n = self.se
        self.se = 0
        main = target if target is not None and target.alive else None
        act.aoe(lv[0], toughness=rec["toughness"][1], main_target=main, ignore_weakness=True)
        if n > 1:
            mult = lv[2] + (self.tp(3, 2) if self.trace(3) and n >= self.tp(3, 1) else 0.0)
            act.bounce(None, int(n / lv[1]), mult, toughness=rec["toughness"][0], ignore_weakness=True)
        if self.e(6) and n >= self.ep(6, 3):
            act.aoe(self.ep(6, 4), main_target=main, ignore_weakness=True)
