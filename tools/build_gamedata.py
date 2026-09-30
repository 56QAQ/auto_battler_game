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
    "AvatarServantConfig",
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
    "ElationSkill",
]
# enemy / endgame tables (only the stages of recent endgame modes are kept)
ENEMY_TABLES = [
    "MonsterConfig",
    "MonsterTemplateConfig",
    "MonsterSkillConfig",
    "HardLevelGroup",
    "EliteGroup",
    "StageConfig",
    "ChallengeGroupConfig",
    "ChallengeMazeConfig",
    "ChallengeBossGroupConfig",
    "ChallengeBossMazeConfig",
    "ChallengeStoryGroupConfig",
    "ChallengeStoryMazeConfig",
    "ScheduleDataChallengeMaze",
    "ScheduleDataChallengeBoss",
    "ScheduleDataChallengeStory",
    "StageInfiniteGroup",
    "StageInfiniteWaveConfig",
    "StageInfiniteMonsterGroup",
]
RECENT_GROUPS = 3  # per endgame mode

RANKS = {"Minion": "normal", "MinionLv2": "normal", "Elite": "elite", "LittleBoss": "boss", "BigBoss": "boss"}
DEBUFF_KEYS = {
    "STAT_CTRL": "cc",
    "STAT_CTRL_Frozen": "freeze",
    "STAT_Confine": "imprisonment",
    "STAT_Entangle": "entanglement",
}

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
    lines = [f"{json.dumps(k)}:{json.dumps(v, ensure_ascii=False, separators=(',', ':'))}" for k, v in data.items()]
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
            "config": a.get("JsonPath", ""),
            "promotions": promotions,
            "skills": [str(s) for s in a["SkillList"]],
            "ranks": [str(r) for r in a["RankIDList"]],
            "traces": trees_by_char[cid],
        }
        if cid in enhanced:
            en_cfg = enhanced[cid]
            characters[cid]["enhanced"] = {
                "id": en_cfg["EnhancedID"],
                "config": en_cfg.get("JsonPath", ""),
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

    # ---------------------------------------------------------- memosprites
    # HP = HPBase + HPInherit x owner Max HP ; SPD = SpeedBase + SpeedInherit x owner SPD
    # values like "#5" reference parameter 5 (1-based) of HPSkill / SpeedSkill at its current level
    memos: dict[str, Any] = {}
    for sv in raw["AvatarServantConfig"]:
        sid = str(sv["ServantID"])
        memos[sid] = {
            "id": sid,
            "owner": sid[1:],
            "skills": [str(x) for x in sv.get("SkillIDList", [])],
            "hp_base": sv.get("HPBase", "0"),
            "hp_inherit": sv.get("HPInherit", "0"),
            "hp_skill": str(sv.get("HPSkill", "")),
            "spd_base": sv.get("SpeedBase", "0"),
            "spd_inherit": sv.get("SpeedInherit", "0"),
            "spd_skill": str(sv.get("SpeedSkill", "")),
            "aggro": val(sv.get("Aggro"), 100),
        }
    dump("memosprites", memos)

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
            "props": [[[x["PropertyType"], val(x["Value"])] for x in s.get("AbilityProperty", [])] for s in srow],
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
        "elation_skill_priority": {str(r["ElationSkillID"]): r["PriorityValue"] for r in raw["ElationSkill"]},
        "relic_main_affix": dict(main_aff),
        "relic_sub_affix": dict(sub_aff),
        "character_groups": character_groups(cache),
    }
    dump("tables", tables)

    add_hit_splits(skills, characters, cache)
    dump("skills", skills)

    enemy_raw = {t: fetch(RAW_BASE + t + ".json", cache / "raw" / f"{t}.json") for t in ENEMY_TABLES}
    dump("endgame", build_endgame(enemy_raw))


CONFIG_BASE = "https://raw.githubusercontent.com/DimbreathBot/turnbasedgamedata/main/"


def character_groups(cache: Path) -> dict[str, list[str]]:
    """Named character groups used by ability scripts (``ByIsInCharacterIDGroup``), e.g. "AstralExpress" (the
    Trailblaze Companions) or "Chrysos" (the Chrysos Heirs), from ``GameCoreConstValue.CharacterIDGroups``."""
    path = "Config/GlobalConfig/GameCoreConstValue.json"
    data = fetch(CONFIG_BASE + path, cache / "config" / path.replace("/", "_"))
    return {g["Group"]: [str(i) for i in g.get("IDList", [])] for g in data.get("CharacterIDGroups", [])}


SPLIT_GROUPS = {
    "AbilityTargetEntity": "splits",  # the designated target
    "AbilityTargetAdjoinEntity": "splits_adj",  # adjacent targets
    "AllEnemy": "splits_aoe",
    "AllDarkTeam": "splits_aoe",
}
GATED = ("ByRankActivated", "BySkillPointActivated")  # eidolon / trace conditions


