"""Summarise a character's in-game ability script (Config/ConfigAbility) for auditing kits.

The game's real skill logic is a JSON "visual script": abilities, modifiers with lifetimes and
event callbacks, property changes. This tool downloads the script of a character and prints the
parts that matter for combat logic (presentation-only operations are skipped):

* every modifier: LifeTime / LifeStepMoment / Stacking / MaxLayer, the events it listens to and the
  properties it changes (StackProperty ...),
* ability entry points and the gameplay operations they run.

Usage::

    python tools/ability_summary.py Seele            # base kit
    python tools/ability_summary.py "Seele+"         # enhanced kit
    python tools/ability_summary.py Acheron --grep Passive
    python tools/ability_summary.py "Jingliu+" --grep PassiveAtkReady --full   # no truncation
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hsrsim.data import get_data  # noqa: E402

RAW = "https://raw.githubusercontent.com/DimbreathBot/turnbasedgamedata/main/"
PRESENTATION = (
    "Effect",
    "Anim",
    "Camera",
    "Sound",
    "UI",
    "Wait",
    "LookAt",
    "Visible",
    "Blur",
    "Intensity",
    "Formation",
    "Preload",
    "Preshow",
    "EnergyBar",
    "Audio",
    "Timeline",
    "Scale",
    "Light",
    "Emotion",
    "Shake",
    "Model",
)


def fetch(path: str, cache: Path) -> Any:
    dest = cache / path.replace("/", "_")
    if not dest.exists():
        cache.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(RAW + path, timeout=120) as resp:  # noqa: S310
            dest.write_bytes(resp.read())
    return json.loads(dest.read_text(encoding="utf-8"))


def op_name(o: dict[str, Any]) -> str:
    return str(o.get("$type", "")).rsplit(".", 1)[-1]


def gameplay_ops(o: Any, out: list[str], depth: int = 0) -> None:
    """Collect gameplay-relevant operation names (with a few key fields) recursively."""
    if isinstance(o, dict):
        name = op_name(o)
        if name and not any(p in name for p in PRESENTATION) and name != "TargetAlias":
            detail = ""
            for k in ("ModifierName", "AbilityName", "Property", "PropertyName", "DynamicKey", "Event"):
                v = o.get(k)
                if isinstance(v, dict):
                    v = v.get("Value")
                if v:
                    detail += f" {k}={v}"
            ap = o.get("AttackProperty")
            if name == "DamageByAttackProperty" and isinstance(ap, dict):
                hs = ap.get("HitSplitRatio") or {}
                split = "dynamic" if hs.get("IsDynamic") else hs.get("FixedValue", {}).get("Value")
                dtype = (ap.get("DamageType") or {}).get("DamageType")
                detail += f" split={split} type={dtype} target={o.get('TargetType', {}).get('Alias')}"
            out.append("  " * depth + name + detail)
        for v in o.values():
            gameplay_ops(v, out, depth + (1 if name else 0))
    elif isinstance(o, list):
        for v in o:
            gameplay_ops(v, out, depth)


def summarize(data: dict[str, Any], grep: str | None, limit: int | None = 30) -> None:
    def clip(ops: list[str], n: int | None, pad: str) -> str:
        return "\n".join(ops[:n]) + (f"\n{pad}..." if n is not None and len(ops) > n else "")

    for ab in data.get("AbilityList", []):
        mods = ab.get("Modifiers") or {}
        for name, m in mods.items():
            if grep and grep.lower() not in name.lower():
                continue
            life = m.get("LifeTime", {})
            life_v = life.get("FixedValue", {}).get("Value") if isinstance(life, dict) else life
            print(f"MODIFIER {name}")
            print(
                f"  LifeTime={life_v if life_v is not None else ('dynamic' if life else '-')}"
                f"  LifeStepMoment={m.get('LifeStepMoment', 'default(turn end)')}"
                f"  Stacking={m.get('Stacking', '-')}  MaxLayer={m.get('MaxLayer', '-')}"
                f"  StatusType={m.get('StatusType', '-')}"
            )
            for cb in m.get("_CallbackList", []):
                ops: list[str] = []
                gameplay_ops(cb.get("CallbackConfig", []), ops, 2)
                if ops:
                    print(f"  on {cb.get('Event')}:")
                    print(clip(ops, limit and limit - 5, "      "))
        name = ab.get("Name", "")
        if name and (not grep or grep.lower() in name.lower()):
            ops = []
            gameplay_ops(ab.get("OnStart", []), ops, 1)
            if ops:
                print(f"ABILITY {name}")
                print(clip(ops, limit, "    "))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("character")
    ap.add_argument("--grep", help="only modifiers/abilities whose name contains this")
    ap.add_argument("--cache", type=Path, default=Path(".cache/ability"))
    ap.add_argument("--full", action="store_true", help="do not truncate long operation lists")
    args = ap.parse_args()
    enhanced = args.character.endswith("+")
    c = get_data().character(args.character.rstrip("+"))
    cfg = c["enhanced"]["config"] if enhanced else c["config"]
    path = cfg.replace("ConfigCharacter", "ConfigAbility").replace("_Config.json", "_Ability.json")
    print(f"# {c['name']}{' (enhanced)' if enhanced else ''}: {path}")
    summarize(fetch(path, args.cache), args.grep, None if args.full else 30)


if __name__ == "__main__":
    main()
