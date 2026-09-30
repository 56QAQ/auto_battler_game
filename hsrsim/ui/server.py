"""Local web UI: a small JSON API over :mod:`hsrsim.session` plus the static front end.

Run with ``python -m hsrsim ui`` (standard library only; binds to 127.0.0.1 by default).

API (JSON)::

    GET  /api/catalog                      characters, light cones, relic sets, stat options, endgame stages
    GET  /api/character/<id>[?enhanced=1]  skill / trace / eidolon texts with parameters filled in
    GET  /api/endgame/<mode>/<group>/<floor>/<half>  enemies of one endgame node
    POST /api/preview        {build}       stat sheet of one build (+ notes / error)
    POST /api/session        {config, settings}            -> state (+ log)
    POST /api/session/<sid>/decide  {decision, settings, since}
    POST /api/session/<sid>/auto    {mode, settings, since}
    POST /api/session/<sid>/undo    {steps}                -> state with the full log
    GET  /api/session/<sid>?since=N
    DELETE /api/session/<sid>

``config`` uses the same schema as the CLI's YAML/JSON configs (``team`` / ``scenario`` / ``config``).
"""

from __future__ import annotations

import json
import re
import threading
import traceback
import uuid
from functools import lru_cache
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .. import stats as S
from ..build import Build, make_character, stat_sheet
from ..cli import scenario_from, team_from
from ..data import get_data
from ..equipment import LIGHT_CONES, RELIC_SETS, load_gear
from ..kits import ENHANCED_KITS, load_all
from ..session import Session

STATIC = Path(__file__).resolve().parent / "static"
MAX_SESSIONS = 24

MAIN_STATS: dict[str, list[tuple[str, str, str]]] = {
    # slot: (config key, EN label, CN label)
    "body": [
        ("crit_rate", "CRIT Rate", "暴击率"),
        ("crit_dmg", "CRIT DMG", "暴击伤害"),
        ("atk%", "ATK%", "攻击力%"),
        ("hp%", "HP%", "生命值%"),
        ("def%", "DEF%", "防御力%"),
        ("ehr", "Effect Hit Rate", "效果命中"),
        ("heal", "Outgoing Healing", "治疗量加成"),
    ],
    "feet": [
        ("spd", "SPD", "速度"),
        ("atk%", "ATK%", "攻击力%"),
        ("hp%", "HP%", "生命值%"),
        ("def%", "DEF%", "防御力%"),
    ],
    "sphere": [
        ("elemental", "Elemental DMG", "属性伤害加成"),
        ("atk%", "ATK%", "攻击力%"),
        ("hp%", "HP%", "生命值%"),
        ("def%", "DEF%", "防御力%"),
    ],
    "rope": [
        ("atk%", "ATK%", "攻击力%"),
        ("err", "Energy Regen", "能量恢复效率"),
        ("break_effect", "Break Effect", "击破特攻"),
        ("hp%", "HP%", "生命值%"),
        ("def%", "DEF%", "防御力%"),
    ],
}
SUBSTATS: list[tuple[str, str, str, str]] = [
    # config key, datamine property, EN, CN
    ("crit_rate", "CriticalChanceBase", "CRIT Rate", "暴击率"),
    ("crit_dmg", "CriticalDamageBase", "CRIT DMG", "暴击伤害"),
    ("atk%", "AttackAddedRatio", "ATK%", "攻击力%"),
    ("hp%", "HPAddedRatio", "HP%", "生命值%"),
    ("def%", "DefenceAddedRatio", "DEF%", "防御力%"),
    ("spd", "SpeedDelta", "SPD", "速度"),
    ("break_effect", "BreakDamageAddedRatioBase", "Break Effect", "击破特攻"),
    ("ehr", "StatusProbabilityBase", "Effect Hit Rate", "效果命中"),
    ("effect_res", "StatusResistanceBase", "Effect RES", "效果抵抗"),
    ("atk", "AttackDelta", "ATK", "攻击力"),
    ("hp", "HPDelta", "HP", "生命值"),
    ("def", "DefenceDelta", "DEF", "防御力"),
]


# ================================================================================ catalog
_PARAM = re.compile(r"#(\d+)\[(i|f\d)\](%?)")