def add_hit_splits(skills: dict[str, Any], characters: dict[str, Any], cache: Path) -> None:
    """Attach per-hit split ratios to skills from the characters' ability scripts.

    For every ability named ``..._<SkillTriggerKey>_Phase*`` the fixed ``HitSplitRatio`` of each
    ``DamageByAttackProperty`` is recorded in order, per target group: ``skill["splits"]`` (designated target),
    ``skill["splits_adj"]`` (adjacent targets) and ``skill["splits_aoe"]`` (all enemies). Loops with a static
    ``MaxLoopCount`` are unrolled; for branches gated by an eidolon or trace only the base branch (the one taken
    without it) is followed. A group is kept only when all its ratios are fixed numbers summing to ~1 and it has
    more than one hit.
    """

    def walk(o: Any, out: list[tuple[str, float | None]]) -> None:
        if isinstance(o, dict):
            t = str(o.get("$type", ""))
            if t.endswith("PredicateTaskList") and str((o.get("Predicate") or {}).get("$type", "")).endswith(GATED):
                walk(o.get("FailedTaskList"), out)
                return
            if t.endswith("LoopExecuteTaskListWithInterval"):
                cnt = o.get("MaxLoopCount") or {}
                n = None if cnt.get("IsDynamic") else val(cnt.get("FixedValue"), None)
                body: list[tuple[str, float | None]] = []
                walk(o.get("TaskList"), body)
                out.extend(body * int(n) if n else [(a, None) for a, _ in body])
                return
            if t.endswith("DamageByAttackProperty"):
                ap = o.get("AttackProperty") or {}
                hs = ap.get("HitSplitRatio") or {}
                ratio = None if hs.get("IsDynamic") else val(hs.get("FixedValue"), None)
                alias = (o.get("TargetType") or {}).get("Alias", "")
                out.append((alias, ratio))
            for v in o.values():
                walk(v, out)
        elif isinstance(o, list):
            for v in o:
                walk(v, out)

    for cid, c in characters.items():
        variants = [(c.get("config", ""), [k for k in skills if k[:-2] == cid])]
        if "enhanced" in c:
            variants.append((c["enhanced"].get("config", ""), [k for k in skills if k[:-2] == "1" + cid]))
        for cfg, sids in variants:
            if not cfg:
                continue
            path = cfg.replace("ConfigCharacter", "ConfigAbility").replace("_Config.json", "_Ability.json")
            try:
                data = fetch(CONFIG_BASE + path, cache / "ability" / path.replace("/", "_"))
            except Exception as exc:  # noqa: BLE001 - some characters have differently named scripts
                print(f"no ability script for {cid}: {exc}", file=sys.stderr)
                continue
            by_trigger: dict[str, list[tuple[str, float | None]]] = {}
            for ab in data.get("AbilityList", []):
                name = ab.get("Name", "")
                for part in name.split("_"):
                    if part.startswith("Skill") and "_Phase" in name:
                        hits: list[tuple[str, float | None]] = []
                        walk(ab.get("OnStart", []), hits)
                        if hits:
                            by_trigger.setdefault(part, []).extend(hits)
                        break
            for sid in sids:
                trig = skills[sid].get("trigger", "")
                hits = by_trigger.get(trig, [])
                for key in dict.fromkeys(SPLIT_GROUPS.values()):
                    group = [r for a, r in hits if SPLIT_GROUPS.get(a) == key]
                    if len(group) > 1 and all(r is not None for r in group) and abs(sum(group) - 1.0) < 0.02:
                        skills[sid][key] = [round(float(r), 4) for r in group]  # type: ignore[arg-type]


