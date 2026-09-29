"""Build the trimmed game-data snapshot used by :mod:`hsrsim`.

Numbers (base stats, skill multipliers, energy, toughness, skill points,
eidolon/trace parameters, light cone and relic values) come straight from the
datamined client tables (``ExcelOutput``). Names and descriptions (EN + CN) come
from the pre-resolved text in Mar-7th/StarRailRes, joined by ID.

Usage::

    python tools/build_gamedata.py              # download sources, write snapshot
    python tools/build_gamedata.py --cache DIR  # reuse / keep downloaded sources in DIR

The snapshot is written to ``hsrsim/data/gamedata`` and is committed so the
simulator works offline. Re-run this script after a game patch.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any

RAW_BASE = "https://raw.githubusercontent.com/DimbreathBot/turnbasedgamedata/main/ExcelOutput/"
RES_BASE = "https://raw.githubusercontent.com/Mar-7th/StarRailRes/master/"

RAW_TABLES = [
    "AvatarConfig",
    "AvatarConfigEnhanced",
    "AvatarPromotionConfig",
    "AvatarSkillConfig",
    "AvatarServantSkillConfig",
    "AvatarRankConfig",
    "AvatarSkillTreeConfig",
    "EquipmentConfig",
    "EquipmentPromotionConfig",
    "EquipmentSkillConfig",
    "RelicSetConfig",
    "RelicSetSkillConfig",
    "RelicMainAffixConfig",
    "RelicSubAffixConfig",
    "AvatarBreakDamage",
    "ElationBasicLevelDamage",
]
# "LD" tables hold the collaboration characters (e.g. the Fate/stay night crossover).
LD_TABLES = [
    "AvatarConfig",
    "AvatarPromotionConfig",
    "AvatarSkillConfig",
    "AvatarRankConfig",
    "AvatarSkillTreeConfig",
]
RES_FILES = [
    "characters",
    "character_skills",
    "character_ranks",
    "character_skill_trees",
    "light_cones",
    "light_cone_ranks",
    "relic_sets",
]
LANGS = {"en": "", "cn": "_cn"}

OUT_DIR = Path(__file__).resolve().parent.parent / "hsrsim" / "data" / "gamedata"


def fetch(url: str, dest: Path) -> Any:
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        print(f"download {url}", file=sys.stderr)
        with urllib.request.urlopen(url, timeout=120) as resp:  # noqa: S310
            dest.write_bytes(resp.read())
    return json.loads(dest.read_text(encoding="utf-8"))


def val(x: Any, default: Any = None) -> Any:
    """Unwrap the ``{"Value": v}`` wrapper used throughout ExcelOutput."""
    if isinstance(x, dict):
        return x.get("Value", default)
    return default if x is None else x


def plist(xs: list[Any] | None) -> list[float]:
    return [val(x, 0.0) for x in (xs or [])]


def dump(name: str, data: dict[str, Any]) -> None:
    """One record per line keeps the snapshot diff-friendly after patches."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        f"{json.dumps(k)}:{json.dumps(v, ensure_ascii=False, separators=(',', ':'))}"
        for k, v in data.items()
    ]
    (OUT_DIR / f"{name}.json").write_text("{\n" + ",\n".join(lines) + "\n}\n", encoding="utf-8")
    print(f"wrote {name}.json ({len(data)} records)", file=sys.stderr)


