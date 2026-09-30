"""Interactive battle sessions (turn-by-turn manual control, Ultimate insertion, undo).

A :class:`Session` runs one battle in a worker thread with a :class:`~hsrsim.control.Controller` attached. When the
battle reaches a decision point that needs the player (an ally's turn, or an Ultimate window while someone's
Ultimate is ready) the worker serialises the state and blocks until :meth:`Session.decide` / :meth:`Session.auto`
answers. Every answer is recorded; :meth:`Session.undo` rebuilds the battle from the same seed and replays the
recorded answers up to the previous decision point.

Settings (sent with every answer, recorded with it so replays are exact):

* ``auto_ult``: ``{ref: bool}`` — cast that character's Ultimate automatically (kit policy) whenever it is ready,
* ``pause``: which Ultimate windows stop for the player while an Ultimate is ready —
  ``before_enemy`` (default on), ``before_ally`` (off: the ally's turn menu offers the Ultimate anyway),
  ``after_action`` (an ally's action has resolved, its turn has not ended yet, on), ``queue`` (between
  follow-ups, on), ``mid_action`` (inside actions that do not end the turn, on),
* ``auto``: set by :meth:`Session.auto` — the kits' policies play until a stop condition (``once``, ``ally_turn``,
  ``cycle``, ``wave``, ``end``).
"""

from __future__ import annotations

import copy
import itertools
import queue
import threading
import traceback
from dataclasses import dataclass
from typing import Any

from . import events as E
from . import stats as S
from .battle import Battle, BattleConfig
from .build import Build, make_character, stat_sheet
from .control import AUTO, CONTINUE, Controller, Decision, MenuItem
from .elation import ElationSystem
from .entities import Character, Enemy, Entity, Summon
from .enums import Element, Path
from .formulas import AV_BASE
from .modifiers import ModKind
from .scenarios import Scenario

DEFAULT_SETTINGS: dict[str, Any] = {
    "auto_ult": {},
    "pause": {"before_enemy": True, "before_ally": False, "after_action": True, "queue": True, "mid_action": True},
    "auto": None,
}
_TIMEOUT = 120.0  # seconds to wait for the worker to reach the next decision point


class _Abort(Exception):
    """Raised inside the worker thread to stop a battle that is being replaced."""


_ABORT = object()


@dataclass
class Point:
    """A decision point reached by the battle."""

    kind: str  # "turn" | "window"
    where: str = ""  # window: before_turn / after_action / queue / mid_action
    actor: Entity | None = None  # turn: the acting unit
    subject: Entity | None = None  # window: unit acting next / owning the next queued action
    extra_turn: bool = False


def _settings(s: dict[str, Any] | None) -> dict[str, Any]:
    out = copy.deepcopy(DEFAULT_SETTINGS)
    for k, v in (s or {}).items():
        if k == "pause" and isinstance(v, dict):
            out["pause"].update(v)
        else:
            out[k] = copy.deepcopy(v)
    return out


