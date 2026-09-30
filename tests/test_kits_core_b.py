"""Targeted checks for the core-kit audit, group B: Jing Yuan, Kafka, Black Swan, Acheron, Firefly,
Trailblazer (Harmony), Yao Guang and Sparxie (base and enhanced kits)."""

import pytest

from hsrsim import events as E
from hsrsim import stats as S
from hsrsim.battle import Action, Battle, BattleConfig
from hsrsim.build import Build, make_character
from hsrsim.entities import Enemy
from hsrsim.enums import ActionKind, DmgTag, Element
from hsrsim.modifiers import DotModifier

from .helpers import generic_build


def _idle(e, b):  # enemy AI that does nothing (keeps Energy/HP bookkeeping out of the way)
    return None


def _dummies(n, **kw):
    kw.setdefault("effect_res", 0.0)
    kw.setdefault("hp", 1e12)
    return [Enemy(f"Dummy {i}", ai=_idle, **kw) for i in range(n)]


def _battle(builds, enemies=None, waves=None, **cfg):
    chars = [make_character(b) for b in builds]
    battle = Battle(chars, waves or [enemies or _dummies(1)], BattleConfig(**cfg))
    battle.start()
    return battle, chars


def _hits(battle):
    out = []
    battle.events.on(E.AFTER_HIT, lambda ev: out.append(ev.hit))
    return out


# ------------------------------------------------------------------ Jing Yuan
def test_jing_yuan_a4_battle_start_energy_scales_with_err():
    b, (jy,) = _battle([Build("Jing Yuan", extra_stats={S.ERR: 0.194})])
    # MAvatar_JingYuan_00_SkillTree02 uses ModifySPNew AddValue (ERR-scaled), not FixedAddValue
    assert jy.energy == pytest.approx(0.5 * jy.max_energy + jy.kit.tp(2, 0) * 1.194)


def test_jing_yuan_skill_splits_40_30_30_on_every_enemy():
    b, (jy,) = _battle([Build("Jing Yuan")], _dummies(3))
    hits = _hits(b)
    jy.kit.skill(b.enemies[1])
    for e in b.enemies:
        assert [round(h.ratio, 3) for h in hits if h.target is e] == [0.4, 0.3, 0.3]


def test_jing_yuan_a2_crit_dmg_buff_sits_on_jing_yuan_through_his_next_turn():
    b, (jy,) = _battle([Build("Jing Yuan")])
    kit = jy.kit
    kit._set_hits(int(kit.tp(1, 0)))
    b.current_turn = kit.ll
    kit._ll_turn(kit.ll, b)
    b.current_turn = None
    mod = jy.get_mod("Battalia Crush")
    assert mod is not None and mod.stats[S.CRIT_DMG] == pytest.approx(kit.tp(1, 1))
    seen = []
    b.events.on(E.AFTER_HIT, lambda ev: seen.append(jy.has_mod("Battalia Crush")))
    jy.energy = 0.0
    b.take_turn(jy)  # his own Skill still benefits, then the buff expires at his turn end
    assert seen and all(seen)
    assert not jy.has_mod("Battalia Crush")


# ---------------------------------------------------------------------- Kafka
def test_kafka_follow_up_uses_the_six_hit_split():
    b, (kafka, mate) = _battle([Build("Kafka"), generic_build("Bronya")])
    hits = _hits(b)
    mate.kit.basic(b.enemies[0])
    b.process_queue()
    fua = [h for h in hits if h.action is not None and h.action.kind == ActionKind.FUA]
    assert [round(h.ratio, 3) for h in fua] == [0.15, 0.15, 0.15, 0.15, 0.15, 0.25]


@pytest.mark.parametrize("enhanced", [False, True])
def test_kafka_skill_splits_main_target_then_one_adjacent_hit(enhanced):
    b, (kafka,) = _battle([Build("Kafka", enhanced=enhanced)], _dummies(3))
    hits = _hits(b)
    kafka.kit.skill(b.enemies[1])
    skill_hits = [h for h in hits if DmgTag.SKILL in h.tags]
    assert [(h.target.name, round(h.ratio, 2)) for h in skill_hits] == [
        ("Dummy 1", 0.2),
        ("Dummy 1", 0.3),
        ("Dummy 1", 0.5),
        ("Dummy 0", 1.0),
        ("Dummy 2", 1.0),
    ]