def fill(desc: str, params: list[Any]) -> str:
    """Replace ``#1[i]%`` placeholders of a description with the parameter values."""

    def rep(m: re.Match[str]) -> str:
        i = int(m.group(1)) - 1
        if i >= len(params):
            return m.group(0)
        v = params[i]
        v = v[0] if isinstance(v, list) else v
        pct = m.group(3) == "%"
        x = float(v) * (100 if pct else 1)
        fmt = m.group(2)
        s = f"{x:.{int(fmt[1])}f}" if fmt.startswith("f") else (f"{x:.0f}" if abs(x - round(x)) < 1e-6 else f"{x:g}")
        return s + ("%" if pct else "")

    return _PARAM.sub(rep, desc or "")


@lru_cache(maxsize=1)
def catalog() -> dict[str, Any]:
    gd = get_data()
    load_gear()
    kits = load_all()
    chars = []
    for cid, c in gd.characters.items():
        kit = kits.get(cid)
        chars.append(
            {
                "id": cid,
                "name": c["name"],
                "name_cn": c["name_cn"],
                "path": c["path"],
                "element": c["element"],
                "rarity": c["rarity"],
                "max_energy": c["max_energy"],
                "enhanced": "enhanced" in c and cid in ENHANCED_KITS,
                "implemented": kit is not None,
                "options": dict(getattr(kit, "default_opts", {})) if kit else {},
            }
        )
    lcs = [
        {
            "id": lid,
            "name": lc["name"],
            "name_cn": lc["name_cn"],
            "path": lc["path"],
            "rarity": lc["rarity"],
            "effect": lid in LIGHT_CONES,
        }
        for lid, lc in gd.light_cones.items()
    ]
    relics = [
        {
            "id": rid,
            "name": r["name"],
            "name_cn": r["name_cn"],
            "planar": bool(r["planar"]),
            "effect": rid in RELIC_SETS,
        }
        for rid, r in gd.relic_sets.items()
    ]
    subs = [
        {"key": k, "label": en, "label_cn": cn, "roll": round(gd.relic_sub_roll(prop), 6)}
        for k, prop, en, cn in SUBSTATS
    ]
    mains = {slot: [{"key": k, "label": en, "label_cn": cn} for k, en, cn in opts] for slot, opts in MAIN_STATS.items()}
    return {
        "version": gd.version,
        "characters": sorted(chars, key=lambda c: (-int(c["rarity"]), c["name"])),
        "light_cones": sorted(lcs, key=lambda x: (-int(x["rarity"]), x["name"])),
        "relic_sets": relics,
        "main_stats": mains,
        "substats": subs,
        "endgame": endgame_index(),
        "elements": ["Physical", "Fire", "Ice", "Thunder", "Wind", "Quantum", "Imaginary"],
    }


def _monster(m: dict[str, Any]) -> dict[str, Any]:
    keys = ("name", "rank", "level", "hp", "atk", "spd", "toughness", "weaknesses", "res", "effect_res")
    out = {k: m[k] for k in keys if k in m}
    out["initial_delay"] = m.get("initial_delay", 1.0)
    out["hit_energy"] = m.get("hit_energy")
    return out


def endgame_index() -> dict[str, Any]:
    """Modes -> groups -> floors -> halves (weakness hints only; stage details via :func:`endgame_stage`)."""
    gd = get_data()
    out: dict[str, Any] = {}
    for mode, groups in gd.endgame.items():
        out[mode] = [
            {
                "group": g["group"],
                "begin": g["begin"],
                "end": g["end"],
                "floors": [
                    {
                        "floor": fl["floor"],
                        "cycles": fl.get("cycles"),
                        "halves": [h["weakness_hint"] for h in fl["halves"]],
                    }
                    for fl in g["floors"]
                ],
            }
            for g in groups
        ]
    return out


def endgame_stage(mode: str, group: int, floor: int, half: int) -> dict[str, Any]:
    """Waves of one endgame node (infinite Pure Fiction waves are marked ``infinite``)."""
    gd = get_data()
    g = next(x for x in gd.endgame[mode] if int(x["group"]) == group)
    fl = next(x for x in g["floors"] if int(x["floor"]) == floor)
    h = fl["halves"][half - 1]
    waves: list[Any] = []
    for st in h["stages"]:
        if st.get("infinite"):
            for w in st["infinite"]:
                waves.append(
                    {
                        "infinite": True,
                        "max_count": w["max_count"],
                        "on_field": w["on_field"],
                        "monsters": [_monster(m) for m in w["monsters"]],
                    }
                )
        else:
            waves += [[_monster(m) for m in wave] for wave in st["waves"]]
    return {"weakness_hint": h["weakness_hint"], "cycles": fl.get("cycles"), "waves": waves}