# =============================================================================== controller
class _SessionController(Controller):
    def __init__(self, worker: _Worker, script: list[dict[str, Any]], settings: dict[str, Any]) -> None:
        self.w = worker
        self.script = list(script)
        self.settings = settings
        self.recorded: list[dict[str, Any]] = []
        self.diverged = False

    # ------------------------------------------------------------- decision points
    def turn(self, battle: Battle, actor: Entity, extra_turn: bool) -> Decision:
        return self._ask(Point("turn", actor=actor, extra_turn=extra_turn))

    def window(self, battle: Battle, where: str, subject: Entity | None) -> Decision:
        ready = [c for c in battle.team if c.alive and c.kit is not None and c.kit.ult_ready()]
        if not ready:
            return CONTINUE
        auto_ult = self.settings.get("auto_ult", {})
        for c in ready:
            if auto_ult.get(c.ref) and c.kit is not None and c.kit.want_ult():
                return Decision("ult", who=c.ref)  # deterministic from the settings: not recorded
        if self.settings.get("auto"):
            return self._ask(Point("window", where=where, subject=subject))
        if not any(not auto_ult.get(c.ref) for c in ready) or not self._pause_here(where, subject):
            return CONTINUE
        return self._ask(Point("window", where=where, subject=subject))

    def _pause_here(self, where: str, subject: Entity | None) -> bool:
        pause = self.settings.get("pause", {})
        if where == "before_turn":
            if isinstance(subject, Enemy):
                return bool(pause.get("before_enemy", True))
            return bool(pause.get("before_ally", False))
        if where == "queue":
            return bool(pause.get("queue", True)) and subject is not None
        if where == "after_action":
            return bool(pause.get("after_action", True))
        return bool(pause.get("mid_action", True))

    # -------------------------------------------------------------------- asking
    def _fingerprint(self, p: Point) -> str:
        b = self.w.battle
        who = p.actor or p.subject
        return f"{b.time:.3f}|{p.kind}|{p.where}|{who.ref if who else ''}|{b.sp}|{b.turns}"

    def _ask(self, p: Point) -> Decision:
        fp = self._fingerprint(p)
        if self.script:
            rec = self.script.pop(0)
            if "s" in rec:
                self.settings = _settings(rec["s"])
            if rec.get("fp") and rec["fp"] != fp:
                self.diverged = True
            self.recorded.append(rec)
            return Decision.from_dict(rec["d"])
        auto = self.settings.get("auto")
        if auto and not self._auto_done(p, auto):
            d = self._auto_answer(p)
            if auto.get("mode") == "once":
                self.settings["auto"] = None
            self.recorded.append({"d": d.to_dict(), "fp": fp, "s": copy.deepcopy(self.settings)})
            return d
        if auto:
            self.settings["auto"] = None
        # ask the player
        self.w.point = p
        while True:
            self.w.outbox.put(("point", self.w.snapshot(p)))
            cmd = self.w.inbox.get()
            if cmd is _ABORT:
                raise _Abort
            kind, payload, settings = cmd
            if settings is not None:
                self.settings = _settings(settings)
            if kind == "auto":
                self.settings["auto"] = self._auto_state(payload)
                d = self._auto_answer(p)
                if payload == "once":
                    self.settings["auto"] = None
            else:
                d = Decision.from_dict(payload)
                problem = self._invalid(p, d)
                if problem:
                    self.w.error = problem
                    continue
            self.w.error = ""
            self.recorded.append({"d": d.to_dict(), "fp": fp, "s": copy.deepcopy(self.settings)})
            return d

    def _invalid(self, p: Point, d: Decision) -> str:
        b = self.w.battle
        if d.kind == "ult":
            c = b.by_ref(d.who)
            if not isinstance(c, Character) or c.kit is None or not c.kit.ult_ready():
                return f"{c.name if c else d.who}: Ultimate not ready"
            return ""
        if d.kind == "continue":
            return "choose an action" if p.kind == "turn" else ""
        if d.kind == "auto":
            return ""
        if d.kind == "act":
            if p.kind != "turn" or p.actor is None:
                return "not a turn"
            menu = b._menu_of(p.actor) or []
            item = next((m for m in menu if m.id == d.item), None)
            if item is None:
                return f"unknown action {d.item!r}"
            if not item.enabled:
                return f"{item.label}: {item.note or 'not available'}"
            return ""
        return f"unknown decision {d.kind!r}"

    # ---------------------------------------------------------------------- auto
    def _auto_state(self, mode: str) -> dict[str, Any]:
        b = self.w.battle
        return {"mode": mode, "cycle": b.cycle, "wave": b.wave_index}

    def _auto_done(self, p: Point, auto: dict[str, Any]) -> bool:
        b = self.w.battle
        mode = auto.get("mode")
        if mode == "ally_turn":
            return p.kind == "turn"
        if mode == "cycle":
            return b.cycle > int(auto.get("cycle", 0))
        if mode == "wave":
            return b.wave_index != int(auto.get("wave", 0))
        return False  # "once" handled by the caller, "end" never stops

    def _auto_answer(self, p: Point) -> Decision:
        b = self.w.battle
        if p.kind == "turn":
            return AUTO
        for c in b.team:
            if c.alive and c.kit is not None and c.kit.ult_ready() and c.kit.want_ult():
                return Decision("ult", who=c.ref)
        return CONTINUE


