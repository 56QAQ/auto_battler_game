"""Aglaea (阿格莱雅) — Remembrance / Lightning. Memosprite Garmentmaker (SPD stacks from hitting the
"Seam Stitch" target); Ultimate "Supreme Stance": Joint ATK enhanced Basic ATK, SPD-to-ATK conversion, countdown.

Options (``default_opts``):
  * ``rotation``: ``"auto"`` (Skill only to summon Garmentmaker, default), ``"skill"`` (also heal Garmentmaker
    with the Skill whenever SP allows) or ``"basic"``.

``memo_hit`` (a hit of an action dealt by another unit, e.g. the memosprite half of a Joint ATK) is shared
with the other Remembrance kits.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from .. import events as E
from .. import formulas as F
from .. import stats as S
from ..entities import Enemy, Entity, Summon
from ..enums import ActionKind, DmgTag, Element
from ..modifiers import Modifier, ModKind, Stacking, Tick, hidden
from . import register
from .base import Kit

if TYPE_CHECKING:
    from ..battle import Action, Battle, Hit

E6_SPD = (160.0, 240.0, 320.0)  # E6 "SPD is greater than 160/240/320" (literal thresholds)
SEAM = "Seam Stitch"


def memo_hit(
    act: Action,
    attacker: Entity,
    target: Enemy,
    mult: float,
    *,
    stat: str = "atk",
    flat: float = 0.0,
    toughness: float = 0.0,
    tags: Iterable[str] | None = None,
    label: str | None = None,
    primary: bool = True,
    extra: dict[str, float] | None = None,
    ignore_weakness: bool = False,
) -> Hit:
    """One hit of ``act`` dealt by ``attacker`` instead of the action's actor (Joint ATKs, a memosprite
    dealing its master's Ultimate DMG ...). ``flat`` is added to the base DMG (e.g. "X% of the master's HP")."""
    hit = act._make(target, mult, stat, toughness, 1.0, None, tags, label, flat, True, ignore_weakness, extra, primary)
    hit.attacker = attacker
    return act.battle.do_hit(hit)