def test_enhanced_kafka_ult_detonates_dots_even_if_shock_is_resisted():
    b, (kafka,) = _battle([Build("Kafka", enhanced=True)], _dummies(1, effect_res=1.0))
    target = b.enemies[0]
    ratios = []
    b.apply(DotModifier("Burn (other)", dot_type="burn", damage_fn=lambda m, bt, r: ratios.append(r) or 0.0), target)
    kafka.kit.ult(target)
    assert not target.has_tag("shock")  # 100% Effect RES: the Shock never lands
    assert ratios == [pytest.approx(kafka.kit.p("ult", 4))]


def test_enhanced_kafka_e1_lands_before_the_skill_detonation():
    b, (kafka,) = _battle([Build("Kafka", enhanced=True, eidolon=1)])
    target = b.enemies[0]
    kafka.kit.shock(target, 1.0)
    hits = _hits(b)
    kafka.kit.skill(target)
    shock = [h for h in hits if h.label == "Shock (Kafka)"]
    assert shock, "the Skill detonates the Shock"
    assert shock[0].parts.vuln_mult == pytest.approx(1.0 + kafka.kit.ep(1, 1))


# ----------------------------------------------------------------- Black Swan
def test_black_swan_a4_arcana_is_applied_once_to_wave_one_enemies():
    b, (bs,) = _battle([Build("Black Swan", extra_stats={S.EHR: 1.0})], _dummies(3))
    assert [e.get_mod("Arcana").stacks for e in b.enemies] == [1, 1, 1]


def test_enhanced_black_swan_e2_inflicts_thirty_stacks_once():
    b, (bs,) = _battle([Build("Black Swan", enhanced=True, eidolon=2, extra_stats={S.EHR: 1.0})], _dummies(2))
    # E2 (30) + A4 (1) on entering combat, applied once
    assert [e.get_mod("Arcana").stacks for e in b.enemies] == [31, 31]


def test_black_swan_epiphany_alone_is_not_a_dot_but_arcana_with_epiphany_is_all_four():
    b, (bs,) = _battle([Build("Black Swan")])
    target = b.enemies[0]
    b.remove_named(target, "Arcana")
    bs.kit.ult(target)
    assert target.has_mod("Epiphany")
    assert not any(target.has_tag(k) for k in ("wind_shear", "bleed", "burn", "shock"))
    bs.kit.add_arcana(target, 1, 1.0, fixed=True)
    assert all(target.has_tag(k) for k in ("wind_shear", "bleed", "burn", "shock"))


def test_black_swan_epiphany_counts_down_at_the_enemy_turn_start_and_e4_energy_once():
    b, (bs,) = _battle([Build("Black Swan", eidolon=4)])
    target = b.enemies[0]
    bs.kit.ult(target)
    bs.energy = 0.0
    b.take_turn(target)
    assert target.get_mod("Epiphany").duration == 1
    assert bs.energy == pytest.approx(bs.kit.ep(4, 1))
    b.take_turn(target)  # second turn start: DoTs, then Epiphany expires (ModifierPhase1End)
    assert not target.has_mod("Epiphany")
    assert bs.energy == pytest.approx(bs.kit.ep(4, 1))  # once per Epiphany


def test_black_swan_e2_spreads_arcana_to_adjacent_enemies_on_kill():
    b, (bs,) = _battle([Build("Black Swan", eidolon=2, extra_stats={S.EHR: 1.0})], _dummies(3))
    before = [e.get_mod("Arcana").stacks for e in b.enemies]
    b.enemies[1].hp = 0.0
    b._reap()
    assert b.enemies[0].get_mod("Arcana").stacks == before[0] + int(bs.kit.ep(2, 1))
    assert b.enemies[2].get_mod("Arcana").stacks == before[2] + int(bs.kit.ep(2, 1))


