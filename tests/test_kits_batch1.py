"""Targeted checks for batch-1 kits: March 7th (Preservation), Dan Heng, Himeko, Welt, Arlan, Asta,
Herta, Serval, Sampo, Hook, Luka."""

import pytest

from hsrsim import events as E
from hsrsim import formulas as F
from hsrsim import stats as S
from hsrsim.battle import Battle, BattleConfig
from hsrsim.build import Build, make_character
from hsrsim.entities import Enemy
from hsrsim.enums import Element
from hsrsim.modifiers import Modifier, ModKind
from hsrsim.scenarios import boss_dps

from .helpers import generic_build


def _battle(builds, enemies=None, **cfg):
    chars = [make_character(b) for b in builds]
    if enemies is None:
        enemies = [Enemy("Dummy", hp=1e12, toughness=1e6, effect_res=0.0)]
    b = Battle(chars, [enemies], BattleConfig(**cfg))
    b.start()
    return b, chars, enemies


def _recs(b, label):
    return [r for r in b.records if r.label == label]


# ------------------------------------------------------------------ March 7th
def test_march_7th_skill_shield_and_counter_limit():
    b, (march,), (e,) = _battle([Build("1001")])
    kit = march.kit
    sp0 = b.sp
    kit.skill(e)
    shield = march.get_mod("The Power of Cuteness")
    assert shield is not None and b.sp == sp0 - 1
    expected = (kit.p("skill", 0) * march.defense + kit.p("skill", 3)) * (1 + march.stat(S.SHIELD_PCT))
    assert shield.data["value"] == pytest.approx(expected)
    assert shield.duration == int(kit.p("skill", 1) + kit.tp(2, 0))  # A4 Reinforce: +1 turn
    assert march.stat(S.AGGRO_PCT) > 0  # full HP -> taunt
    # three enemy attacks on the Shielded March 7th within one turn -> only 2 Counters (Talent limit)
    for _ in range(3):
        b.sp = b.max_sp
        kit.skill(e)  # keep the Shield up
        b.enemy_basic_attack(e)
        b.process_queue()
    counters = _recs(b, "Girl Power (Counter)")
    assert len(counters) == int(kit.p("talent", 1))
    assert all("fua" in r.tags for r in counters)


def test_march_7th_ult_freeze_skips_turn_and_deals_additional_dmg():
    b, (march,), (e,) = _battle([Build("1001", eidolon=1, extra_stats={"ehr": 1.0})])
    kit = march.kit
    e0 = march.energy
    kit.ult(e)  # (50% + 15% A6) x 200% EHR vs Effect RES 0 -> Frozen
    assert e.has_tag("freeze")
    ult_energy = kit.sk("ult")["energy"]
    assert march.energy - e0 == pytest.approx((ult_energy + kit.ep(1, 0)) * (1 + march.stat(S.ERR)))  # E1
    acted = []
    b.events.on(E.ACTION_START, lambda ev: ev.action.actor is e and acted.append(ev.action))
    b.take_turn(e)
    assert len(_recs(b, "Glacial Cascade")) == 4  # ability script: 4 hits of 25%
    add = _recs(b, "Frozen (March 7th)")
    assert len(add) == 1 and "additional" in add[0].tags
    assert not acted  # the Frozen enemy skipped its turn
    assert not e.has_tag("freeze")


# ------------------------------------------------------------------- Dan Heng
def test_dan_heng_ult_bonus_vs_slowed_and_talent_res_pen():
    def ult_dmg(slowed: bool) -> float:
        b, (dh,), (e,) = _battle([Build("1002", traces=False)])
        if slowed:
            b.apply(Modifier("Slow", stats={S.SPD_PCT: -0.1}, duration=2, kind=ModKind.DEBUFF), e, dh)
        dh.kit.ult(e)
        return sum(r.amount for r in _recs(b, "Ethereal Dream"))

    kit = make_character(Build("1002")).kit
    assert ult_dmg(True) / ult_dmg(False) == pytest.approx((kit.p("ult", 0) + kit.p("ult", 1)) / kit.p("ult", 0))

    # Talent: Bronya's Skill targets Dan Heng -> Wind RES PEN on his next attack, consumed by it
    b, (dh, bronya), (e,) = _battle([Build("1002"), Build("Bronya", options={"target": "Dan Heng"})])
    bronya.kit.skill(e)
    assert dh.stat(f"{S.RES_PEN}:Wind") == pytest.approx(dh.kit.p("talent", 0))
    dh.kit.basic(e)
    assert dh.stat(f"{S.RES_PEN}:Wind") == 0.0
    assert dh.kit.talent_cd == int(dh.kit.p("talent", 1))


