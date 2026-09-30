"""Audit fixes for the core-A kits: Seele, Bronya, Sparkle, Robin, Ruan Mei, Tingyun, Pela, Silver Wolf, Huohuo."""

import pytest

from hsrsim import events as E
from hsrsim import stats as S
from hsrsim.battle import Battle, BattleConfig
from hsrsim.build import Build, make_character
from hsrsim.entities import Enemy
from hsrsim.enums import ActionKind, Element, EnemyRank
from hsrsim.modifiers import Modifier, ModKind, Tick


def _battle(builds, n_enemies=1, waves=1, **cfg):
    chars = [make_character(b) for b in builds]
    wave_list = [
        [
            Enemy(f"Dummy {w}.{i}", hp=1e12, toughness=1e6, effect_res=0.0, weaknesses=list(Element))
            for i in range(n_enemies)
        ]
        for w in range(waves)
    ]
    b = Battle(chars, wave_list, BattleConfig(**cfg))
    b.start()
    return b, chars, b.enemies


def _always_succeed(b):
    b.rng.random = lambda: 0.0  # every chance roll succeeds


def _actions(b, who):
    out = []
    b.events.on(E.ACTION_START, lambda ev: ev.action.actor is who and out.append(ev.action.kind))
    return out


# ------------------------------------------------------------------- Seele
def test_1102_seele_e6_flurry_duration_from_data():
    b, (seele,), (e,) = _battle([Build("Seele", eidolon=6)])
    seele.kit.ult(e)
    flurry = e.get_mod("Butterfly Flurry")
    assert flurry is not None and flurry.duration == int(seele.kit.ep(6, 1))


def test_1102_seele_enhanced_nightshade_only_on_her_own_kills():
    b, (seele, bro), (e1, e2) = _battle([Build("Seele", enhanced=True), Build("Bronya")], n_enemies=2)
    b.events.emit(E.KILL, target=e1, killer=bro)  # another ally's kill: no Nightshade
    assert seele.get_mod("Nightshade") is None
    b.events.emit(E.KILL, target=e2, killer=seele)
    assert seele.get_mod("Nightshade") is not None


def test_1102_seele_enhanced_auto_skill_targets_lowest_hp():
    b, (seele, bro), (e1, e2) = _battle([Build("Seele", enhanced=True), Build("Bronya")], n_enemies=2)
    e1.hp = 0.4 * e1.max_hp
    e2.hp = 0.2 * e2.max_hp
    targets = []
    b.events.on(E.ACTION_START, lambda ev: ev.action.actor is seele and targets.append(ev.action.target))
    with b.action(bro, ActionKind.BASIC) as act:
        act.hit(e1, 0.0)
        act.hit(e2, 0.0)
    b.process_queue()
    assert targets == [e2]


# ------------------------------------------------------------------ Bronya
def test_1101_bronya_e1_one_turn_cooldown():
    b, (bro, ally), _ = _battle([Build("Bronya", eidolon=1), Build("Seele")], start_sp=5)
    _always_succeed(b)
    deltas = []
    for _ in range(3):
        bro.energy = 0.0
        before = b.sp
        b.take_turn(bro)
        deltas.append(b.sp - before)
    # proc (net 0 SP), cooldown turn (-1 SP), proc again (net 0)
    assert deltas == [0, -1, 0]


# ----------------------------------------------------------------- Sparkle
def test_1306_sparkle_red_herring_cipher_bonus_follows_cipher():
    b, (spk, seele), (e,) = _battle([Build("Sparkle"), Build("Seele")], start_sp=5)
    k = spk.kit
    k.ult(None)
    b.use_sp(1, seele)
    herring = seele.get_mod("Red Herring")
    assert herring is not None
    assert herring.value(S.DMG_PCT) == pytest.approx(k.p("talent", 1) + k.p("ult", 2))
    b.remove_named(seele, "Cipher")
    assert herring.value(S.DMG_PCT) == pytest.approx(k.p("talent", 1))


def test_1306_sparkle_a4_self_cast_lasts_until_the_turn_after_next():
    b, (spk,), (e,) = _battle([Build("Sparkle")])
    b.take_turn(spk)  # alone: the Skill targets Sparkle herself
    dd = spk.get_mod("Dreamdiver")
    assert dd is not None and dd.tick == Tick.HOLDER_TURN_START
    b._tick(spk, at_start=True)  # start of her next turn: still active
    assert spk.get_mod("Dreamdiver") is not None
    b._tick(spk, at_start=True)
    assert spk.get_mod("Dreamdiver") is None


