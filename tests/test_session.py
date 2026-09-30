"""Manual control: controller hooks, interactive sessions (decisions, Ultimate insertion, undo, auto) and the UI API."""

import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from hsrsim.battle import Battle, BattleConfig
from hsrsim.build import Build, make_character
from hsrsim.control import Controller, Decision, target_kind
from hsrsim.data import get_data
from hsrsim.entities import Enemy
from hsrsim.enums import Element
from hsrsim.scenarios import aoe_dps, boss_dps
from hsrsim.session import Session
from hsrsim.ui.server import App, catalog, fill, make_handler

TEAM = [Build("Seele"), Build("Bronya"), Build("Silver Wolf"), Build("Huohuo")]


def _strip(state):
    return {k: v for k, v in state.items() if k not in ("log", "log_total", "decisions", "undo", "error")}


# ----------------------------------------------------------------------------- controller
class Script(Controller):
    """Records every decision point and answers from a small policy."""

    def __init__(self):
        self.points = []

    def turn(self, battle, actor, extra_turn):
        self.points.append(("turn", actor.ref))
        return Decision("act", item="basic", target=battle.alive_enemies()[0].ref)

    def window(self, battle, where, subject):
        self.points.append((where, subject.ref if subject else ""))
        for c in battle.team:
            if c.kit.ult_ready():
                return Decision("ult", who=c.ref)
        return Decision("continue")


def test_controller_drives_turns_and_ult_windows():
    chars = [make_character(b) for b in TEAM]
    enemy = Enemy("Dummy", hp=1e12, toughness=1e6, weaknesses=list(Element))
    b = Battle(chars, [[enemy]], BattleConfig(start_energy=1.0))
    ctrl = Script()
    b.controller = ctrl
    b.run(max_cycles=2)
    turns = [p for p in ctrl.points if p[0] == "turn"]
    assert {r for _, r in turns} == {"a0", "a1", "a2", "a3"}
    assert ("before_turn", enemy.ref) in ctrl.points  # a window opens before the enemy acts
    assert all(c.energy < c.max_energy for c in chars)  # every full Ultimate was cast at the first window
    ult_actions = [r for r in b.records if "ult" in r.tags]
    assert ult_actions  # the Ultimates dealt damage


def test_refs_are_stable_and_target_kinds():
    gd = get_data()
    assert target_kind(gd.skills["110102"]) == "ally"  # Bronya: Combat Redeployment (one ally)
    assert target_kind(gd.skills["110103"]) == "allies"  # Bronya: The Belobog March (whole team)
    assert target_kind(gd.skills["110202"]) == "enemy"  # Seele: Sheathed Blade
    assert fill("Deals #1[i]% of ATK, #2[f1] turns", [2.2, 1.5]) == "Deals 220% of ATK, 1.5 turns"


# -------------------------------------------------------------------------------- session
def test_session_decisions_ult_insertion_undo_and_auto():
    s = Session(aoe_dps(cycles=4, count=3), TEAM, seed=3, settings={"pause": {"before_enemy": True}})
    try:
        st = s.start()
        first = _strip(st)
        assert st["point"]["kind"] == "turn" and st["point"]["menu"][0]["id"] == "basic"
        actor = st["point"]["actor"]
        target = st["enemies"][2]["ref"]
        st = s.decide({"kind": "act", "item": "skill", "target": target})
        assert st["decisions"] == 1 and not st["error"]
        acts = [e for e in s.log_since(0) if e["t"] == "action" and e["who"] == actor]
        assert acts[-1]["target"] == "Elite 3" and acts[-1]["kind"] == "skill"
        # an invalid decision is rejected without advancing
        again = s.decide({"kind": "act", "item": "no-such-action"})
        assert again["error"] and again["decisions"] == 1
        # undo returns exactly to the first decision point
        st = s.undo()
        assert _strip(st) == first and not st["diverged"]
        # play until an Ultimate is ready at a window, then insert it before the enemy's turn
        for _ in range(60):
            p = st["point"]
            if p is None:
                break
            if p["kind"] == "window":
                ready = [a for a in st["allies"] if a["ult_ready"]]
                assert ready
                who = ready[0]["ref"]
                st = s.decide({"kind": "ult", "who": who, "target": st["enemies"][0]["ref"]})
                assert any(e["t"] == "ult" and e["who"] == who for e in s.log_since(0))
                break
            st = s.decide({"kind": "act", "item": "basic", "target": st["enemies"][0]["ref"]})
        else:
            pytest.fail("no Ultimate window reached")
        before = st["decisions"]
        st = s.auto("cycle")
        assert st["decisions"] > before and st["cycle"] >= 2
        st = s.auto("end")
        assert st["point"] is None and st["finished"]
        st = s.undo()
        assert st["point"] is not None and not st["diverged"]
    finally:
        s.close()