# --------------------------------------------------------------------- Himeko
def test_himeko_charge_and_victory_rush():
    b, (himeko,), (e,) = _battle([Build("1003")])
    kit = himeko.kit
    assert kit.charge == 1  # "At the start of the battle, Himeko gains 1 point of Charge"
    kit.basic(e)
    b.process_queue()
    assert not _recs(b, "Victory Rush")
    kit.charge = kit.max_charge
    kit.basic(e)
    b.process_queue()
    fua = _recs(b, "Victory Rush")
    assert all("fua" in r.tags for r in fua) and kit.charge == 0
    # one Follow-Up ATK of 4 hits (ability script: 3 x 20% + 40%)
    total = sum(r.amount for r in fua)
    assert [r.amount / total for r in fua] == pytest.approx([0.2, 0.2, 0.2, 0.4], rel=1e-6)


def test_himeko_charge_from_weakness_break():
    enemy = Enemy("Dummy", hp=1e12, toughness=10, weaknesses=[Element.FIRE], effect_res=0.0)
    b, (himeko,), _ = _battle([Build("1003")], enemies=[enemy])
    himeko.kit.basic(enemy)
    assert enemy.broken and himeko.kit.charge == 2


# ----------------------------------------------------------------------- Welt
def test_welt_talent_additional_dmg_vs_slowed_and_imprison():
    b, (welt,), (e,) = _battle([Build("1004", traces=False)])
    kit = welt.kit
    kit.basic(e)
    assert not _recs(b, "Time Distortion")
    b.apply(Modifier("Slow", stats={S.SPD_PCT: -0.1}, duration=2, kind=ModKind.DEBUFF), e, welt)
    kit.basic(e)
    basic = _recs(b, "Gravity Suppression")[-1].amount
    talent = _recs(b, "Time Distortion")
    assert len(talent) == 1
    assert talent[0].amount / basic == pytest.approx(kit.p("talent", 0) / kit.p("basic", 0))
    # Ultimate: 100% base chance to Imprison (enemy Effect RES 0) -> action delayed
    gauge = e.gauge
    kit.ult(e)
    assert e.has_mod("Imprisoned (Welt)")
    assert e.gauge == pytest.approx(gauge + kit.p("ult", 1) * F.AV_BASE)


def test_welt_ult_two_hits_trigger_talent_twice_and_a2_before_damage():
    b, (welt,), (e,) = _battle([Build("1004")])
    kit = welt.kit
    b.apply(Modifier("Slow", stats={S.SPD_PCT: -0.1}, duration=2, kind=ModKind.DEBUFF), e, welt)
    kit.ult(e)
    ult = _recs(b, "Synthetic Black Hole")
    # ability script: split 0.1 / 0.9 on all enemies; the Talent triggers on every hit vs a Slowed enemy
    assert [r.amount / sum(x.amount for x in ult) for r in ult] == pytest.approx([0.1, 0.9], rel=1e-6)
    assert len(_recs(b, "Time Distortion")) == 2
    # A2 Retribution is added before the damage: the Ultimate itself takes the DMG-taken increase
    assert all(r.parts.vuln_mult == pytest.approx(1 + kit.tp(1, 1)) for r in ult)


def test_welt_enhanced_weightless():
    rep = boss_dps(cycles=4).run([Build("1004", enhanced=True), Build("Bronya"), Build("Pela"), Build("Huohuo")])
    b = rep.battle
    assert b.team[0].enhanced
    labels = {r.label for r in rep.records}
    assert "Judgment" in labels  # A4 Additional DMG on Basic ATK / Skill
    kit = b.team[0].kit
    boss = b.enemies[0]
    if any(r.label == "Synthetic Black Hole" for r in rep.records) and boss.has_mod("Weightless"):
        assert boss.stat("def_reduction") >= kit.p("talent", 1)


# ---------------------------------------------------------------------- Arlan
def test_arlan_skill_consumes_hp_not_sp_and_talent_scales():
    b, (arlan,), (e,) = _battle([Build("1008")])
    kit = arlan.kit
    sp0, dmg0 = b.sp, arlan.stat(S.DMG_PCT)
    kit.skill(e)
    assert b.sp == sp0
    assert arlan.hp == pytest.approx(arlan.max_hp * (1 - kit.p("skill", 0)))
    assert arlan.stat(S.DMG_PCT) - dmg0 == pytest.approx(kit.p("talent", 0) * kit.p("skill", 0))
    arlan.hp = 5.0
    kit.skill(e)
    assert arlan.hp == pytest.approx(1.0)  # insufficient HP -> reduced to 1


