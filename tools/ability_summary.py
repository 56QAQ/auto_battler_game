"""Summarise a character's in-game ability script (Config/ConfigAbility) for auditing kits.

The game's real skill logic is a JSON "visual script": abilities, modifiers with lifetimes and
event callbacks, property changes. This tool downloads the script of a character and prints the
parts that matter for combat logic (presentation-only operations are skipped):

* every modifier: LifeTime / LifeStepMoment / Stacking / MaxLayer, the events it listens to and the
  properties it changes (StackProperty ...),
* ability entry points and the gameplay operations they run, with targets (``target=Caster``), static values
  (``MaxLoopCount=2``; ``dyn`` = computed from skill parameters), inverted conditions (``NOT``) and
  ``if`` / ``else`` branches,
* file-level ``GlobalModifiers`` (modifiers shared by several abilities) and, with ``--servant``, the memosprite script.

Usage::

    python tools/ability_summary.py Seele            # base kit
    python tools/ability_summary.py "Seele+"         # enhanced kit
    python tools/ability_summary.py Acheron --grep Passive
    python tools/ability_summary.py "Jingliu+" --grep PassiveAtkReady --full   # no truncation
    python tools/ability_summary.py Aglaea --servant                          # + memosprite script
    python tools/ability_summary.py x --file Config/ConfigAbility/Servant/Servant_AglaeaServant_00_Ability.json
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
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


# Fields printed as ``key=value`` when present (dict-wrapped values are unwrapped)
NAME_FIELDS = ("ModifierName", "AbilityName", "Property", "PropertyName", "DynamicKey", "Event", "Flag", "ValueType")
ENUM_FIELDS = ("CompareType", "RatioType", "FormulaType", "AttackType", "AttackTypes", "Stacking")
# Numeric fields: printed with their value when static, "dyn" when computed from dynamic values (skill params)
VALUE_FIELDS = (
    "MaxLoopCount",
    "CompareValue",
    "LifeTime",
    "Ratio",
    "Floor",
    "HealPercentage",
    "AddValue",
    "FixedAddValue",
    "PropertyValue",
    "Value",
    "Count",
    "Layer",
)


def _value(v: Any) -> Any:
    if isinstance(v, dict):
        if v.get("IsDynamic"):
            return "dyn"
        if "FixedValue" in v:
            return (v.get("FixedValue") or {}).get("Value", 0)
        if "Value" in v:
            return v["Value"]
    return v


def _detail(name: str, o: dict[str, Any]) -> str:
    detail = " NOT" if o.get("Inverse") else ""
    for k in NAME_FIELDS:
        v = o.get(k)
        if isinstance(v, dict):
            v = v.get("Value")
        if v:
            detail += f" {k}={v}"
    for k in ENUM_FIELDS:
        if o.get(k) not in (None, "", []):
            detail += f" {k}={o[k]}"
    for k in VALUE_FIELDS:
        if k in o and not isinstance(o[k], (list, str)):
            detail += f" {k}={_value(o[k])}"
    ap = o.get("AttackProperty")
    if name == "DamageByAttackProperty" and isinstance(ap, dict):
        hs = ap.get("HitSplitRatio") or {}
        split = "dynamic" if hs.get("IsDynamic") else hs.get("FixedValue", {}).get("Value")
        dtype = (ap.get("DamageType") or {}).get("DamageType")
        detail += f" split={split} type={dtype}"
    tt = o.get("TargetType")
    if isinstance(tt, dict) and tt.get("Alias"):
        detail += f" target={tt['Alias']}"
    return detail


def gameplay_ops(o: Any, out: list[str], depth: int = 0) -> None:
    """Collect gameplay-relevant operations (with their key fields) recursively.

    ``PredicateTaskList`` is printed as ``if <predicate>`` / ``else`` so that the branches are distinguishable.
    """
    if isinstance(o, dict):
        name = op_name(o)
        if name == "PredicateTaskList":
            cond: list[str] = []
            gameplay_ops(o.get("Predicate"), cond, 0)
            out.append(
                "  " * depth + "if " + " / ".join(c.strip() for c in cond[:4]) + (" ..." if len(cond) > 4 else "")
            )
            gameplay_ops(o.get("SuccessTaskList"), out, depth + 1)
            if o.get("FailedTaskList"):
                out.append("  " * depth + "else")
                gameplay_ops(o.get("FailedTaskList"), out, depth + 1)
            return
        shown = bool(name) and not any(p in name for p in PRESENTATION) and name != "TargetAlias"
        if shown:
            out.append("  " * depth + name + _detail(name, o))
        for k, v in o.items():
            if k in ("TargetType", "AttackProperty") or (k in VALUE_FIELDS and not isinstance(v, list)):
                continue
            gameplay_ops(v, out, depth + (1 if shown else 0))
    elif isinstance(o, list):
        for v in o:
            gameplay_ops(v, out, depth)


def _print_modifier(name: str, m: dict[str, Any], limit: int | None) -> None:
    life = m.get("LifeTime", {})
    life_v = life.get("FixedValue", {}).get("Value") if isinstance(life, dict) else life
    print(f"MODIFIER {name}")
    print(
        f"  LifeTime={life_v if life_v is not None else ('dynamic' if life else '-')}"
        f"  LifeStepMoment={m.get('LifeStepMoment', 'default(turn end)')}"
        f"  Stacking={m.get('Stacking', '-')}  MaxLayer={_value(m.get('MaxLayer', '-'))}"
        f"  StatusType={m.get('StatusType', '-')}"
    )
    for cb in m.get("_CallbackList", []):
        ops: list[str] = []
        gameplay_ops(cb.get("CallbackConfig", []), ops, 2)
        if ops:
            print(f"  on {cb.get('Event')}:")
            print(_clip(ops, limit and limit - 5, "      "))


def _clip(ops: list[str], n: int | None, pad: str) -> str:
    return "\n".join(ops[:n]) + (f"\n{pad}..." if n is not None and len(ops) > n else "")


def summarize(data: dict[str, Any], grep: str | None, limit: int | None = 30) -> None:
    def match(name: str) -> bool:
        return not grep or grep.lower() in name.lower()

    for ab in data.get("AbilityList", []):
        for name, m in (ab.get("Modifiers") or {}).items():
            if match(name):
                _print_modifier(name, m, limit)
        name = ab.get("Name", "")
        if name and match(name):
            ops: list[str] = []
            gameplay_ops(ab.get("OnStart", []), ops, 1)
            if ops:
                print(f"ABILITY {name}")
                print(_clip(ops, limit, "    "))
    # modifiers defined at file level (shared by several abilities: Hellscape, Ashen Roast, marks ...)
    for name, m in (data.get("GlobalModifiers") or {}).items():
        if match(name):
            _print_modifier(name, m, limit)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("character")
    ap.add_argument("--grep", help="only modifiers/abilities whose name contains this")
    ap.add_argument("--cache", type=Path, default=Path(".cache/ability"))
    ap.add_argument("--full", action="store_true", help="do not truncate long operation lists")
    ap.add_argument("--servant", action="store_true", help="also summarise the memosprite (servant) script")
    ap.add_argument("--file", help="summarise this ability file instead (path inside the data repository)")
    args = ap.parse_args()
    limit = None if args.full else 30
    if args.file:
        print(f"# {args.file}")
        summarize(fetch(args.file, args.cache), args.grep, limit)
        return
    enhanced = args.character.endswith("+")
    c = get_data().character(args.character.rstrip("+"))
    cfg = c["enhanced"]["config"] if enhanced else c["config"]
    path = cfg.replace("ConfigCharacter", "ConfigAbility").replace("_Config.json", "_Ability.json")
    print(f"# {c['name']}{' (enhanced)' if enhanced else ''}: {path}")
    summarize(fetch(path, args.cache), args.grep, limit)
    if args.servant:
        # Avatar_<X>_<NN>_Ability.json -> Servant/Servant_<X>Servant_<NN>_Ability.json
        stem = path.rsplit("/", 1)[-1].removeprefix("Avatar_").removesuffix("_Ability.json")
        base, _, num = stem.rpartition("_")
        spath = f"Config/ConfigAbility/Servant/Servant_{base}Servant_{num}_Ability.json"
        try:
            data = fetch(spath, args.cache)
        except urllib.error.HTTPError:
            print(f"# no servant script at {spath}")
            return
        print(f"# memosprite: {spath}")
        summarize(data, args.grep, limit)


if __name__ == "__main__":
    main()