def text(res: dict[str, dict[str, Any]], key: str, field: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for lang, suffix in LANGS.items():
        rec = res[lang].get(key)
        if rec is not None and field in rec:
            out[f"{field}{suffix}"] = rec[field]
    return out


def constant_or_list(values: list[Any]) -> Any:
    return values[0] if all(v == values[0] for v in values) else values


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", type=Path, default=Path(".cache/gamedata_src"))
    args = ap.parse_args()
    cache: Path = args.cache

    raw = {t: fetch(RAW_BASE + t + ".json", cache / "raw" / f"{t}.json") for t in RAW_TABLES}
    for t in LD_TABLES:
        raw[t] = raw[t] + fetch(RAW_BASE + t + "LD.json", cache / "raw" / f"{t}LD.json")
    res: dict[str, dict[str, dict[str, Any]]] = {}
    for f in RES_FILES:
        res[f] = {lang: fetch(f"{RES_BASE}index_new/{lang}/{f}.json", cache / lang / f"{f}.json") for lang in LANGS}
    version = fetch(RES_BASE + "info.json", cache / "info.json")

    # ---------------------------------------------------------------- characters
    promos: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for p in raw["AvatarPromotionConfig"]:
        promos[p["AvatarID"]].append(p)
    # trace nodes: "<cid>NNN" belong to the base kit, "1<cid>NNN" to the enhanced kit
    trees_by_char: dict[str, list[str]] = defaultdict(list)
    for t in raw["AvatarSkillTreeConfig"]:
        cid, pid = str(t["AvatarID"]), str(t["PointID"])
        key = cid if len(pid) == len(cid) + 3 else f"{cid}+"
        if pid not in trees_by_char[key]:
            trees_by_char[key].append(pid)
    enhanced = {str(a["AvatarID"]): a for a in raw["AvatarConfigEnhanced"]}

    characters: dict[str, Any] = {}
    for a in raw["AvatarConfig"]:
        cid = str(a["AvatarID"])
        if cid not in res["characters"]["en"]:
            continue  # unreleased / trial / test avatars
        rows = sorted(promos[a["AvatarID"]], key=lambda p: val(p.get("Promotion"), 0) or 0)
        rows.sort(key=lambda p: p["MaxLevel"])
        promotions = [
            {
                "max_level": p["MaxLevel"],
                "hp": [val(p["HPBase"]), val(p["HPAdd"])],
                "atk": [val(p["AttackBase"]), val(p["AttackAdd"])],
                "def": [val(p["DefenceBase"]), val(p["DefenceAdd"])],
                "spd": val(p["SpeedBase"]),
                "crit_rate": val(p["CriticalChance"]),
                "crit_dmg": val(p["CriticalDamage"]),
                "aggro": val(p["BaseAggro"]),
            }
            for p in rows
        ]
        en = res["characters"]["en"][cid]
        characters[cid] = {
            "id": cid,
            "name": en["name"],
            "name_cn": res["characters"]["cn"].get(cid, {}).get("name", en["name"]),
            "tag": en.get("tag"),
            "rarity": int(a["Rarity"][-1]),
            "path": a["AvatarBaseType"],
            "element": a["DamageType"],
            "max_energy": val(a.get("SPNeed")),
            "promotions": promotions,
            "skills": [str(s) for s in a["SkillList"]],
            "ranks": [str(r) for r in a["RankIDList"]],
            "traces": trees_by_char[cid],
        }
        if cid in enhanced:
            en_cfg = enhanced[cid]
            characters[cid]["enhanced"] = {
                "id": en_cfg["EnhancedID"],
                "max_energy": val(en_cfg.get("SPNeed")),
                "skills": [str(x) for x in en_cfg["SkillList"]],
                "ranks": [str(x) for x in en_cfg["RankIDList"]],
                "traces": trees_by_char[f"{cid}+"],
            }
    dump("characters", characters)

    # -------------------------------------------------------------------- skills
    skill_rows: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for s in raw["AvatarSkillConfig"] + raw["AvatarServantSkillConfig"]:
        skill_rows[s["SkillID"]].append(s)
    skills: dict[str, Any] = {}
    for sid, rows in sorted(skill_rows.items()):
        rows.sort(key=lambda r: r["Level"])
        key = str(sid)
        if key not in res["character_skills"]["en"]:
            continue
        en = res["character_skills"]["en"][key]
        tough = [constant_or_list([val(x, 0) / 3 for x in r.get("ShowStanceList", [])]) for r in rows]
        skills[key] = {
            "id": key,
            "name": en["name"],
            **{k: v for k, v in text(res["character_skills"], key, "name").items() if k != "name"},
            "type": en["type"],
            "type_text": en.get("type_text", ""),
            "effect": en.get("effect", ""),
            "attack_type": rows[0].get("AttackType", ""),
            "element": rows[0].get("StanceDamageType", ""),
            "trigger": rows[0].get("SkillTriggerKey", ""),
            "energy": constant_or_list([val(r.get("SPBase"), 0) for r in rows]),
            "toughness": constant_or_list(tough) if tough else [],
            "sp_need": constant_or_list([val(r.get("BPNeed"), -1) for r in rows]),
            "sp_add": constant_or_list([val(r.get("BPAdd"), 0) for r in rows]),
            "max_level": rows[-1]["Level"],
            "params": [plist(r.get("ParamList")) for r in rows],
            **text(res["character_skills"], key, "desc"),
        }
    dump("skills", skills)

    # ----------------------------------------------------------------- eidolons
    ranks: dict[str, Any] = {}
    for r in raw["AvatarRankConfig"]:
        key = str(r["RankID"])
        if key not in res["character_ranks"]["en"]:
            continue
        ranks[key] = {
            "id": key,
            "char": key[:-2],
            "rank": r["Rank"],
            **text(res["character_ranks"], key, "name"),
            **text(res["character_ranks"], key, "desc"),
            "params": plist(r.get("Param")),
            "skill_add_level": {str(k): v for k, v in (r.get("SkillAddLevelList") or {}).items()},
        }
    dump("ranks", ranks)

    # ------------------------------------------------------------------- traces
    traces: dict[str, Any] = {}
    for t in raw["AvatarSkillTreeConfig"]:
        key = str(t["PointID"])
        if key in traces or t.get("Level", 1) != 1:
            continue
        rec: dict[str, Any] = {
            "id": key,
            "char": str(t["AvatarID"]),
            "type": t["PointType"],
            "anchor": t["AnchorType"],
            "max_level": t["MaxLevel"],
            "pre": [str(p) for p in t.get("PrePoint", [])],
            "skills": [str(s) for s in t.get("LevelUpSkillID", [])],
            "stats": [[x["PropertyType"], val(x["Value"])] for x in t.get("StatusAddList", [])],
            "params": plist(t.get("ParamList")),
        }
        if key in res["character_skill_trees"]["en"]:
            names = text(res["character_skill_trees"], key, "name")
            descs = text(res["character_skill_trees"], key, "desc")
            rec.update({k: v for k, v in names.items() if v})
            rec.update({k: v for k, v in descs.items() if v})
        traces[key] = rec
    dump("traces", traces)

    # -------------------------------------------------------------- light cones
    eq_promos: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for p in raw["EquipmentPromotionConfig"]:
        eq_promos[p["EquipmentID"]].append(p)
    eq_skills: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for s in raw["EquipmentSkillConfig"]:
        eq_skills[s["SkillID"]].append(s)
    light_cones: dict[str, Any] = {}
    for e in raw["EquipmentConfig"]:
        key = str(e["EquipmentID"])
        if key not in res["light_cones"]["en"]:
            continue
        prow = sorted(eq_promos[e["EquipmentID"]], key=lambda p: p["MaxLevel"])
        srow = sorted(eq_skills[e["SkillID"]], key=lambda s: s["Level"])
        lc_rank = res["light_cone_ranks"]
        light_cones[key] = {
            "id": key,
            "name": res["light_cones"]["en"][key]["name"],
            "name_cn": res["light_cones"]["cn"].get(key, {}).get("name", ""),
            "rarity": int(e["Rarity"][-1]),
            "path": e["AvatarBaseType"],
            "promotions": [
                {
                    "max_level": p["MaxLevel"],
                    "hp": [val(p["BaseHP"]), val(p["BaseHPAdd"])],
                    "atk": [val(p["BaseAttack"]), val(p["BaseAttackAdd"])],
                    "def": [val(p["BaseDefence"]), val(p["BaseDefenceAdd"])],
                }
                for p in prow
            ],
            "skill": lc_rank["en"].get(key, {}).get("skill", ""),
            "skill_cn": lc_rank["cn"].get(key, {}).get("skill", ""),
            **text(lc_rank, key, "desc"),
            "params": [plist(s.get("ParamList")) for s in srow],
            "props": [
                [[x["PropertyType"], val(x["Value"])] for x in s.get("AbilityProperty", [])] for s in srow
            ],
        }
    dump("light_cones", light_cones)

    # --------------------------------------------------------------- relic sets
    set_skills: dict[int, dict[int, dict[str, Any]]] = defaultdict(dict)
    for s in raw["RelicSetSkillConfig"]:
        props = []
        for p in s.get("PropertyList", []):
            # field names of this table are obfuscated: pick the string + the {"Value"} dict
            prop = next((v for v in p.values() if isinstance(v, str)), None)
            num = next((val(v) for v in p.values() if isinstance(v, dict)), None)
            props.append([prop, num])
        set_skills[s["SetID"]][s["RequireNum"]] = {"props": props, "params": plist(s.get("AbilityParamList"))}
    relic_sets: dict[str, Any] = {}
    for rs in raw["RelicSetConfig"]:
        key = str(rs["SetID"])
        if key not in res["relic_sets"]["en"]:
            continue
        en = res["relic_sets"]["en"][key]
        cn = res["relic_sets"]["cn"].get(key, {})
        pieces = {}
        for i, n in enumerate(rs["SetSkillList"]):
            pieces[str(n)] = {
                "desc": en["desc"][i] if i < len(en["desc"]) else "",
                "desc_cn": cn.get("desc", [""] * 4)[i] if i < len(cn.get("desc", [])) else "",
                **set_skills[rs["SetID"]].get(n, {"props": [], "params": []}),
            }
        relic_sets[key] = {
            "id": key,
            "name": en["name"],
            "name_cn": cn.get("name", ""),
            "planar": bool(rs.get("IsPlanarSuit", False)),
            "pieces": pieces,
        }
    dump("relic_sets", relic_sets)

    # ------------------------------------------------------ relic stats + tables
    main_aff: dict[str, dict[str, Any]] = defaultdict(dict)
    for m in raw["RelicMainAffixConfig"]:
        main_aff[str(m["GroupID"])][m["Property"]] = {"base": val(m["BaseValue"]), "add": val(m["LevelAdd"])}
    sub_aff: dict[str, dict[str, Any]] = defaultdict(dict)
    for s in raw["RelicSubAffixConfig"]:
        sub_aff[str(s["GroupID"])][s["Property"]] = {
            "base": val(s["BaseValue"]),
            "step": val(s["StepValue"]),
            "step_num": s["StepNum"],
        }
    tables = {
        "version": version,
        "break_level_base": {str(r["Level"]): val(r["BreakBaseDamage"]) for r in raw["AvatarBreakDamage"]},
        "elation_level_base": {
            str(r["Level"]): val(r["ElationBasicLevelDamage"]) for r in raw["ElationBasicLevelDamage"]
        },
        "relic_main_affix": dict(main_aff),
        "relic_sub_affix": dict(sub_aff),
    }
    dump("tables", tables)


if __name__ == "__main__":
    main()