@register
class Aglaea(Kit):
    char_id = "1402"
    default_opts = {"rotation": "auto"}

    def setup(self) -> None:
        self.countdown: Summon | None = None
        self.stance: Modifier | None = None
        self.gm_stacks = 0
        self.retained = 0
        self.seam: Enemy | None = None
        self.on(E.ATTACK_START, self._apply_seam)
        self.on(E.ATTACK_END, self._after_attack)
        self.passive("Supreme Stance SPD", {}, dyn=self._stance_spd, dyn_keys={S.SPD_PCT})
        if self.trace(1):
            self.passive("The Myopic's Doom", {}, dyn=self._a2_atk, dyn_keys={S.ATK_FLAT})
        if self.e(2):
            self.on(E.ACTION_START, self._e2)
        if self.e(6):
            res_key = f"{S.RES_PEN}:{Element.LIGHTNING.value}"
            self.passive(
                "Fluctuate in the Tapestry of Fates",
                {},
                dyn=lambda m, k, e: self.ep(6, 0) if self.in_stance else 0.0,
                dyn_keys={res_key},
            )
            self.on(E.BEFORE_HIT, self._e6_joint)

    def on_battle_start(self) -> None:
        if self.trace(3):
            floor = self.tp(3, 1) * self.char.max_energy
            if self.char.energy < self.tp(3, 0) * self.char.max_energy:
                self.char.energy = floor

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        self.summon_gm()
        self.battle.gain_energy(self.char, p[1], fixed=True)
        with self.action(ActionKind.EXTRA, None, label="Meteoric Sunder (Technique)", energy=0, sp=0) as act:
            act.aoe(p[0], toughness=self.toughness("technique"))
        enemies = self.enemies()
        if enemies:
            self._mark(self.battle.rng.choice(enemies))

    # ------------------------------------------------------------ helpers
    @property
    def in_stance(self) -> bool:
        return self.stance is not None and not self.stance.removed

    def gm(self) -> Summon | None:
        return self.memosprite()

    def _memo_rec(self, sid: str) -> list[Any]:
        rec = self.sk(sid)
        return list(rec["params"][self.level_of(rec) - 1])

    def max_stacks(self) -> int:
        return int(self._memo_rec("1140203")[2]) + (int(self.ep(4, 0)) if self.e(4) else 0)

    def _stance_spd(self, mod: Modifier, key: str, ent: Entity) -> float:
        return self.p("ult", 0) * self.gm_stacks if self.in_stance else 0.0

    def _a2_atk(self, mod: Modifier, key: str, ent: Entity) -> float:
        gm = self.gm()
        if not self.in_stance or gm is None:
            return 0.0
        return self.tp(1, 0) * self.char.spd + self.tp(1, 1) * gm.spd

    def _gm_spd(self, mod: Modifier, key: str, ent: Entity) -> float:
        return self._memo_rec("1140203")[0] * self.gm_stacks

    def add_gm_stack(self) -> None:
        self.gm_stacks = min(self.max_stacks(), self.gm_stacks + 1)

    # ------------------------------------------------------- Garmentmaker
    def summon_gm(self) -> Summon:
        gm = self.gm()
        if gm is not None:
            return gm
        gm = self.summon_memosprite("Garmentmaker", on_turn=self._gm_turn)
        self.gm_stacks = self.retained
        self.retained = 0
        self.battle.apply(hidden("A Body Brewed by Tears", {}, dyn=self._gm_spd, dyn_keys={S.SPD_FLAT}), gm, self.char)
        self.battle.advance(gm, self._memo_rec("1140205")[0])  # "The Speeding Summer"
        return gm

    def dismiss_gm(self) -> None:
        gm = self.gm()
        if gm is not None:
            self.battle.remove_unit(gm)
            self.battle.gain_energy(self.char, self._memo_rec("1140206")[0])
        self.retained = min(int(self.tp(2, 0)), self.gm_stacks) if self.trace(2) else 0
        self.gm_stacks = 0
        if self.stance is not None:
            self.battle.remove_modifier(self.stance)
        self.stance = None
        if self.countdown is not None:
            self.battle.remove_unit(self.countdown)
            self.countdown = None
        if self.seam is not None:
            self.battle.remove_named(self.seam, SEAM)
            self.seam = None

    def _gm_turn(self, gm: Summon, battle: Battle) -> None:
        seam = self.seam if self.seam is not None and self.seam.alive else None
        target = seam or self.pick_target()
        if target is None:
            return
        rec = self.sk("1140201")
        lv = rec["params"][self.level_of(rec) - 1]
        tough = rec["toughness"]
        with self.battle.action(gm, ActionKind.MEMOSPRITE, skill=rec, target=target) as act:
            act.blast(target, lv[0], lv[1], toughness=(float(tough[0]), float(tough[2])))

    def _countdown_turn(self, unit: Summon, battle: Battle) -> None:
        self.dismiss_gm()  # "When the countdown's turn starts, Garmentmaker self-destructs"

    # ------------------------------------------------------- Seam Stitch
    def _mark(self, t: Enemy) -> None:
        if self.seam is not None and self.seam is not t:
            self.battle.remove_named(self.seam, SEAM)
        self.seam = t
        stats = {S.VULN: self.ep(1, 0)} if self.e(1) else {}
        self.battle.apply(
            Modifier(SEAM, stats=stats, kind=ModKind.DEBUFF, tick=Tick.NONE, dispellable=False, key=SEAM), t, self.char
        )

    def _apply_seam(self, ev: E.Ev) -> None:
        act = ev.attack
        if act.actor is self.char and self.gm() is not None and isinstance(act.target, Enemy) and act.target.alive:
            self._mark(act.target)

    def _after_attack(self, ev: E.Ev) -> None:
        act = ev.attack
        gm = self.gm()
        if act.actor is not self.char and (gm is None or act.actor is not gm):
            return
        seam = self.seam
        gm_hit_seam = act.actor is gm and seam is not None and seam in act.attacked
        if gm is not None and (gm_hit_seam or (act.actor is self.char and self.e(4))):
            self.add_gm_stack()  # Memosprite Talent SPD Boost (E4: Aglaea's attacks too)
        if seam is None or seam not in act.attacked or not seam.alive:
            return
        self.battle.additional_damage(
            self.char,
            seam,
            self.p("talent", 0),
            element=Element.LIGHTNING,
            label="Rosy-Fingered (Seam Stitch)",
            tags=(DmgTag.ADDITIONAL,),
        )
        if self.e(1):
            self.battle.gain_energy(self.char, self.ep(1, 1))

    # -------------------------------------------------------- eidolons
    def _e2(self, ev: E.Ev) -> None:
        act = ev.action
        if act.kind in (ActionKind.FUA, ActionKind.EXTRA):
            return
        gm = self.gm()
        if act.actor is self.char or (gm is not None and act.actor is gm):
            self.buff_self(
                Modifier(
                    "Sail on the Raft of Eyelids",
                    stats={S.DEF_IGNORE: self.ep(2, 0)},
                    stacking=Stacking.STACK,
                    max_stacks=int(self.ep(2, 1)),
                    tick=Tick.NONE,
                )
            )
        else:
            self.battle.remove_named(self.char, "Sail on the Raft of Eyelids")

    def _e6_joint(self, ev: E.Ev) -> None:
        h = ev.hit
        if h.action is None or not h.action.data.get("aglaea_joint"):
            return
        gm = self.gm()
        spd = max(self.char.spd, gm.spd if gm is not None else 0.0)
        for thr, bonus in reversed(list(zip(E6_SPD, (self.ep(6, 1), self.ep(6, 2), self.ep(6, 3)), strict=True))):
            if spd > thr:
                h.add(S.DMG_PCT, bonus)
                break

    # ------------------------------------------------------------ policy
    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        policy = self.opts.get("rotation", "auto")
        if self.in_stance or policy == "basic" or not self.can_skill():
            self.basic(target)
        elif self.gm() is None or policy == "skill":
            self.skill(target)
        else:
            self.basic(target)

    # ----------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        gm = self.gm()
        if not self.in_stance or gm is None:
            with self.action(ActionKind.BASIC, "basic", target) as act:
                act.hit(target, self.p("basic", 0), toughness=self.toughness("basic"), splits="data")
            return
        rec = self.sk("140208")
        lv = rec["params"][self.level_of(rec) - 1]
        tough = rec["toughness"]
        with self.action(ActionKind.BASIC, rec, target) as act:
            act.data["aglaea_joint"] = True
            act.blast(target, lv[0], lv[1], toughness=(float(tough[0]), float(tough[2])))
            memo_tags = (DmgTag.BASIC, DmgTag.MEMOSPRITE)
            for t in [target, *self.battle.adjacent(target)]:
                memo_hit(act, gm, t, lv[2] if t is target else lv[3], tags=memo_tags, primary=t is target)

    def skill(self, target: Enemy | None) -> None:
        gm = self.gm()
        rec = self.sk("140209") if gm is not None else self.sk("skill")
        with self.action(ActionKind.SKILL, rec, gm):
            if gm is not None:
                self.battle.heal(gm, self.p("skill", 0) * gm.max_hp, self.char)
            else:
                self.summon_gm()

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult"):
            gm = self.gm()
            if gm is not None:
                self.battle.heal(gm, gm.max_hp, self.char)
            else:
                self.summon_gm()
            if not self.in_stance:
                self.stance = self.buff_self(hidden("Supreme Stance", {}))
            if self.countdown is None:
                self.countdown = self.battle.add_unit(
                    Summon("Supreme Stance Countdown", self.char, spd=self.p("ult", 3), on_turn=self._countdown_turn)
                )
            else:  # "using Ultimate again will reset the countdown"
                self.countdown.gauge = F.AV_BASE
        self.battle.advance(self.char, 1.0)
