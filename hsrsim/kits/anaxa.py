"""Anaxa (那刻夏) — Erudition / Wind. Implants Weaknesses on every hit; Qualitative Disclosure targets
take more DMG and trigger an additional Skill after his Basic ATK / Skill. Ultimate: Sublimation (all Weaknesses).

Options (``default_opts``):
  * ``rotation``: ``"skill"`` (Skill whenever SP allows, default) or ``"basic"``.
  * ``sublimation_cc``: Sublimation stops enemies without Control RES from acting (default True).
    # approximation: enemies count as having Control RES when they are bosses or have ``debuff_res:cc`` > 0.
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..entities import Enemy
from ..enums import ActionKind, Element, EnemyRank, Path
from ..modifiers import Modifier, ModKind, Stacking, Tick
from . import register
from .base import Kit

# Toughness of each extra Skill bounce: not in the data (the display value only covers the first
# instance); community frame data lists 5 per bounce.
BOUNCE_TOUGHNESS = 5.0
MAX_WEAKNESS_TYPES = 7  # A6 "Up to a max of 7 Weakness Types can be taken into account" (literal)


@register
class Anaxa(Kit):
    char_id = "1405"
    default_opts = {"rotation": "skill", "sublimation_cc": True}

    def setup(self) -> None:
        self.first_skill = True
        self.on(E.AFTER_HIT, self._implant_on_hit)
        self.on(E.BEFORE_HIT, self._before_hit)
        self.on(E.ACTION_START, self._check_disclosure)
        self.on(E.ACTION_END, self._additional_skill)
        self.on(E.TURN_START, self._turn_start)
        if self.e(2):
            self.on(E.ENEMY_SPAWNED, lambda ev: self._e2(ev.enemy))
        eru = sum(1 for c in self.battle.team if c.path == Path.ERUDITION)
        if self.trace(2):
            if eru == 1 or self.e(6):
                self.passive("Imperative Hiatus (CRIT DMG)", {S.CRIT_DMG: self.tp(2, 0)})
            if eru >= 2 or self.e(6):
                self.passive("Imperative Hiatus (DMG)", {S.DMG_PCT: self.tp(2, 1)}, scope=self.ally_scope)
        if self.e(6):
            self.passive("Everything Is in Everything", {S.FINAL_DMG: self.ep(6, 0) - 1.0})

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        for e in self.enemies():
            self.implant(e, self.char.element, int(p[1]))

    # --------------------------------------------------------- weaknesses
    @staticmethod
    def weakness_count(e: Enemy) -> int:
        return sum(1 for el in Element if e.is_weak_to(el))

    def disclosed(self, e: Enemy) -> bool:
        """Qualitative Disclosure: at least #3 different Weakness types."""
        return self.weakness_count(e) >= int(self.p("talent", 2))

    def implant(self, e: Enemy, element: Element | None = None, turns: int | None = None) -> None:
        if not e.alive:
            return
        if element is None:
            missing = [el for el in Element if not e.is_weak_to(el)]
            element = self.battle.rng.choice(missing or list(Element))
        self.battle.apply(
            Modifier(
                f"Anaxa Weakness ({element.value})",
                duration=turns if turns is not None else int(self.p("talent", 1)),
                kind=ModKind.DEBUFF,
                tags={f"weak:{element.value}"},
                key=f"Anaxa Weakness {element.value}",
            ),
            e,
            self.char,
        )

    def _implant_on_hit(self, ev: E.Ev) -> None:
        h = ev.hit
        if h.attacker is self.char and h.action is not None:
            self.implant(h.target)

    def _before_hit(self, ev: E.Ev) -> None:
        h = ev.hit
        if h.attacker is not self.char:
            return
        if self.disclosed(h.target):
            h.add(S.DMG_PCT, self.p("talent", 0))
        if self.trace(3):
            h.add(S.DEF_IGNORE, self.tp(3, 0) * min(MAX_WEAKNESS_TYPES, self.weakness_count(h.target)))

    def _e2(self, e: Enemy) -> None:
        self.implant(e)
        self.battle.apply(
            Modifier(
                "Soul, True to History",
                stats={S.RES_REDUCTION: self.ep(2, 0)},
                kind=ModKind.DEBUFF,
                tick=Tick.NONE,
            ),
            e,
            self.char,
        )

    def _turn_start(self, ev: E.Ev) -> None:
        if ev.entity is self.char and self.trace(1) and not any(self.disclosed(e) for e in self.enemies()):
            self.battle.gain_energy(self.char, self.tp(1, 1))

    # ------------------------------------------------------------ actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.BASIC, "basic", target) as act:
            act.hit(target, self.p("basic", 0), toughness=self.toughness("basic"))
            if self.trace(1):
                act.energy += self.tp(1, 0)

    def skill(self, target: Enemy | None, additional: bool = False) -> None:
        assert target is not None
        b = self.battle
        mult = self.p("skill", 0)
        extra = {S.DMG_PCT: self.p("skill", 2) * len(self.enemies())}
        with self.action(ActionKind.SKILL, "skill", target, sp=0 if additional else None) as act:
            act.data["anaxa_additional"] = additional
            if self.e(4):
                self.buff_self(
                    Modifier(
                        "Blaze, Plunged to Canyon",
                        stats={S.ATK_PCT: self.ep(4, 0)},
                        duration=int(self.ep(4, 1)),
                        stacking=Stacking.STACK,
                        max_stacks=int(self.ep(4, 2)),
                    )
                )
            act.hit(target, mult, toughness=self.toughness("skill"), extra=extra)
            hit = {target}
            for _ in range(int(self.p("skill", 1))):
                alive = [e for e in b.alive_enemies() if e.hp > 0] or b.alive_enemies()
                if not alive:
                    break
                fresh = [e for e in alive if e not in hit]
                t = b.rng.choice(fresh or alive)
                hit.add(t)
                act.hit(t, mult, toughness=BOUNCE_TOUGHNESS, extra=extra, primary=False)
            if self.e(1):
                for t in act.attacked:
                    if t.alive:
                        self.battle.apply(
                            Modifier(
                                "Magician, Isolated by Stars",
                                stats={S.DEF_REDUCTION: self.ep(1, 0)},
                                duration=int(self.ep(1, 1)),
                                kind=ModKind.DEBUFF,
                            ),
                            t,
                            self.char,
                        )
        if self.e(1) and self.first_skill:
            self.first_skill = False
            b.gain_sp(int(self.ep(1, 2)), self.char)

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult", target) as act:
            for e in self.enemies():
                cc_res = e.rank == EnemyRank.BOSS or e.stat(f"{S.DEBUFF_RES}:cc") > 0
                self.battle.apply(
                    Modifier(
                        "Sublimation",
                        duration=1,
                        tick=Tick.HOLDER_TURN_START,
                        kind=ModKind.DEBUFF,
                        tags={f"weak:{el.value}" for el in Element},
                        skip_turn=bool(self.opts.get("sublimation_cc", True)) and not cc_res,
                    ),
                    e,
                    self.char,
                )
            act.aoe(self.p("ult", 0), toughness=self.toughness("ult", 1), main_target=target)

    # ------------------------------------------------------------- talent
    def _check_disclosure(self, ev: E.Ev) -> None:
        """The additional Skill is decided when the Basic ATK / Skill is used (OnBeforeSkillUse in the ability
        script): the target must already be in "Qualitative Disclosure", Weaknesses implanted by this action's
        own hits do not count."""
        act = ev.action
        if act.actor is self.char and act.kind in (ActionKind.BASIC, ActionKind.SKILL):
            target = act.target
            act.data["anaxa_disclosed"] = isinstance(target, Enemy) and self.disclosed(target)

    def _additional_skill(self, ev: E.Ev) -> None:
        act = ev.action
        if act.actor is not self.char or act.kind not in (ActionKind.BASIC, ActionKind.SKILL):
            return
        if act.data.get("anaxa_additional"):
            return
        target = act.target
        if not isinstance(target, Enemy) or not act.data.get("anaxa_disclosed"):
            return

        def extra_skill() -> None:
            t = target if target.alive and target.hp > 0 else None
            if t is None:
                alive = self.enemies()
                t = self.battle.rng.choice(alive) if alive else None
            if t is not None:
                self.skill(t, additional=True)

        self.battle.queue_action(extra_skill, self.char, "Anaxa additional Skill", priority=5)
