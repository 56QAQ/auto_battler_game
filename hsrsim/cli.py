"""Command line interface.

    python -m hsrsim run examples/seele_boss.yaml [--runs 20] [--seed 1] [-v] [--json out.json]
    python -m hsrsim stats examples/seele_boss.yaml
    python -m hsrsim list characters [--implemented]
    python -m hsrsim list lightcones | relics
    python -m hsrsim info Seele
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any

from .build import Build, make_character, stat_sheet
from .data import get_data
from .equipment import LIGHT_CONES, RELIC_SETS, load_gear
from .kits import load_all
from .report import Report
from .scenarios import PRESETS, EnemySpec, Scenario


def load_config(path: str) -> dict[str, Any]:
    text = Path(path).read_text(encoding="utf-8")
    if path.endswith((".yaml", ".yml")):
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover
            raise SystemExit("PyYAML is required for YAML configs (pip install pyyaml) or use JSON") from exc
        return yaml.safe_load(text)
    return json.loads(text)


def scenario_from(cfg: dict[str, Any]) -> Scenario:
    sc = dict(cfg.get("scenario", {"preset": "boss"}))
    battle_cfg = dict(cfg.get("config", {}))
    if "waves" in sc:
        waves = [[EnemySpec(**e) for e in wave] for wave in sc["waves"]]
        s = Scenario(sc.get("name", "custom"), waves, max_cycles=sc.get("cycles"), max_av=sc.get("max_av"))
    elif sc.get("preset") in ("moc", "pf", "as", "endgame"):
        mode = sc.pop("preset")
        mode = sc.pop("mode", "moc") if mode == "endgame" else mode
        s = PRESETS["endgame"](mode, group=sc.get("group"), floor=sc.get("floor"), half=int(sc.get("half", 1)))
        if "cycles" in sc:
            s.max_cycles = int(sc["cycles"])
    else:
        preset = sc.pop("preset", "boss")
        kw: dict[str, Any] = {}
        if "cycles" in sc:
            kw["cycles" if preset != "waves" else "max_cycles"] = sc.pop("cycles")
        if "weaknesses" in sc:
            kw["weaknesses"] = sc.pop("weaknesses")
        if preset == "aoe" and "count" in sc:
            kw["count"] = sc.pop("count")
        kw.update(sc.pop("enemy", {}))
        s = PRESETS[preset](**kw)
    s.config.update(battle_cfg)
    return s


def team_from(cfg: dict[str, Any]) -> list[Build]:
    team = []
    for m in cfg["team"]:
        m = dict(m)
        name = m.pop("character")
        team.append(Build(name, **m))
    return team


def run_many(scenario: Scenario, team: list[Build], runs: int, seed: int, verbose: bool) -> list[Report]:
    return [scenario.run(team, seed=seed + i, verbose=verbose and i == 0) for i in range(runs)]


def summarize(reports: list[Report]) -> str:
    if len(reports) == 1:
        return reports[0].to_text()
    totals = [r.total for r in reports]
    cycles = [r.cycles for r in reports]
    lines = [reports[0].to_text(), "", f"=== {len(reports)} runs (random effects re-rolled per seed) ==="]
    sd = statistics.pstdev(totals) if len(totals) > 1 else 0.0
    lines.append(f"Total DMG mean {statistics.fmean(totals):,.0f}  sd {sd:,.0f}  min {min(totals):,.0f}  max {max(totals):,.0f}")
    lines.append(f"Cycles mean {statistics.fmean(cycles):.2f}")
    by: dict[str, list[float]] = {}
    for r in reports:
        for k, v in r.by_owner().items():
            by.setdefault(k, []).append(v)
    for k, vs in sorted(by.items(), key=lambda kv: -statistics.fmean(kv[1])):
        lines.append(f"  {k:<28} mean {statistics.fmean(vs):>14,.0f}")
    return "\n".join(lines)


def cmd_run(args: argparse.Namespace) -> None:
    cfg = load_config(args.config)
    scenario = scenario_from(cfg)
    team = team_from(cfg)
    runs = args.runs or int(cfg.get("runs", 1))
    reports = run_many(scenario, team, runs, args.seed, args.verbose)
    print(f"Scenario: {scenario.name}  |  data version {get_data().version}")
    print(summarize(reports))
    if args.json:
        out = [r.to_dict() for r in reports]
        Path(args.json).write_text(json.dumps(out if runs > 1 else out[0], ensure_ascii=False, indent=2,
                                              default=_json_default), encoding="utf-8")
        print(f"\nwrote {args.json}")


def _json_default(o: Any) -> Any:
    if isinstance(o, float) and math.isinf(o):
        return None
    return str(o)


def cmd_stats(args: argparse.Namespace) -> None:
    cfg = load_config(args.config)
    for b in team_from(cfg):
        c = make_character(b)
        print(f"== {c.name} (E{c.eidolon}{', enhanced' if c.enhanced else ''})")
        for k, v in stat_sheet(c).items():
            shown = f"{v:,.1f}" if k in ("HP", "ATK", "DEF", "SPD") else f"{v:.1%}"
            print(f"  {k:<18} {shown}")
        for note in c.build_notes:
            print(f"  note: {note}")


def cmd_list(args: argparse.Namespace) -> None:
    gd = get_data()
    kits = load_all()
    load_gear()
    if args.what == "characters":
        for cid, c in sorted(gd.characters.items(), key=lambda kv: kv[0]):
            done = cid in kits
            if args.implemented and not done:
                continue
            enh = " [+enhanced kit]" if "enhanced" in c else ""
            print(f"{'*' if done else ' '} {cid}  {c['name']} / {c['name_cn']}  {c['path']} {c['element']}{enh}")
    elif args.what == "lightcones":
        for lid, lc in sorted(gd.light_cones.items()):
            done = lid in LIGHT_CONES
            if args.implemented and not done:
                continue
            print(f"{'*' if done else ' '} {lid}  {lc['rarity']}* {lc['path']:<8} {lc['name']} / {lc['name_cn']}")
    else:
        for sid, rs in sorted(gd.relic_sets.items()):
            done = sid in RELIC_SETS
            if args.implemented and not done:
                continue
            kind = "planar" if rs["planar"] else "relic"
            print(f"{'*' if done else ' '} {sid}  {kind:<6} {rs['name']} / {rs['name_cn']}")
    print("\n* = conditional effects implemented (everything else: static stats only / no kit)")


def cmd_info(args: argparse.Namespace) -> None:
    import subprocess

    tool = Path(__file__).resolve().parent.parent / "tools" / "kitinfo.py"
    subprocess.run([sys.executable, str(tool), *args.names], check=False)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="hsrsim", description="Honkai: Star Rail combat simulator")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run a scenario from a YAML/JSON config")
    r.add_argument("config")
    r.add_argument("--runs", type=int, default=0, help="number of seeds to average (default: config 'runs' or 1)")
    r.add_argument("--seed", type=int, default=0)
    r.add_argument("-v", "--verbose", action="store_true", help="print the battle log of the first run")
    r.add_argument("--json", help="write the report(s) as JSON")
    r.set_defaults(fn=cmd_run)
    s = sub.add_parser("stats", help="print the stat sheet of each team member")
    s.add_argument("config")
    s.set_defaults(fn=cmd_stats)
    li = sub.add_parser("list", help="list characters / light cones / relic sets")
    li.add_argument("what", choices=["characters", "lightcones", "relics"])
    li.add_argument("--implemented", action="store_true")
    li.set_defaults(fn=cmd_list)
    inf = sub.add_parser("info", help="print a character's kit data (skills, traces, eidolons)")
    inf.add_argument("names", nargs="+")
    inf.set_defaults(fn=cmd_info)
    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