def test_1306_sparkle_e6_spreads_only_to_teammates_with_cipher():
    b, (spk, seele, bro), (e,) = _battle(
        [Build("Sparkle", eidolon=6, options={"target": "Seele"}), Build("Seele"), Build("Bronya")], start_sp=5
    )
    spk.kit.ult(None)  # everyone gets Cipher
    spk.kit.skill(e)
    assert seele.get_mod("Dreamdiver") is not None and bro.get_mod("Dreamdiver") is not None
    assert spk.get_mod("Dreamdiver") is None  # "teammates" (AllTeammate) excludes Sparkle


def test_1306_sparkle_enhanced_technique_energy_scales_with_err():
    b, (spk,), _ = _battle([Build("Sparkle", enhanced=True, extra_stats={S.ERR: 0.2})], techniques=True)
    assert spk.energy == pytest.approx(spk.max_energy * 0.5 + spk.kit.sk("technique")["params"][0][1] * 1.2)


# ------------------------------------------------------------------- Robin
def test_1309_robin_technique_energy_every_wave():
    b, (robin,), _ = _battle([Build("Robin", extra_stats={S.ERR: 0.2})], waves=2, techniques=True)
    gain = robin.kit.sk("technique")["params"][0][1] * 1.2
    assert robin.energy == pytest.approx(robin.max_energy * 0.5 + gain)
    before = robin.energy
    for e in b.enemies:
        e.hp = 0.0
    b._reap()
    b.process_queue()
    assert b.wave_index == 1
    assert robin.energy == pytest.approx(before + gain)


# ---------------------------------------------------------------- Ruan Mei
def test_1303_ruan_mei_e4_break_effect_precedes_talent_break_dmg():
    b, (rm, seele), (e,) = _battle([Build("Ruan Mei", eidolon=4), Build("Seele")])
    seen = []
    b.events.on(
        E.AFTER_HIT, lambda ev: ev.hit.label == "Ruan Mei Talent Break" and seen.append(rm.has_mod("Chatoyant Eclat"))
    )
    b.weakness_break(e, seele, Element.QUANTUM, None)
    assert seen == [True]


def test_1303_ruan_mei_technique_is_a_skill_and_rotation_skill_basic_basic():
    b, (rm,), (e,) = _battle([Build("Ruan Mei")], techniques=True, start_sp=5)
    assert rm.get_mod("Overtone") is not None
    assert rm.energy == pytest.approx(rm.max_energy * 0.5 + rm.kit.sk("skill")["energy"])
    assert b.sp == 5  # the technique's Skill costs no SP
    kinds = _actions(b, rm)
    rm.energy = 0.0
    for _ in range(4):
        b.take_turn(rm)
    assert kinds == [ActionKind.BASIC, ActionKind.BASIC, ActionKind.SKILL, ActionKind.BASIC]


# ----------------------------------------------------------------- Tingyun
def test_1202_tingyun_a6_energy_scales_with_err():
    b, (ty,), _ = _battle([Build("Tingyun", extra_stats={S.ERR: 0.2})])
    before = ty.energy
    b.events.emit(E.TURN_START, entity=ty, extra=False)
    assert ty.energy - before == pytest.approx(ty.kit.tp(3, 0) * 1.2)


def test_1202_tingyun_benediction_atk_snapshot_at_cast():
    b, (ty, seele), (e,) = _battle([Build("Tingyun", options={"target": "Seele"}), Build("Seele")], start_sp=5)
    ty.kit.skill(e)
    bene = seele.get_mod("Benediction")
    assert bene is not None
    value = bene.value(S.ATK_FLAT)
    assert value == pytest.approx(min(ty.kit.p("skill", 1) * seele.raw(S.BASE_ATK), ty.kit.p("skill", 3) * ty.atk))
    b.apply(Modifier("test ATK", stats={S.ATK_PCT: 1.0}), ty, ty)
    assert bene.value(S.ATK_FLAT) == pytest.approx(value)


# -------------------------------------------------------------------- Pela
def _enemy_buff(b, e):
    b.apply(Modifier("Enemy Buff", stats={S.DEF_PCT: 0.1}, duration=5, kind=ModKind.BUFF), e, e)