# ----------------------------------------------------------------------- Asta
def test_asta_charging_team_atk_and_ult_spd():
    enemy = Enemy("Dummy", hp=1e12, toughness=1e6, weaknesses=[Element.FIRE], effect_res=0.0)
    b, (asta, ally), _ = _battle([Build("1009"), generic_build("Seele")], enemies=[enemy])
    kit = asta.kit
    atk0 = ally.stat(S.ATK_PCT)
    kit.basic(enemy)  # one enemy hit + Fire Weakness -> 2 Charging
    assert kit.charging == 2
    assert ally.stat(S.ATK_PCT) - atk0 == pytest.approx(2 * kit.p("talent", 0))
    spd0 = ally.spd
    kit.ult(None)
    assert ally.spd - spd0 == pytest.approx(kit.p("ult", 0))


# ---------------------------------------------------------------------- Herta
def test_herta_follow_up_when_enemy_drops_below_half():
    b, (herta,), (e,) = _battle([Build("1013")])
    kit = herta.kit
    e.hp = e.max_hp * kit.p("talent", 0) + 1.0  # just above the threshold
    kit.basic(e)
    b.process_queue()
    fua = _recs(b, "Fine, I'll Do It Myself")
    assert len(fua) == 1 and "fua" in fua[0].tags
    kit.basic(e)  # already below 50%: no new trigger
    b.process_queue()
    assert len(_recs(b, "Fine, I'll Do It Myself")) == 1


def test_herta_skill_two_hits_check_hp_per_hit():
    b, (herta,), (e,) = _battle([Build("1013", traces=False)])
    kit = herta.kit
    kit.skill(e)  # full HP: both hits (30% / 70%) get the "HP >= 50%" bonus
    hits = _recs(b, "One-Time Offer")
    assert len(hits) == 2
    assert hits[1].parts.dmg_boost == pytest.approx(hits[0].parts.dmg_boost)
    assert hits[1].amount / hits[0].amount == pytest.approx(0.7 / 0.3, rel=1e-6)
    b.records.clear()
    e.hp = e.max_hp * kit.p("skill", 1) - 1.0  # below 50%: no bonus
    kit.skill(e)
    low = _recs(b, "One-Time Offer")
    assert hits[0].parts.dmg_boost - low[0].parts.dmg_boost == pytest.approx(kit.p("skill", 2))


def test_herta_e1_checks_hp_before_the_basic_hit():
    b, (herta,), (e,) = _battle([Build("1013", eidolon=1)])
    kit = herta.kit
    e.hp = e.max_hp * kit.ep(1, 0) + 1.0  # above 50% before the hit, below after it
    kit.basic(e)
    b.process_queue()
    assert e.hp_ratio <= kit.ep(1, 0)
    assert not _recs(b, "Kick You When You're Down")
    kit.basic(e)
    assert len(_recs(b, "Kick You When You're Down")) == 1


# --------------------------------------------------------------------- Serval
def test_serval_shock_talent_and_ult_extension():
    b, (serval,), (e,) = _battle([Build("1103")])
    kit = serval.kit
    kit.skill(e)  # 80% + 20% (A2) base chance vs Effect RES 0 -> Shocked
    shock = e.get_mod("Shock (Serval)")
    assert shock is not None and shock.duration == int(kit.p("skill", 3))
    assert len(_recs(b, "Galvanic Chords")) == 1  # Talent after the Skill hits the freshly Shocked enemy
    kit.ult(e)
    assert shock.duration == int(kit.p("skill", 3) + kit.p("ult", 1))
    assert len(_recs(b, "Galvanic Chords")) == 2


def test_serval_e4_shock_applied_before_ult_damage():
    b, (serval,), (e,) = _battle([Build("1103", eidolon=6)])
    kit = serval.kit
    kit.basic(e)  # enemy not Shocked: no E6 bonus
    basic_boost = _recs(b, "Roaring Thunderclap")[0].parts.dmg_boost
    kit.ult(e)
    ult = _recs(b, "Here Comes the Mechanical Fever")
    # E4 Shocks the enemy before the damage -> E6 (+30% vs Shocked) applies to the Ultimate hit
    assert ult[0].parts.dmg_boost - basic_boost == pytest.approx(kit.ep(6, 0))
    shock = e.get_mod("Shock (Serval)")
    assert shock is not None and shock.duration == int(kit.p("skill", 3) + kit.p("ult", 1))


