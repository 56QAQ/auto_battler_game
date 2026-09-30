"""Print light cone passives with parameters filled in.

Usage: python tools/lcinfo.py [PATH ...]      (paths: Rogue Warrior Mage Shaman Warlock Knight Priest Memory Elation)
       python tools/lcinfo.py --id 23001 ...
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hsrsim.data import get_data  # noqa: E402


def fill(desc: str, params: list[float]) -> str:
    def rep(m: re.Match[str]) -> str:
        i = int(m.group(1)) - 1
        v = params[i] if i < len(params) else "?"
        if isinstance(v, (int, float)) and m.group(3) == "%":
            return f"{v * 100:g}%"
        return f"{v:g}" if isinstance(v, (int, float)) else str(v)

    return re.sub(r"#(\d+)\[(\w+)\](%?)", rep, desc)


def main() -> None:
    gd = get_data()
    args = sys.argv[1:]
    ids = set(args[args.index("--id") + 1 :]) if "--id" in args else None
    paths = set(args) if args and ids is None else None
    for k, v in sorted(gd.light_cones.items(), key=lambda kv: (kv[1]["path"], -kv[1]["rarity"], kv[0])):
        if ids is not None and k not in ids:
            continue
        if paths is not None and v["path"] not in paths:
            continue
        print(f"{k} {v['rarity']}* {v['path']} {v['name']} / {v['name_cn']}")
        print(f"    S1 params={v['params'][0]}  S5 params={v['params'][-1]}  static props S1={v['props'][0]}")
        print("    " + fill(v["desc"] or "", v["params"][0]).replace("\n", " "))


if __name__ == "__main__":
    main()