def build_endgame(raw: dict[str, Any]) -> dict[str, Any]:
    """Recent Memory of Chaos / Apocalyptic Shadow / Pure Fiction stages with computed enemy stats."""
    monsters = {m["MonsterID"]: m for m in raw["MonsterConfig"]}
    templates = {t["MonsterTemplateID"]: t for t in raw["MonsterTemplateConfig"]}
    hlg = {(h["HardLevelGroup"], h["Level"]): h for h in raw["HardLevelGroup"]}
    elite = {e["EliteGroup"]: e for e in raw["EliteGroup"]}
    stages = {s["StageID"]: s for s in raw["StageConfig"]}
    skills = {s["SkillID"]: s for s in raw["MonsterSkillConfig"]}

    def monster(mid: int, level: int, hl: int, eg: int | None) -> dict[str, Any]:
        m = monsters[mid]
        t = templates[m["MonsterTemplateID"]]
        h = hlg.get((hl, level), {})
        e = elite.get(eg, {}) if eg else {}

        def mul(field: str, mfield: str) -> float:
            return float(
                val(t.get(field), 0)
                * val(m.get(mfield), 1)
                * val(h.get(field.replace("Base", "Ratio")), 1)
                * val(e.get(field.replace("Base", "Ratio")), 1)
            )

        hits = [val(skills[k].get("SPHitBase"), 0) for k in m.get("SkillList", []) if k in skills]
        hits = [x for x in hits if x]
        name = t.get("JsonConfig", "").rsplit("/", 1)[-1]
        name = name.removeprefix("Monster_").removesuffix(".json").replace("_Config", "")
        return {
            "id": mid,
            "name": name or str(mid),
            "rank": RANKS.get(t.get("Rank", ""), "normal"),
            "level": level,
            "hp": mul("HPBase", "HPModifyRatio"),
            "atk": mul("AttackBase", "AttackModifyRatio"),
            "def": mul("DefenceBase", "DefenceModifyRatio"),
            "spd": mul("SpeedBase", "SpeedModifyRatio"),
            "toughness": mul("StanceBase", "StanceModifyRatio") / 3.0,  # display units
            "effect_res": float(val(t.get("StatusResistanceBase"), 0) + val(h.get("StatusResistance"), 0)),
            "weaknesses": list(m.get("StanceWeakList", [])),
            "res": {r["DamageType"]: val(r["Value"], 0) for r in m.get("DamageTypeResistance", [])},
            "debuff_res": {DEBUFF_KEYS.get(r["Key"], r["Key"]): val(r["Value"], 0) for r in m.get("DebuffResist", [])},
            "hit_energy": max(set(hits), key=hits.count) if hits else 10,
            "initial_delay": val(t.get("InitialDelayRatio"), 1),
            # passive skills ("SkillP01" ...) with their parameters, for monster traits (hsrsim/monsters.py)
            "passives": {
                skills[k]["SkillTriggerKey"]: [float(val(x, 0)) for x in skills[k].get("ParamList", [])]
                for k in m.get("SkillList", [])
                if k in skills and str(skills[k].get("SkillTriggerKey", "")).startswith("SkillP")
            },
        }

    def stage(sid: int) -> dict[str, Any] | None:
        st = stages.get(sid)
        if st is None:
            return None
        lv, hl, eg = st["Level"], st["HardLevelGroup"], st.get("EliteGroup")
        waves = [
            [monster(mid, lv, hl, eg) for _, mid in sorted(w.items()) if mid in monsters]
            for w in st.get("MonsterList", [])
        ]
        out: dict[str, Any] = {"stage_id": sid, "level": lv, "waves": waves}
        infinite = next(
            (c["MNDFOPKBHKP"] for c in st.get("StageConfigData", []) if c.get("BFLIFKBEOPJ") == "_StageInfiniteGroup"),
            None,
        )
        if infinite:
            group = next((g for g in raw["StageInfiniteGroup"] if g["WaveGroupID"] == int(infinite)), None)
            iwaves = {w["InfiniteWaveID"]: w for w in raw["StageInfiniteWaveConfig"]}
            igroups = {g["InfiniteMonsterGroupID"]: g for g in raw["StageInfiniteMonsterGroup"]}
            spawn = []
            for wid in (group or {}).get("WaveIDList", []):
                w = iwaves[wid]
                pool = []
                for gid in w["MonsterGroupIDList"]:
                    g = igroups[gid]
                    pool += [monster(mid, lv, hl, g.get("EliteGroup")) for mid in g["MonsterList"] if mid in monsters]
                spawn.append({"max_count": w["MaxMonsterCount"], "on_field": w["MaxTeammateCount"], "monsters": pool})
            out["infinite"] = spawn
        return out

    def recent(schedule: str, group_table: str, maze_table: str, mode: str) -> list[dict[str, Any]]:
        # ignore placeholder schedules far in the future (e.g. year 2033 test entries)
        sched = {s["ID"]: s for s in raw[schedule] if s["BeginTime"][:4] < "2030"}
        groups = [g for g in raw[group_table] if g.get("ScheduleDataID") in sched]
        groups.sort(key=lambda g: sched[g["ScheduleDataID"]]["BeginTime"])
        out = []
        for g in groups[-RECENT_GROUPS:]:
            sc = sched[g["ScheduleDataID"]]
            floors = []
            for mz in sorted((m for m in raw[maze_table] if m["GroupID"] == g["GroupID"]), key=lambda m: m["Floor"]):
                halves = []
                for side in (1, 2):
                    sts = [stage(sid) for sid in mz.get(f"EventIDList{side}", [])]
                    halves.append({"weakness_hint": mz.get(f"DamageType{side}", []), "stages": [x for x in sts if x]})
                floors.append(
                    {"id": mz["ID"], "floor": mz["Floor"], "cycles": mz.get("ChallengeCountDown"), "halves": halves}
                )
            out.append(
                {"group": g["GroupID"], "mode": mode, "begin": sc["BeginTime"], "end": sc["EndTime"], "floors": floors}
            )
        return out

    return {
        "moc": recent("ScheduleDataChallengeMaze", "ChallengeGroupConfig", "ChallengeMazeConfig", "moc"),
        "as": recent("ScheduleDataChallengeBoss", "ChallengeBossGroupConfig", "ChallengeBossMazeConfig", "as"),
        "pf": recent("ScheduleDataChallengeStory", "ChallengeStoryGroupConfig", "ChallengeStoryMazeConfig", "pf"),
    }


if __name__ == "__main__":
    main()