def character_info(key: str, enhanced: bool = False) -> dict[str, Any]:
    gd = get_data()
    c = gd.character(key)
    src = c["enhanced"] if enhanced and "enhanced" in c else c
    skills = []
    for sid in src["skills"]:
        s = gd.skills.get(sid)
        if s is None or s["type"] in ("MazeNormal",):
            continue
        cap = 10 if s["type"] in ("BPSkill", "Ultra", "Talent") else 6  # max player level without eidolons
        lv = s["params"][min(len(s["params"]), cap) - 1] if s["params"] else []
        skills.append(
            {
                "id": sid,
                "type": s["type"],
                "type_text": s.get("type_text", ""),
                "name": s["name"],
                "name_cn": s.get("name_cn", ""),
                "desc": fill(s.get("desc", ""), lv),
                "desc_cn": fill(s.get("desc_cn", ""), lv),
                "energy": s.get("energy"),
                "toughness": s.get("toughness"),
            }
        )
    traces = []
    for tid in src["traces"]:
        t = gd.traces[tid]
        if t.get("type") == 3:
            traces.append(
                {
                    "id": tid,
                    "name": t["name"],
                    "name_cn": t.get("name_cn", ""),
                    "desc": fill(t.get("desc", ""), t["params"]),
                    "desc_cn": fill(t.get("desc_cn", ""), t["params"]),
                }
            )
    ranks = []
    for n, rid in enumerate(src["ranks"], 1):
        r = gd.ranks.get(rid)
        if r:
            ranks.append(
                {
                    "rank": n,
                    "name": r["name"],
                    "name_cn": r.get("name_cn", ""),
                    "desc": fill(r["desc"], r["params"]),
                    "desc_cn": fill(r.get("desc_cn", ""), r["params"]),
                }
            )
    return {
        "id": c["id"],
        "name": c["name"],
        "name_cn": c["name_cn"],
        "skills": skills,
        "traces": traces,
        "ranks": ranks,
    }


def preview(build: dict[str, Any]) -> dict[str, Any]:
    b = dict(build)
    name = b.pop("character")
    try:
        char = make_character(Build(name, **b))
    except Exception as exc:  # noqa: BLE001 - reported to the editor
        return {"error": f"{type(exc).__name__}: {exc}"}
    sheet = stat_sheet(char)
    extra = {
        "Break Efficiency": char.stat(S.BREAK_EFF),
        "Outgoing Healing": char.stat(S.HEAL_PCT),
        "All-Type DMG": char.stat(S.DMG_PCT),
    }
    return {
        "stats": {k: round(v, 4) for k, v in sheet.items()},
        "extra": {k: round(v, 4) for k, v in extra.items() if v},
        "notes": list(char.build_notes),
        "max_energy": char.max_energy,
    }