# =================================================================================== worker
class _Worker:
    def __init__(self, session: Session, script: list[dict[str, Any]]) -> None:
        self.session = session
        sc = session.scenario
        conf = BattleConfig(**{**sc.config, "seed": session.seed})
        chars = [make_character(copy.deepcopy(b)) for b in session.team]
        self.battle = Battle(chars, sc.make_waves(), conf)
        self.ctrl = _SessionController(self, script, _settings(session.initial_settings))
        self.battle.controller = self.ctrl
        self.inbox: queue.Queue[Any] = queue.Queue()
        self.outbox: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.point: Point | None = None
        self.error = ""
        self.log: list[dict[str, Any]] = []
        self._attach_log()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def _run(self) -> None:
        sc = self.session.scenario
        try:
            self.battle.run(max_av=sc.max_av, max_cycles=sc.max_cycles)
            self.point = None
            self.outbox.put(("end", self.snapshot(None)))
        except _Abort:
            return
        except BaseException:  # noqa: BLE001 - reported to the player
            self.outbox.put(("error", traceback.format_exc()))

    def next(self) -> tuple[str, Any]:
        try:
            return self.outbox.get(timeout=_TIMEOUT)
        except queue.Empty:
            return ("error", "the battle did not reach a decision point in time")

    def send(self, cmd: Any) -> tuple[str, Any]:
        self.inbox.put(cmd)
        return self.next()

    def stop(self) -> None:
        if self.thread.is_alive():
            self.inbox.put(_ABORT)
            self.thread.join(timeout=5)

    # ------------------------------------------------------------------- log
    def _attach_log(self) -> None:
        b = self.battle
        ev = b.events
        seq = itertools.count()

        def add(entry: dict[str, Any]) -> None:
            entry["i"] = next(seq)
            entry["time"] = round(b.time, 2)
            entry["cycle"] = b.cycle + 1
            self.log.append(entry)

        def name(e: Entity | None) -> str:
            return e.name if e is not None else ""

        def ref(e: Entity | None) -> str:
            return e.ref if e is not None else ""

        ev.on(E.WAVE_START, lambda e: add({"t": "wave", "n": b.wave_index + 1}), owner=self)
        ev.on(
            E.TURN_START,
            lambda e: add({"t": "turn", "who": ref(e.entity), "name": name(e.entity), "extra": bool(e.extra)}),
            owner=self,
        )

        def on_action(e: E.Ev) -> None:
            a = e.action
            add(
                {
                    "t": "action",
                    "who": ref(a.owner),
                    "actor": name(a.actor),
                    "kind": a.kind.value,
                    "label": a.label,
                    "label_cn": (a.skill or {}).get("name_cn", ""),
                    "target": name(a.target),
                    "sp": b.sp,
                }
            )

        ev.on(E.ACTION_START, on_action, owner=self)
        ev.on(E.ULT_USED, lambda e: add({"t": "ult", "who": ref(e.entity), "name": name(e.entity)}), owner=self)

        def on_dmg(e: E.Ev) -> None:
            r = e.record
            p = r.parts
            entry: dict[str, Any] = {
                "t": "dmg",
                "tref": ref(e.target),
                "oref": ref(e.credited),
                "owner": r.owner,
                "attacker": r.attacker,
                "label": r.label,
                "target": r.target,
                "amount": round(r.amount, 1),
                "element": r.element.value,
                "tags": sorted(r.tags),
            }
            if p is not None:
                entry["parts"] = {
                    k: round(getattr(p, k), 5)
                    for k in (
                        "base",
                        "dmg_boost",
                        "def_mult",
                        "res_mult",
                        "vuln_mult",
                        "mitig_mult",
                        "broken_mult",
                        "weaken_mult",
                        "crit_mult",
                        "extra_mult",
                        "elation_mult",
                        "merry_mult",
                        "punch_mult",
                        "punchline",
                    )
                }
            add(entry)

        ev.on(E.DAMAGE_DEALT, on_dmg, owner=self)

        def on_hit(e: E.Ev) -> None:
            h = e.hit
            for entry in reversed(self.log[-6:]):
                if entry["t"] == "dmg" and entry["target"] == h.target.name and entry["label"] == h.label:
                    if h.crit is not None:
                        entry["crit"] = bool(h.crit)
                    if h.toughness_reduced:
                        entry["tough"] = round(h.toughness_reduced, 2)
                    break

        ev.on(E.AFTER_HIT, on_hit, owner=self)
        ev.on(
            E.BREAK,
            lambda e: add(
                {
                    "t": "break",
                    "target": name(e.target),
                    "tref": ref(e.target),
                    "by": name(e.attacker),
                    "element": e.element.value,
                }
            ),
            owner=self,
        )
        ev.on(
            E.KILL,
            lambda e: add({"t": "kill", "target": name(e.target), "tref": ref(e.target), "by": name(e.killer)}),
            owner=self,
        )

        def on_mod(e: E.Ev) -> None:
            m = e.mod
            if m.kind == ModKind.OTHER and m.duration is None:
                return
            add(
                {
                    "t": "mod",
                    "name": m.name,
                    "target": name(e.target),
                    "tref": ref(e.target),
                    "kind": m.kind.value,
                    "duration": m.duration,
                    "stacks": m.stacks,
                    "source": name(m.source),
                }
            )

        ev.on(E.MOD_APPLIED, on_mod, owner=self)

        def on_heal(e: E.Ev) -> None:
            if e.effective > 0:
                add(
                    {
                        "t": "heal",
                        "target": name(e.entity),
                        "tref": ref(e.entity),
                        "amount": round(e.effective, 1),
                        "source": name(e.source),
                    }
                )

        ev.on(E.HEALED, on_heal, owner=self)

    # -------------------------------------------------------------- snapshot
    def snapshot(self, p: Point | None) -> dict[str, Any]:
        return serialize(self.battle, p, self.ctrl.settings)