def test_1106_pela_a6_next_attack_and_e2_spd_after_dispel():
    b, (pela,), (e,) = _battle([Build("Pela", eidolon=2)], start_sp=5)
    k = pela.kit
    hits = []
    b.events.on(E.AFTER_HIT, lambda ev: hits.append(ev.hit))
    k.skill(e)  # nothing to dispel: no A6 / E2
    assert pela.get_mod("Wipe Out") is None and pela.get_mod("Adamant Charge") is None
    _enemy_buff(b, e)
    k.skill(e)
    assert e.get_mod("Enemy Buff") is None
    assert pela.get_mod("Wipe Out") is not None
    spd = pela.get_mod("Adamant Charge")
    assert spd is not None and spd.stats[S.SPD_PCT] == pytest.approx(k.ep(2, 0))
    assert spd.duration == int(k.ep(2, 1))
    hits.clear()
    k.basic(e)
    assert pela.get_mod("Wipe Out") is None  # consumed by that attack
    with_bonus = hits[0].parts.dmg_boost
    hits.clear()
    k.basic(e)
    assert with_bonus - hits[0].parts.dmg_boost == pytest.approx(k.tp(3, 0))


def test_1106_pela_e4_before_skill_dmg_and_turn_start_tick():
    b, (pela,), (e,) = _battle([Build("Pela", eidolon=4)], start_sp=5)
    seen = []
    b.events.on(E.BEFORE_HIT, lambda ev: seen.append(e.has_mod("Full Analysis")))
    pela.kit.skill(e)
    assert seen and seen[0]
    assert e.get_mod("Full Analysis").tick == Tick.HOLDER_TURN_START


def test_1106_pela_technique_damage_and_turn_start_tick():
    b, (pela,), (e,) = _battle([Build("Pela")], techniques=True)
    assert any(r.label == "Pela Technique" for r in b.records)
    assert e.get_mod("Pela Technique").tick == Tick.HOLDER_TURN_START


# ------------------------------------------------------------- Silver Wolf
@pytest.mark.parametrize("enhanced", [False, True])
def test_1006_silver_wolf_shreds_tick_at_turn_start(enhanced):
    b, (sw,), (e,) = _battle([Build("Silver Wolf", enhanced=enhanced)], start_sp=5)
    _always_succeed(b)
    sw.kit.skill(e)
    sw.kit.ult(e)
    assert e.get_mod("Allow Changes?").tick == Tick.HOLDER_TURN_START
    assert e.get_mod("User Banned").tick == Tick.HOLDER_TURN_START


def test_1006_silver_wolf_a6_counts_debuffs_before_the_implant():
    b, (sw, seele), (e,) = _battle([Build("Silver Wolf"), Build("Seele")], start_sp=5)
    _always_succeed(b)
    k = sw.kit
    e.weaknesses.discard(Element.QUANTUM)  # Seele's Quantum can be implanted
    for i in range(2):
        b.apply(Modifier(f"Other {i}", duration=5, kind=ModKind.DEBUFF), e, seele)
    k.skill(e)  # 2 debuffs when the Skill is used: no A6 bonus even though the implant makes it 3
    assert e.get_mod("Implanted Weakness") is not None
    assert e.get_mod("Allow Changes?").stats[S.RES_REDUCTION] == pytest.approx(k.p("skill", 5))
    k.skill(e)
    assert e.get_mod("Allow Changes?").stats[S.RES_REDUCTION] == pytest.approx(k.p("skill", 5) + k.tp(3, 1))


def test_1006_silver_wolf_technique_hits_all_enemies_ignoring_weakness():
    e1, e2 = (Enemy(f"Fire-weak {i}", hp=1e12, weaknesses=[Element.FIRE]) for i in range(2))
    b = Battle([make_character(Build("Silver Wolf"))], [[e1, e2]], BattleConfig(techniques=True))
    b.start()
    hits = [r for r in b.records if r.label == "Silver Wolf Technique"]
    assert len(hits) == 2
    assert e1.toughness < e1.max_toughness and e2.toughness < e2.max_toughness


def test_1006_silver_wolf_bug_prefers_missing_types():
    b, (sw,), (e,) = _battle([Build("Silver Wolf")])
    _always_succeed(b)
    for _ in range(3):
        sw.kit.bug(e, 1.0)
    assert all(e.get_mod(f"Bug ({t})") is not None for t in ("ATK", "DEF", "SPD"))