def test_black_swan_a4_attack_cap_is_per_action():
    b, (bs,) = _battle([Build("Black Swan", extra_stats={S.EHR: 1.0})])
    target = b.enemies[0]
    b.remove_named(target, "Arcana")
    dot = DotModifier("Burn (other)", dot_type="burn", damage_fn=lambda m, bt, r: 0.0)
    for act in (Action(b, bs, ActionKind.SKILL), Action(b, bs, ActionKind.SKILL)):
        for _ in range(5):
            bs.kit._on_dot(E.Ev(E.DOT_TRIGGERED, {"mod": dot, "target": target, "turn_start": False, "action": act}))
    assert target.get_mod("Arcana").stacks == 2 * int(bs.kit.tp(2, 1))


def test_black_swan_talent_ignores_freeze_at_turn_start():
    b, (bs,) = _battle([Build("Black Swan", traces=False, extra_stats={S.EHR: 1.0})])
    target = b.enemies[0]
    b.remove_named(target, "Arcana")
    frozen = DotModifier("Frozen", dot_type="freeze", damage_fn=lambda m, bt, r: 0.0, is_dot=False)
    bs.kit._on_dot(E.Ev(E.DOT_TRIGGERED, {"mod": frozen, "target": target, "turn_start": True, "action": None}))
    assert not target.has_mod("Arcana")


def test_black_swan_technique_rolls_arcana_repeatedly():
    b, (bs,) = _battle([Build("Black Swan", traces=False, extra_stats={S.EHR: 1.0})], techniques=True)
    # base chance 150% x 2 (EHR) then halved after every success: at least two guaranteed stacks
    assert b.enemies[0].get_mod("Arcana").stacks >= 2


@pytest.mark.parametrize("enhanced", [False, True])
def test_black_swan_e6_arcana_lands_before_the_teammate_hit(enhanced):
    b, (bs, mate) = _battle(
        [Build("Black Swan", enhanced=enhanced, eidolon=6, extra_stats={S.EHR: 1.0}), generic_build("Bronya")]
    )
    target = b.enemies[0]
    b.remove_named(target, "Arcana")
    seen = []
    b.events.on(E.AFTER_HIT, lambda ev: ev.hit.attacker is mate and seen.append(target.has_mod("Arcana")))
    mate.kit.basic(target)
    assert seen == [True]


def test_enhanced_black_swan_adjacent_arcana_dot_rolls_arcana():
    b, (bs,) = _battle([Build("Black Swan", enhanced=True, extra_stats={S.EHR: 1.0})], _dummies(3))
    for e in b.enemies:
        b.remove_named(e, "Arcana")
    bs.kit.add_arcana(b.enemies[1], 1, 1.0, fixed=True)
    b.take_turn(b.enemies[1])
    assert b.enemies[0].has_mod("Arcana") and b.enemies[2].has_mod("Arcana")


# -------------------------------------------------------------------- Acheron
def test_acheron_crimson_knot_is_not_a_debuff():
    b, (ach,) = _battle([Build("Acheron", eidolon=1)])
    target = b.enemies[0]
    ach.kit.skill(target)
    assert ach.kit.knots(target) > 0
    assert target.debuffs == []


def test_acheron_e4_is_applied_once_per_enemy():
    chars = [make_character(Build("Acheron", eidolon=4))]
    b = Battle(chars, [_dummies(2)])
    applied = []
    b.events.on(E.MOD_APPLIED, lambda ev: ev.mod.name == "Shrined Fire" and applied.append(ev.target.name))
    b.start()
    assert applied == ["Dummy 0", "Dummy 1"]


def test_acheron_rainblade_locks_onto_the_most_knotted_enemy():
    b, (ach,) = _battle([Build("Acheron", traces=False)], _dummies(3))
    ach.kit.add_knots(b.enemies[2], 3)
    hits = _hits(b)
    ach.kit.sd = ach.kit.sd_max
    ach.kit.use_ult()  # the Ultimate's chosen target is Dummy 0 (default), which has no Crimson Knot
    first = next(h for h in hits if h.label == "Rainblade")
    assert first.target is b.enemies[2]
    assert any(h.label == "Rainblade (Crimson Knot)" for h in hits)