# ================================================================================== server
class App:
    def __init__(self) -> None:
        self.sessions: dict[str, Session] = {}
        self.order: list[str] = []
        self.lock = threading.Lock()

    def new_session(self, body: dict[str, Any]) -> dict[str, Any]:
        cfg = body.get("config") or {}
        scenario = scenario_from(cfg)
        team = team_from(cfg)
        seed = int((cfg.get("config") or {}).get("seed", 0))
        sess = Session(scenario, team, seed=seed, settings=body.get("settings"))
        sid = uuid.uuid4().hex[:12]
        with self.lock:
            self.sessions[sid] = sess
            self.order.append(sid)
            while len(self.order) > MAX_SESSIONS:
                old = self.sessions.pop(self.order.pop(0), None)
                if old is not None:
                    old.close()
        with sess.lock:
            state = sess.start()
            return self._out(sid, sess, state, 0)

    def get(self, sid: str) -> Session:
        s = self.sessions.get(sid)
        if s is None:
            raise KeyError("session not found (the server may have restarted)")
        return s

    @staticmethod
    def _out(sid: str, sess: Session, state: dict[str, Any], since: int) -> dict[str, Any]:
        out = dict(state)
        out["sid"] = sid
        out["log_from"] = since
        out["log"] = sess.log_since(since)
        out["scenario"] = {
            "name": sess.scenario.name,
            "cycles": sess.scenario.max_cycles,
            "desc": sess.scenario.description,
        }
        return out

    def handle(self, method: str, path: str, query: dict[str, list[str]], body: dict[str, Any]) -> Any:
        parts = [p for p in path.split("/") if p]
        if parts[:1] != ["api"]:
            raise KeyError(path)
        route = parts[1:]
        if method == "GET" and route == ["catalog"]:
            return catalog()
        if method == "GET" and len(route) == 2 and route[0] == "character":
            return character_info(route[1], enhanced=query.get("enhanced", ["0"])[0] in ("1", "true"))
        if method == "GET" and len(route) == 5 and route[0] == "endgame":
            return endgame_stage(route[1], int(route[2]), int(route[3]), int(route[4]))
        if method == "POST" and route == ["preview"]:
            return preview(body.get("build") or body)
        if method == "POST" and route == ["session"]:
            return self.new_session(body)
        if len(route) >= 2 and route[0] == "session":
            sid = route[1]
            sess = self.get(sid)
            since = int(body.get("since", query.get("since", ["0"])[0]))
            with sess.lock:
                if method == "GET" and len(route) == 2:
                    return self._out(sid, sess, sess.state(), since)
                if method == "DELETE" and len(route) == 2:
                    sess.close()
                    self.sessions.pop(sid, None)
                    return {"ok": True}
                if method == "POST" and route[2:] == ["decide"]:
                    return self._out(sid, sess, sess.decide(body["decision"], body.get("settings")), since)
                if method == "POST" and route[2:] == ["auto"]:
                    return self._out(sid, sess, sess.auto(str(body.get("mode", "once")), body.get("settings")), since)
                if method == "POST" and route[2:] == ["undo"]:
                    return self._out(sid, sess, sess.undo(int(body.get("steps", 1))), 0)
        raise KeyError(path)


def make_handler(app: App) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "hsrsim-ui"

        def log_message(self, fmt: str, *args: Any) -> None:  # quiet
            pass

        def _send(self, code: int, payload: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def _json(self, code: int, obj: Any) -> None:
            self._send(code, json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8"), "application/json")

        def _api(self, method: str) -> None:
            u = urlparse(self.path)
            body: dict[str, Any] = {}
            n = int(self.headers.get("Content-Length") or 0)
            if n:
                body = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
            try:
                self._json(200, app.handle(method, u.path, parse_qs(u.query), body))
            except KeyError as exc:
                self._json(404, {"error": str(exc)})
            except (ValueError, TypeError) as exc:
                self._json(400, {"error": f"{type(exc).__name__}: {exc}"})
            except Exception as exc:  # noqa: BLE001
                self._json(500, {"error": f"{type(exc).__name__}: {exc}", "trace": traceback.format_exc()})

        def do_GET(self) -> None:  # noqa: N802
            u = urlparse(self.path)
            if u.path.startswith("/api/"):
                self._api("GET")
                return
            name = "index.html" if u.path in ("/", "") else u.path.lstrip("/").removeprefix("static/")
            f = (STATIC / name).resolve()
            if STATIC not in f.parents or not f.is_file():
                self._send(HTTPStatus.NOT_FOUND, b"not found", "text/plain")
                return
            ctype = {
                ".html": "text/html; charset=utf-8",
                ".js": "text/javascript; charset=utf-8",
                ".css": "text/css; charset=utf-8",
                ".svg": "image/svg+xml",
            }.get(f.suffix, "application/octet-stream")
            self._send(200, f.read_bytes(), ctype)

        def do_POST(self) -> None:  # noqa: N802
            self._api("POST")

        def do_DELETE(self) -> None:  # noqa: N802
            self._api("DELETE")

    return Handler


def serve(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    app = App()
    httpd = ThreadingHTTPServer((host, port), make_handler(app))
    url = f"http://{host}:{httpd.server_address[1]}/"
    print(f"hsrsim UI: {url}  (Ctrl+C to stop)")
    catalog()  # warm the data before the first request
    if open_browser:
        import webbrowser

        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        for s in list(app.sessions.values()):
            s.close()