# ================================================================================== session
class Session:
    """One interactive battle. Thread-safe for one caller at a time (the server holds a lock per session)."""

    def __init__(self, scenario: Scenario, team: list[Build], seed: int = 0, settings: dict[str, Any] | None = None):
        self.scenario = scenario
        self.team = team
        self.seed = seed
        self.initial_settings = _settings(settings)
        self.worker: _Worker | None = None
        self.shown: list[int] = []  # number of recorded decisions at each state shown to the player
        self.lock = threading.Lock()
        self.last: dict[str, Any] = {}

    # ----------------------------------------------------------------- api
    def start(self) -> dict[str, Any]:
        return self._restart([])

    def decide(self, decision: dict[str, Any], settings: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._send(("decide", decision, settings))

    def auto(self, mode: str, settings: dict[str, Any] | None = None) -> dict[str, Any]:
        if mode not in ("once", "ally_turn", "cycle", "wave", "end"):
            raise ValueError(f"unknown auto mode {mode!r}")
        return self._send(("auto", mode, settings))

    def undo(self, steps: int = 1) -> dict[str, Any]:
        """Go back ``steps`` decision points (after a crash: rebuild the last good point)."""
        if self.worker is None or not self.shown:
            return self.state()
        if self.last.get("fatal"):
            shown = list(self.shown)
        elif len(self.shown) <= 1:
            return self.state()
        else:
            shown = self.shown[: max(1, len(self.shown) - steps)]
        script = self.worker.ctrl.recorded[: shown[-1]]
        self.shown = shown
        return self._restart(script, count_shown=False)

    def state(self) -> dict[str, Any]:
        return self.last

    def close(self) -> None:
        if self.worker is not None:
            self.worker.stop()

    @property
    def decisions(self) -> list[dict[str, Any]]:
        return self.worker.ctrl.recorded if self.worker is not None else []

    # ------------------------------------------------------------- internals
    def _restart(self, script: list[dict[str, Any]], count_shown: bool = True) -> dict[str, Any]:
        if self.worker is not None:
            self.worker.stop()
        self.worker = _Worker(self, script)
        self.worker.start()
        if count_shown:
            self.shown = []
        return self._publish(self.worker.next())

    def _send(self, cmd: tuple[str, Any, Any]) -> dict[str, Any]:
        w = self.worker
        if w is None or not w.thread.is_alive() or w.point is None:
            return self.state()
        return self._publish(w.send(cmd))

    def _publish(self, msg: tuple[str, Any]) -> dict[str, Any]:
        kind, payload = msg
        w = self.worker
        assert w is not None
        if kind == "error":
            state = dict(self.last) if self.last else {}
            state["fatal"] = payload
            self.last = state
            return state
        state = payload
        state["log_total"] = len(w.log)
        state["diverged"] = w.ctrl.diverged
        state["error"] = w.error
        state["decisions"] = len(w.ctrl.recorded)
        if not self.shown or self.shown[-1] != len(w.ctrl.recorded):
            self.shown.append(len(w.ctrl.recorded))
        state["undo"] = len(self.shown) > 1
        self.last = state
        return state

    def log_since(self, since: int) -> list[dict[str, Any]]:
        return self.worker.log[since:] if self.worker is not None else []


# ============================================================================== serialisation
def _mod_state(m: Any) -> dict[str, Any]:
    stats = {}
    for k in list(m.stats)[:6]:
        v = m.value(k)
        if v:
            stats[k] = round(v, 4)
    return {
        "name": m.name,
        "kind": m.kind.value,
        "stacks": m.stacks,
        "max_stacks": m.max_stacks,
        "duration": m.duration,
        "tick": m.tick.value,
        "source": m.source.name if m.source is not None else "",
        "stats": stats,
        "dispellable": m.dispellable,
        "tags": sorted(t for t in m.tags if isinstance(t, str)),
        "hidden": m.kind == ModKind.OTHER and m.duration is None,
    }


def _kit_state(kit: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    skip = {"char", "opts", "gd", "state", "prefix"}
    for k, v in vars(kit).items():
        if k.startswith("_") or k in skip:
            continue
        if isinstance(v, bool) or (isinstance(v, (int, float)) and abs(v) < 1e15):
            out[k] = round(v, 3) if isinstance(v, float) else v
        elif isinstance(v, str) and len(v) < 40:
            out[k] = v
        elif isinstance(v, Entity):
            out[k] = v.name
    for k, v in getattr(kit, "state", {}).items():
        if isinstance(v, (bool, int, float, str)):
            out[k] = v
    return out


def _unit(e: Entity) -> dict[str, Any]:
    d: dict[str, Any] = {
        "ref": e.ref,
        "name": e.name,
        "side": e.side.value,
        "level": e.level,
        "hp": round(e.hp, 1),
        "max_hp": round(e.max_hp, 1) if e.max_hp else 0,
        "alive": e.alive,
        "targetable": e.targetable,
        "on_timeline": e.on_timeline,
        "av": round(e.av, 2) if e.spd > 0 else None,
        "spd": round(e.spd, 2),
        "mods": [_mod_state(m) for m in e.modifiers if not m.removed],
    }
    b = e.battle
    if b is not None:
        d["shield"] = round(b.shield_value(e), 1)
    el = getattr(e, "element", None)
    d["element"] = el.value if el is not None else ""
    return d


def _character(c: Character) -> dict[str, Any]:
    d = _unit(c)
    d.update(
        kind="char",
        id=c.char_id,
        name_cn=c.data.get("name_cn", ""),
        path=c.data.get("path", ""),
        slot=c.slot,
        eidolon=c.eidolon,
        enhanced=c.enhanced,
        energy=round(c.energy, 2),
        max_energy=c.max_energy,
    )
    kit = c.kit
    if kit is not None:
        d["ult_ready"] = bool(kit.ult_ready())
        cur, need, res_label = kit.ult_resource()
        d["ult_res"] = {"cur": round(float(cur), 2), "max": round(float(need), 2), "label": res_label}
        d["ult_target"] = kit.ult_target_kind()
        ult = kit.sk("ult")
        d["ult_name"] = ult["name"]
        d["ult_shape"] = str(ult.get("effect") or "")
        d["ult_name_cn"] = ult.get("name_cn", "")
        d["kit"] = _kit_state(kit)
    sheet = stat_sheet(c)
    d["stats"] = {k: round(v, 4) for k, v in sheet.items()}
    d["summons"] = [u.ref for u in c.summons]
    d["elation"] = _elation_of(c)
    return d


def _elation_of(c: Character) -> dict[str, Any] | None:
    """Elation-path resources of a character: Elation (欢愉度), Merrymake (增笑) and Certified Banger (好活当赏)."""
    bangers = [m for m in c.modifiers if m.name == "Certified Banger" and not m.removed]
    if c.path != Path.ELATION and not bangers:
        return None
    return {
        "elation": round(c.stat(S.ELATION_DMG_PCT), 4),
        "merrymake": round(c.stat(S.MERRYMAKE_PCT), 4),
        "banger": ElationSystem.certified_banger(c),
        "banger_stacks": [
            {"p": round(float(m.data.get("punchline", 0)), 1), "turns": m.duration}
            for m in bangers
            if m.data.get("punchline", 0)
        ],
    }


def _team_elation(b: Battle) -> dict[str, Any] | None:
    """Team-wide Elation state: Punchline (笑点) and Aha."""
    el = b.elation
    if not el.enabled and el.punchline <= 0:
        return None
    return {
        "punchline": el.punchline,
        "chars": len(el.elation_chars()),
        "aha": bool(el.aha.on_timeline),
        "aha_spd": round(el.aha.spd, 1),
        "instants": el.instants,
    }


def _enemy(e: Enemy) -> dict[str, Any]:
    d = _unit(e)
    d.update(
        kind="enemy",
        rank=e.rank.value if hasattr(e.rank, "value") else str(e.rank),
        toughness=round(e.toughness, 2),
        max_toughness=round(e.max_toughness, 2),
        broken=e.broken,
        weaknesses=[w.value for w in e.weaknesses],
        res={el.value: round(e.res_to(el), 3) for el in Element},
        effect_res=round(e.stat(S.EFFECT_RES), 3),
        slot=e.slot,
    )
    return d


def _summon(u: Summon) -> dict[str, Any]:
    d = _unit(u)
    owner = getattr(u, "owner", None)
    d.update(
        kind="summon" if owner is not None else "aha",  # Elation's Aha belongs to no character
        owner=owner.ref if owner is not None else "",
        memosprite=bool(getattr(u, "is_memosprite", False)),
        stat_mode=getattr(u, "stat_mode", ""),
    )
    return d


def _order(b: Battle, n: int = 12) -> list[dict[str, Any]]:
    """Predicted action order (next ``n`` turns) from the current gauges and speeds."""
    ents = [e for e in b.timeline() if e.spd > 0]
    heap = [(e.av, i, e) for i, e in enumerate(ents)]
    out = []
    for _ in range(n):
        if not heap:
            break
        heap.sort(key=lambda x: (round(x[0], 6), x[1]))
        av, i, e = heap.pop(0)
        out.append({"ref": e.ref, "name": e.name, "av": round(av, 1), "side": e.side.value})
        heap.append((av + AV_BASE / e.spd, i, e))
    return out


def _menu_state(items: list[MenuItem]) -> list[dict[str, Any]]:
    return [m.to_dict() for m in items]


def serialize(b: Battle, p: Point | None, settings: dict[str, Any]) -> dict[str, Any]:
    by_owner: dict[str, float] = {}
    for r in b.records:
        by_owner[r.owner] = by_owner.get(r.owner, 0.0) + r.amount
    state: dict[str, Any] = {
        "time": round(b.time, 2),
        "cycle": b.cycle + 1,
        "cycle_limit": None,
        "wave": b.wave_index + 1,
        "waves": len(b.waves),
        "sp": b.sp,
        "max_sp": b.max_sp,
        "turns": b.turns,
        "finished": b.finished or p is None,
        "cleared": b.cleared_at is not None,
        "total": round(sum(by_owner.values()), 1),
        "by_owner": {k: round(v, 1) for k, v in by_owner.items()},
        "allies": [_character(c) for c in b.team],
        "summons": [_summon(u) for u in b.units],
        "enemies": [_enemy(e) for e in b.enemies],
        "order": _order(b),
        "settings": copy.deepcopy(settings),
        # an Ultimate's inserted extra turn is resolving: Ultimates tried now are cast when it is over
        "elation": _team_elation(b),
        "ult_locked": b.ults_locked,
        "deferred_ults": [c.ref for c, _ in b.deferred_ults],
        "point": None,
    }
    if p is not None:
        pt: dict[str, Any] = {"kind": p.kind, "where": p.where, "extra_turn": p.extra_turn}
        if p.actor is not None:
            pt["actor"] = p.actor.ref
            pt["actor_name"] = p.actor.name
            pt["menu"] = _menu_state(b._menu_of(p.actor) or [])
        if p.subject is not None:
            pt["subject"] = p.subject.ref
            pt["subject_name"] = p.subject.name
            pt["subject_side"] = p.subject.side.value
        if p.kind == "window" and p.where == "queue":
            pt["queued"] = [q.label for q in b.queue]
        state["point"] = pt
    return state


__all__ = ["Session", "serialize", "DEFAULT_SETTINGS", "Point"]