def test_acheron_thunder_core_stack_buffs_its_own_rainblade():
    b, (ach,) = _battle([Build("Acheron")])
    target = b.enemies[0]
    seen = []
    b.events.on(E.AFTER_HIT, lambda ev: ev.hit.label == "Rainblade" and seen.append(ach.has_mod("Thunder Core")))
    ach.kit.sd = ach.kit.sd_max
    assert ach.kit.knots(target) > 0
    ach.kit.use_ult()
    assert seen and seen[0] is True


def test_acheron_technique_triggers_at_every_wave():
    waves = [_dummies(1, hp=1.0), _dummies(1)]
    b, (ach,) = _battle([Build("Acheron")], waves=waves, techniques=True)
    tech = {r.wave for r in b.records if r.label == "Quadrivalent Ascendance (technique)"}
    assert tech == {0, 1}


# -------------------------------------------------------------------- Firefly
@pytest.mark.parametrize("enhanced", [False, True])
def test_firefly_hit_splits(enhanced):
    b, (ff,) = _battle([Build("Firefly", enhanced=enhanced)], _dummies(3))
    hits = _hits(b)
    ff.kit.skill(b.enemies[1])
    assert [round(h.ratio, 2) for h in hits if DmgTag.SKILL in h.tags] == [0.4, 0.6]
    ff.energy = ff.max_energy
    ff.kit.use_ult()
    hits.clear()
    ff.kit.basic(b.enemies[1])
    assert [round(h.ratio, 2) for h in hits if DmgTag.BASIC in h.tags] == [0.15, 0.15, 0.15, 0.15, 0.4]
    hits.clear()
    ff.kit.skill(b.enemies[1])
    rounds = [[h.target.name for h in hits if DmgTag.SKILL in h.tags][i : i + 3] for i in range(0, 15, 3)]
    assert rounds == [["Dummy 1", "Dummy 0", "Dummy 2"]] * 5  # target, then adjacent, five times


def test_enhanced_firefly_uses_its_own_records_at_their_skill_level():
    b, (ff,) = _battle([Build("Firefly", enhanced=True)], _dummies(3))
    kit = ff.kit
    ff.energy = ff.max_energy
    kit.use_ult()
    hits = _hits(b)
    kit.basic(b.enemies[1])
    rec = kit.sk("1131008")
    assert sum(h.mult["atk"] for h in hits) == pytest.approx(rec["params"][kit.level_of(rec) - 1][0])
    assert kit.level_of(rec) > 1  # the base-kit ID 131008 would be read at Lv. 1 for the enhanced variant


def test_enhanced_firefly_skill_weakness_lasts_two_turns_and_heals():
    b, (ff,) = _battle([Build("Firefly", enhanced=True)], _dummies(3))
    ff.energy = ff.max_energy
    ff.kit.use_ult()
    ff.hp = 0.1 * ff.max_hp
    ff.kit.skill(b.enemies[1])
    for e in b.enemies:
        assert e.get_mod("Fire Weakness (Firefly)").duration == 2
    assert ff.hp == pytest.approx(0.35 * ff.max_hp)


def test_enhanced_firefly_a2_delays_the_countdown_for_every_break():
    b, (ff,) = _battle([Build("Firefly", enhanced=True)], _dummies(3, toughness=1.0, weaknesses=[Element.FIRE]))
    kit = ff.kit
    ff.energy = ff.max_energy
    kit.use_ult()
    gauge = kit.countdown.gauge
    kit.skill(b.enemies[1])  # breaks all three enemies
    assert kit.delays_left == 0
    assert kit.countdown.gauge == pytest.approx(gauge + 3 * kit.tp(1, 1) * 10000)


def test_firefly_technique_triggers_at_every_wave():
    waves = [_dummies(1, hp=1.0), _dummies(1)]
    b, (ff,) = _battle([Build("Firefly")], waves=waves, techniques=True)
    assert {r.wave for r in b.records if r.label == "Firefly Technique"} == {0, 1}
    assert b.enemies[0].has_mod("Fire Weakness (Firefly)")