# ---------------------------------------------------------------------- Sampo
def test_sampo_skill_wind_shear_per_hit_and_energy():
    b, (sampo,), (e,) = _battle([Build("1108", extra_stats={"ehr": 1.0})])
    kit = sampo.kit
    e0 = sampo.energy
    kit.skill(e)  # 1 + 4 bounces on the only enemy, 65% x 200% EHR -> every hit inflicts Wind Shear
    hits = int(kit.p("skill", 0)) + 1
    assert len(_recs(b, "Ricochet Love")) == hits
    assert kit.ws_stacks(e) == min(hits, int(kit.p("talent", 3)))
    assert sampo.energy - e0 == pytest.approx(kit.sk("skill")["energy"] * hits * (1 + sampo.stat(S.ERR)))
    b.take_turn(e)  # Wind Shear triggers at the enemy's turn start: stacks x multiplier
    ws = _recs(b, "Wind Shear (Sampo)")
    assert len(ws) == 1 and "dot" in ws[0].tags


def test_sampo_basic_and_ult_hits_each_roll_wind_shear():
    b, (sampo,), (e,) = _battle([Build("1108", extra_stats={"ehr": 1.0})])
    kit = sampo.kit
    kit.basic(e)  # 3 hits in the ability script
    assert len(_recs(b, "Dazzling Blades")) == 3 and kit.ws_stacks(e) == 3
    b2, (sampo2,), (e2,) = _battle([Build("1108", extra_stats={"ehr": 1.0})])
    sampo2.kit.ult(e2)  # 4 AoE hits of 25%
    assert len(_recs(b2, "Surprise Present")) == 4 and sampo2.kit.ws_stacks(e2) == 4


def test_sampo_technique_delay_uses_the_right_parameters():
    b, (sampo,), (e,) = _battle([Build("1108")])
    p = sampo.kit.sk("technique")["params"][0]  # [Blind seconds, fixed chance, delay]
    gauge = e.gauge
    sampo.kit.technique()
    assert e.gauge == pytest.approx(gauge + p[2] * F.AV_BASE)


def test_sampo_e4_checks_stacks_before_each_skill_hit():
    b, (sampo,), (e,) = _battle([Build("1108", eidolon=4, extra_stats={"ehr": 1.0})])
    kit = sampo.kit
    kit.wind_shear(e, 1.0, stacks=int(kit.ep(4, 0)) - 1)  # one stack short of the E4 threshold
    triggers = []
    b.events.on(E.DOT_TRIGGERED, lambda ev: triggers.append(ev))
    kit.skill(e)  # every hit lands on the only enemy and adds a stack after it hits
    hits = len(_recs(b, "Ricochet Love"))
    assert len(triggers) == hits - 1  # the first hit sees 4 stacks, every later one 5


# ----------------------------------------------------------------------- Hook
def test_hook_burn_talent_and_enhanced_skill():
    enemies = [Enemy(f"E{i}", hp=1e12, toughness=1e6, effect_res=0.0) for i in range(3)]
    b, (hook,), _ = _battle([Build("1109")], enemies=enemies)
    kit = hook.kit
    mid = enemies[1]
    kit.skill(mid)
    assert mid.has_mod("Burn (Hook)")
    assert not _recs(b, "Ha! Oil to the Flames!")  # the target was not Burned before the hit
    kit.skill(mid)
    assert len(_recs(b, "Ha! Oil to the Flames!")) == 1
    kit.ult(mid)
    assert kit.enhanced_skill
    assert len(_recs(b, "Ha! Oil to the Flames!")) == 2
    n0 = len(b.records)
    kit.skill(mid)
    assert not kit.enhanced_skill
    hit_targets = {r.target for r in b.records[n0:] if r.label == "Hey! Remember Hook?"}
    assert hit_targets == {"E0", "E1", "E2"}  # Enhanced Skill: blast


# ----------------------------------------------------------------------- Luka
def test_luka_fighting_will_enhanced_basic_detonates_bleed():
    b, (luka,), (e,) = _battle([Build("1111", traces=False)])
    kit = luka.kit
    assert kit.fighting_will == 1  # start of battle
    kit.skill(e)  # Bleed (100% base chance vs Effect RES 0) + 1 Fighting Will
    assert e.has_mod("Bleed (Luka)") and kit.fighting_will == 2
    sp0 = b.sp
    kit.basic(e)  # Sky-Shatter Fist: 3 Direct Punch + Rising Uppercut, consumes 2 stacks, +1 SP
    assert kit.fighting_will == 0 and b.sp == sp0 + 1
    assert len([r for r in b.records if r.label in ("Sky-Shatter Fist", "Rising Uppercut")]) == 4
    det = _recs(b, "Bleed (Luka)")
    assert len(det) == 1
    b.detonate(e, 1.0, kinds=("bleed",))  # a full Bleed instance for comparison
    full = _recs(b, "Bleed (Luka)")[-1].amount
    assert det[0].amount == pytest.approx(kit.p("talent", 1) * full)