def test_session_auto_ult_setting_and_pause_policy():
    s = Session(boss_dps(cycles=3), TEAM, settings={"auto_ult": {"a0": True, "a1": True, "a2": True, "a3": True}})
    try:
        st = s.start()
        # with every Ultimate on auto no window ever pauses: only turn points are shown
        for _ in range(40):
            if st["point"] is None:
                break
            assert st["point"]["kind"] == "turn"
            st = s.decide({"kind": "auto"})
        assert any(e["t"] == "ult" for e in s.log_since(0))
    finally:
        s.close()


# ------------------------------------------------------------------------------------ api
@pytest.fixture()
def server():
    app = App()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    for sess in app.sessions.values():
        sess.close()


def _call(url, body=None, method=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, method=method)
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def test_http_api_end_to_end(server):
    with urllib.request.urlopen(server + "/", timeout=10) as r:
        assert b"hsrsim" in r.read()
    cat = _call(server + "/api/catalog")
    assert len(cat["characters"]) == len(get_data().characters) and cat["names"]["Seele"] == "希儿"
    g = cat["endgame"]["moc"][-1]
    stage = _call(f"{server}/api/endgame/moc/{g['group']}/{g['floors'][-1]['floor']}/1")
    assert stage["waves"] and stage["waves"][0][0]["hp"] > 0
    info = _call(server + "/api/character/1102")
    assert info["skills"] and "#" not in info["skills"][0]["desc"]
    prev = _call(server + "/api/preview", {"build": {"character": "Seele", "eidolon": 1}})
    assert prev["stats"]["ATK"] > 0
    cfg = {"team": [{"character": "1102"}, {"character": "1101"}], "scenario": {"preset": "boss", "cycles": 3}}
    st = _call(server + "/api/session", {"config": cfg})
    sid = st["sid"]
    assert st["point"]["kind"] == "turn" and st["log"] is not None
    st2 = _call(
        f"{server}/api/session/{sid}/decide", {"decision": {"kind": "act", "item": "basic"}, "since": len(st["log"])}
    )
    assert st2["decisions"] == 1 and st2["log_from"] == len(st["log"])
    st3 = _call(f"{server}/api/session/{sid}/undo", {})
    assert st3["decisions"] == 0 and st3["log_from"] == 0
    st4 = _call(f"{server}/api/session/{sid}/auto", {"mode": "end"})
    assert st4["point"] is None
    assert _call(f"{server}/api/session/{sid}", method="DELETE")["ok"]


def test_catalog_is_light():
    assert len(json.dumps(catalog(), ensure_ascii=False)) < 400_000


def test_session_shows_elation_resources():
    team = [Build("Yao Guang"), Build("Pearl"), Build("Bronya"), Build("Huohuo")]
    s = Session(boss_dps(cycles=2), team, seed=1)
    try:
        st = s.start()
        el = st["elation"]
        assert el["chars"] == 2 and el["punchline"] >= 2 and el["aha"]
        by_name = {a["name"]: a for a in st["allies"]}
        yao = by_name["Yao Guang"]["elation"]
        assert yao["banger"] >= 20 and yao["banger_stacks"][0]["turns"] is not None
        assert by_name["Yao Guang"]["stats"]["Elation"] == pytest.approx(yao["elation"])
        assert by_name["Pearl"]["elation"]["banger_stacks"][0]["turns"] is None  # Pearl's never expire
        assert by_name["Bronya"]["elation"] is None and "Elation" not in by_name["Bronya"]["stats"]
    finally:
        s.close()
    s = Session(boss_dps(cycles=1), TEAM, seed=1)
    try:
        assert s.start()["elation"] is None  # no Elation character
    finally:
        s.close()
    assert catalog()["names"]["Certified Banger"] == "好活当赏"