# ------------------------------------------------------ Trailblazer (Harmony)
@pytest.mark.parametrize("cid", ["8005", "8006"])
def test_trailblazer_harmony_e1_recovers_skill_points_after_the_first_skill_only(cid):
    b, (tb,) = _battle([Build(cid, eidolon=1)])
    b.sp = 3
    tb.kit.skill(b.enemies[0])
    assert b.sp == 3 - 1 + int(tb.kit.ep(1, 0))
    tb.kit.skill(b.enemies[0])
    assert b.sp == 2 - 1 + int(tb.kit.ep(1, 0))


# ------------------------------------------------------------------ Yao Guang
@pytest.mark.parametrize("eidolon", [0, 2])
def test_yao_guang_zone_converts_her_own_elation_too(eidolon):
    # traces off: the A2 SPD -> Elation bonus would change with the E2 SPD of the Zone
    b, (yg, mate) = _battle([Build("Yao Guang", eidolon=eidolon, traces=False), generic_build("Bronya")])
    kit = yg.kit
    kit.skill(b.enemies[0])
    zone = kit.zone
    own = kit._elation_before_zone(zone)
    e2 = kit.ep(2, 0) if eidolon >= 2 else 0.0
    gain = kit.p("skill", 1) * (own + e2) + e2
    assert yg.stat(S.ELATION_DMG_PCT) == pytest.approx(own + gain)
    assert mate.stat(S.ELATION_DMG_PCT) == pytest.approx(gain)
    b.remove_modifier(zone)
    assert yg.stat(S.ELATION_DMG_PCT) == pytest.approx(own)  # the E2 Elation ends with the Zone
    assert mate.stat(S.ELATION_DMG_PCT) == pytest.approx(0.0)


def test_yao_guang_woes_whisper_is_guaranteed():
    b, (yg,) = _battle([Build("Yao Guang")], _dummies(3, effect_res=1.0))
    yg.kit.elation_skill(10)
    assert all(e.has_mod("Woe's Whisper") for e in b.enemies)


def test_yao_guang_e4_flag_is_cleared_when_the_aha_turn_ends_the_wave():
    waves = [_dummies(1, hp=1.0), _dummies(1)]
    b, (yg,) = _battle([Build("Yao Guang", eidolon=4)], waves=waves)
    kit = yg.kit
    yg.energy = yg.max_energy
    kit.use_ult()
    b.process_queue()
    assert b.wave_index == 1
    assert not kit.e4_turn
    assert not yg.has_mod("Threads of Fate (E4)")


def test_yao_guang_technique_is_a_free_skill():
    b, (yg,) = _battle([Build("Yao Guang")], techniques=True)
    assert b.sp == 3
    assert yg.kit.zone is not None and not yg.kit.zone.removed
    assert b.elation.total_gained >= int(yg.kit.p("skill", 2))
    energy = yg.kit.sk("skill")["energy"]
    energy = energy[0] if isinstance(energy, list) else energy
    assert yg.energy == pytest.approx(0.5 * yg.max_energy + energy)


# -------------------------------------------------------------------- Sparxie
def test_sparxie_engagement_farming_accounting_and_bloom_multiplier():
    opts = {"straight_fire_chance": 1.0, "farming": 3, "sp_reserve": 0}
    b, (sp,) = _battle([Build("Sparxie", options=opts)], _dummies(3))
    kit = sp.kit
    farm = kit.sk("150109")
    flv = farm["params"][kit.level_of(farm) - 1]
    bloom = kit.sk("150108")
    blv = bloom["params"][kit.level_of(bloom) - 1]
    b.sp = 1
    gained = b.elation.total_gained
    hits = _hits(b)
    kit.livestream(b.enemies[1])
    # 3 farms, each paid with 1 SP and returning "Straight Fire" SP; Bloom adds its own SP
    assert b.sp == min(b.max_sp, 1 + 3 * (int(flv[0]) - 1) + 1)
    assert b.elation.total_gained - gained == 3 * int(flv[2])
    main = [h for h in hits if h.target is b.enemies[1] and DmgTag.BASIC in h.tags]
    assert main[0].mult["atk"] == pytest.approx(blv[0] + 3 * flv[3])