def test_1006_silver_wolf_enhanced_a4_energy_and_implant_transfer():
    b, (sw,), (e1, e2) = _battle([Build("Silver Wolf", enhanced=True, extra_stats={S.ERR: 0.2})], n_enemies=2)
    k = sw.kit
    sw.energy = 0.0
    k.on_battle_start()
    assert sw.energy == pytest.approx(k.tp(2, 0) * 1.2)
    _always_succeed(b)
    e1.weaknesses.discard(Element.QUANTUM)
    e2.weaknesses.discard(Element.QUANTUM)
    e2.rank = EnemyRank.BOSS
    k.skill(e1)
    assert e1.is_weak_to(Element.QUANTUM) and not e2.is_weak_to(Element.QUANTUM)
    e1.hp = 0.0
    b._reap()
    moved = e2.get_mod("Implanted Weakness")
    assert moved is not None and e2.is_weak_to(Element.QUANTUM)
    assert moved.stats[f"{S.RES_REDUCTION}:Quantum"] == pytest.approx(k.p("skill", 3))


# ------------------------------------------------------------------ Huohuo
def test_1217_huohuo_enhanced_e1_values():
    b, (hh, seele), _ = _battle([Build("Huohuo", enhanced=True, eidolon=1), Build("Seele")])
    k = hh.kit
    k.skill(None)
    assert seele.stat(S.SPD_PCT) == pytest.approx(k.ep(1, 2))  # 12%, not the 1-turn extension param
    with_dp = hh.stat(S.HEAL_PCT)
    b.remove_named(hh, "Divine Provision")
    assert with_dp - hh.stat(S.HEAL_PCT) == pytest.approx(k.ep(1, 1))
    assert seele.stat(S.HEAL_PCT) == pytest.approx(0.0)  # Outgoing Healing is Huohuo's only


def test_1217_huohuo_skill_heals_adjacent_and_e6_buffs_them():
    b, (a, hh, c, d), _ = _battle(
        [Build("Seele"), Build("Huohuo", eidolon=6, options={"target": "Seele"}), Build("Bronya"), Build("Tingyun")],
        start_sp=5,
    )
    for x in (a, hh, c, d):
        x.hp = 1.0
    hh.kit.skill(None)
    k = hh.kit
    assert a.hp > 1.0 and hh.hp > 1.0  # target (slot 0) and its adjacent ally (slot 1)
    assert a.get_mod("Woven Together") is not None and hh.get_mod("Woven Together") is not None
    assert c.get_mod("Woven Together") is None
    adj = (k.p("skill", 2) * hh.max_hp + k.p("skill", 3)) * (1.0 + hh.stat(S.HEAL_PCT))
    assert hh.hp == pytest.approx(min(hh.max_hp, 1.0 + adj))


def test_1217_huohuo_talent_heals_low_hp_allies_with_a6_energy():
    b, (hh, a, c), _ = _battle([Build("Huohuo", options={"target": "Seele"}), Build("Seele"), Build("Bronya")])
    k = hh.kit
    k._provision(2)
    a.hp = 0.6 * a.max_hp
    c.hp = 1.0
    hh.energy = 0.0
    b.events.emit(E.TURN_START, entity=a, extra=False)  # heals Seele, then Bronya (at or below 50% HP)
    assert a.hp > 0.6 * a.max_hp and c.hp > 1.0
    assert hh.energy == pytest.approx(2 * k.tp(3, 0))
    assert k.triggers_left == int(k.p("talent", 6)) - 1


def test_1217_huohuo_rotation_recasts_only_when_provision_expired():
    b, (hh,), (e,) = _battle([Build("Huohuo")], start_sp=5)
    kinds = _actions(b, hh)
    for _ in range(3):
        hh.energy = 0.0
        b.take_turn(hh)
    assert kinds == [ActionKind.SKILL, ActionKind.BASIC, ActionKind.SKILL]


def test_1217_huohuo_basic_uses_data_splits_and_enhanced_a2_energy():
    b, (hh,), (e,) = _battle([Build("Huohuo")])
    hits = []
    b.events.on(E.AFTER_HIT, lambda ev: hits.append(ev.hit))
    hh.kit.basic(e)
    assert [h.ratio for h in hits] == pytest.approx([0.2, 0.2, 0.2, 0.4])
    b, (hh,), _ = _battle([Build("Huohuo", enhanced=True, extra_stats={S.ERR: 0.2})])
    hh.energy = 0.0
    hh.kit.on_battle_start()
    assert hh.energy == pytest.approx(hh.kit.tp(1, 0) * 1.2)
