"""Targeted checks of distinctive mechanics for the batch-2 kits (real kits, no gear)."""

import pytest

from hsrsim import events as E
from hsrsim import stats as S
from hsrsim.battle import Battle, BattleConfig
from hsrsim.build import Build, make_character
from hsrsim.entities import Enemy
from hsrsim.enums import Element


def _battle(builds, n_enemies=1, **cfg):
    chars = [make_character(b) for b in builds]
    enemies = [
        Enemy(f"Dummy {i}", hp=1e12, toughness=1e6, effect_res=0.0, weaknesses=list(Element)) for i in range(n_enemies)
    ]
    b = Battle(chars, [enemies], BattleConfig(**cfg))
    b.start()
    return b, chars, enemies


def _hits(b):
    out = []
    b.events.on(E.AFTER_HIT, lambda ev: out.append(ev.hit))
    return out


def _main_base(hits, label=None):
    """Base DMG on the main target summed over the hit splits of an action."""
    return sum(h.base for h in hits if h.primary and (label is None or h.label == label))


# ------------------------------------------------------------------ Gepard
def test_gepard_shield_freeze_and_revive():
    b, (gep, bro), (e,) = _battle([Build("Gepard", eidolon=1), Build("Bronya")])
    k = gep.kit
    gep.energy = gep.max_energy
    gep.kit.use_ult()
    expected = k.p("ult", 0) * gep.defense + k.p("ult", 2)
    for c in (gep, bro):
        assert b.shield_value(c) == pytest.approx(expected)
    # E1: 65% + 35% base chance vs 0% Effect RES -> guaranteed Freeze that skips the enemy's turn
    k.skill(e)
    frozen = e.get_mod("Frozen (Gepard)")
    assert frozen is not None and frozen.skip_turn
    # Talent: a killing blow (HP floored at 1) restores HP to 50% and (A4) refills Energy once per battle
    gep.energy = 0.0
    b.lose_hp(gep, 1e9, e)
    assert gep.hp == pytest.approx(k.p("talent", 0) * gep.max_hp)
    assert gep.energy == pytest.approx(gep.max_energy)
    b.lose_hp(gep, 1e9, e)
    assert gep.hp == pytest.approx(1.0)


def test_gepard_a6_atk_from_def():
    b, (gep,), _ = _battle([Build("Gepard")])
    grit = gep.get_mod("Grit")
    assert grit is not None
    assert grit.value(S.ATK_FLAT) == pytest.approx(gep.kit.tp(3, 0) * gep.defense)


# ----------------------------------------------------------------- Natasha
def test_natasha_skill_heal_and_heal_over_time():
    b, (nat, bro), (e,) = _battle([Build("Natasha", options={"target": "Bronya"}), Build("Bronya")])
    k = nat.kit
    bro.hp = 1.0  # below the Talent's 30% threshold: +50% outgoing healing
    bonus = 1.0 + nat.stat(S.HEAL_PCT) + k.p("talent", 1)
    k.skill(e)
    assert bro.hp == pytest.approx(1.0 + (k.p("skill", 0) * nat.max_hp + k.p("skill", 3)) * bonus)
    hot = bro.get_mod("Love, Heal, and Choose")
    assert hot is not None and hot.duration == int(k.p("skill", 2) + k.tp(3, 0))  # A6: +1 turn
    before = bro.hp
    b.take_turn(bro)
    assert bro.hp > before  # continuous healing at the start of the ally's turn


def test_natasha_e6_basic_adds_max_hp_scaling():
    b, (nat,), (e,) = _battle([Build("Natasha", eidolon=6)])
    hits = _hits(b)
    nat.kit.basic(e)
    k = nat.kit
    assert _main_base(hits) == pytest.approx(k.p("basic", 0) * nat.atk + k.ep(6, 0) * nat.max_hp)


# ------------------------------------------------------------------- Clara
def test_clara_counter_marks_and_enhanced_counter():
    b, (clara,), (e,) = _battle([Build("Clara")])
    k = clara.kit
    b.enemy_basic_attack(e)
    b.process_queue()
    counters = [r for r in b.records if r.label == "Svarog Counter"]
    assert len(counters) == 1 and "fua" in counters[0].tags
    assert e.has_mod("Mark of Counter")
    hits = _hits(b)
    k.skill(e)  # bonus hit on the marked enemy, then marks are removed (E0)
    assert [h.label for h in hits] == ["Svarog Watches Over You", "Svarog Watches Over You (Mark)"]
    assert not e.has_mod("Mark of Counter")
    clara.energy = clara.max_energy
    k.use_ult()
    assert k.enhanced_left == int(k.p("ult", 4))
    hits.clear()
    b.enemy_basic_attack(e)
    b.process_queue()
    assert k.enhanced_left == int(k.p("ult", 4)) - 1
    fua = [h for h in hits if h.label == "Svarog Enhanced Counter"]
    base = (k.p("talent", 1) + k.p("ult", 1)) * clara.atk
    assert fua and _main_base(fua) == pytest.approx(base)
    assert fua[0].extra[S.DMG_PCT] == pytest.approx(k.tp(3, 0))  # A6 Revenge


# -------------------------------------------------------------------- Lynx
def test_lynx_survival_response_max_hp():
    b, (lynx, clara), (e,) = _battle([Build("Lynx", options={"target": "Clara"}), Build("Clara")])
    k = lynx.kit
    hp0 = clara.max_hp
    k.skill(e)
    sr = clara.get_mod("Survival Response")
    assert sr is not None
    assert clara.max_hp - hp0 == pytest.approx(k.p("skill", 0) * lynx.max_hp + k.p("skill", 1))
    assert sr.value(S.AGGRO_PCT) == pytest.approx(k.p("skill", 5))  # Destruction target: aggro up
    assert clara.has_mod("Outdoor Survival Experience")  # Talent continuous healing


# ------------------------------------------------------------------- Topaz
def test_topaz_proof_of_debt_and_numby_advance():
    b, (topaz,), (e1, e2) = _battle([Build("Topaz")], n_enemies=2)
    k = topaz.kit
    numby = k.numby
    assert numby is not None and numby.spd == pytest.approx(k.p("talent", 0))
    k.skill(e1)
    k.skill(e2)  # Proof of Debt only on the most recent target
    assert e2.has_mod("Proof of Debt") and not e1.has_mod("Proof of Debt")
    assert e2.stat(f"{S.VULN}:fua") == pytest.approx(k.p("skill", 1))
    numby.gauge = 10000.0
    k.basic(e2)  # A2: the Basic ATK counts as a Follow-Up ATK -> Numby advanced by 50%
    assert numby.gauge == pytest.approx(10000.0 * (1 - k.p("talent", 2)))
    hits = _hits(b)
    topaz.energy = topaz.max_energy
    k.use_ult()
    b.take_turn(numby)
    assert _main_base(hits) == pytest.approx((k.p("talent", 1) + k.p("ult", 0)) * topaz.atk)
    assert hits[0].extra[S.CRIT_DMG] == pytest.approx(k.p("ult", 1))
    assert k.windfall_left == int(k.p("ult", 3)) - 1


# ----------------------------------------------------------------- Qingque
def test_qingque_skill_stacks_and_hidden_hand():
    b, (qq,), (e1, e2, e3) = _battle([Build("Qingque")], n_enemies=3, start_sp=5)
    k = qq.kit
    atk0 = qq.stat(S.ATK_PCT)
    k.hand = [0, 1]
    k.skill(e2)
    k.skill(e2)
    stacks = qq.get_mod("A Scoop of Moon")
    assert stacks.stacks == 2
    assert qq.stat(S.DMG_PCT) == pytest.approx(2 * (k.p("skill", 1) + k.tp(2, 0)))
    assert b.sp == 5 - 2 + 1  # A2: the first Skill of the battle restores 1 SP
    k.hidden_hand = False  # the random draws above may already have completed a suit
    b.remove_named(qq, "Hidden Hand")
    k.hand = [2, 2, 2, 2]
    k._check_hidden_hand()
    assert k.hidden_hand and k.hand == []
    assert qq.stat(S.ATK_PCT) - atk0 == pytest.approx(k.p("talent", 0))
    sp = b.sp
    hits = _hits(b)
    k.basic(e2)  # "Cherry on Top!": Blast, no SP recovery, ends Hidden Hand
    assert {h.target.name for h in hits} == {"Dummy 0", "Dummy 1", "Dummy 2"}
    assert all(h.label == "Cherry on Top!" for h in hits)
    assert b.sp == sp
    assert not k.hidden_hand and not qq.has_mod("Hidden Hand")


# ------------------------------------------------------------------ Luocha
def test_luocha_zone_after_two_flowers_heals_attacker():
    b, (luo, bro), (e,) = _battle([Build("Luocha", eidolon=1), Build("Bronya")], start_sp=5)
    k = luo.kit
    atk_pct = bro.stat(S.ATK_PCT)
    k.skill(e)
    assert k.flowers == 1 and not luo.has_mod("Cycle of Life")
    k.skill(e)
    assert luo.has_mod("Cycle of Life") and k.flowers == 0
    assert bro.stat(S.ATK_PCT) - atk_pct == pytest.approx(k.ep(1, 0))  # E1 while the Zone is active
    b.remove_named(luo, "Cycle of Life")
    assert bro.stat(S.ATK_PCT) == pytest.approx(atk_pct)
    k._deploy_zone()
    bro.hp = 1.0
    bro.kit.basic(e)
    heal = (k.p("talent", 1) * luo.atk + k.p("talent", 3)) * (1 + luo.stat(S.HEAL_PCT))
    assert bro.hp == pytest.approx(1.0 + heal)


def test_luocha_auto_skill_on_low_hp():
    b, (luo, bro), (e,) = _battle([Build("Luocha"), Build("Bronya")], start_sp=0)
    b.lose_hp(bro, bro.max_hp * 0.6, e)
    b.process_queue()
    assert luo.kit.flowers == 1 and b.sp == 0  # triggered Skill costs no SP
    assert luo.kit.auto_cd == int(luo.kit.p("skill", 3))


# ----------------------------------------------------------------- Sushang
def test_sushang_sword_stance_on_broken_enemy():
    b, (su,), (e,) = _battle([Build("Sushang")])
    k = su.kit
    e.broken = True  # Sword Stance is guaranteed against Weakness Broken enemies
    k.skill(e)
    stance = [r for r in b.records if r.label == "Sword Stance"]
    assert len(stance) == 1 and k.riposte == 1
    su.energy = su.max_energy
    gauge = su.gauge
    k.use_ult()
    assert su.gauge == 0.0 and gauge > 0  # "immediately takes action"
    hits = _hits(b)
    k.skill(e)
    stance_hits = [h for h in hits if h.label == "Sword Stance"]
    assert len(stance_hits) == 1 + 2  # 2 extra chances during the Ultimate buff
    base = k.p("skill", 1) * su.atk
    assert stance_hits[0].base == pytest.approx(base)
    assert stance_hits[1].base == pytest.approx(base * k.p("ult", 2))
    assert stance_hits[0].extra[S.DMG_PCT] == pytest.approx(1 * k.tp(2, 0))  # A4 Riposte stacks


# ------------------------------------------------------------------ Yukong
def test_yukong_bowstrings_team_buffs():
    b, (yk, bro), (e,) = _battle([Build("Yukong"), Build("Bronya")])
    k = yk.kit
    base_atk = bro.stat(S.ATK_PCT)
    k.skill(e)
    rb = yk.get_mod("Roaring Bowstrings")
    assert rb.stacks == int(k.p("skill", 0))
    assert bro.stat(S.ATK_PCT) - base_atk == pytest.approx(k.p("skill", 1))
    cr = bro.stat(S.CRIT_RATE)
    yk.energy = yk.max_energy
    k.use_ult()
    assert bro.stat(S.CRIT_RATE) - cr == pytest.approx(k.p("ult", 1))
    b.events.emit(E.TURN_END, entity=bro, extra=False)
    b.events.emit(E.TURN_END, entity=bro, extra=False)
    assert not yk.has_mod("Roaring Bowstrings") and bro.stat(S.CRIT_RATE) == pytest.approx(cr)
    assert bro.stat(f"{S.DMG_PCT}:Imaginary") == pytest.approx(k.tp(2, 0))  # A4 Bowmaster


def test_yukong_talent_basic_every_other_turn():
    b, (yk,), (e,) = _battle([Build("Yukong", options={"rotation": "basic"})])
    k = yk.kit
    hits = _hits(b)
    bases = []
    for _ in range(3):
        hits.clear()
        b.take_turn(yk)
        bases.append(_main_base(hits))
    big = (k.p("basic", 0) + k.p("talent", 0)) * yk.atk
    assert bases == pytest.approx([big, k.p("basic", 0) * yk.atk, big])


# ----------------------------------------------------------------- Yanqing
def test_yanqing_soulsteel_sync_lost_on_damage():
    b, (yq,), (e,) = _battle([Build("Yanqing")])
    k = yq.kit
    cr, cd = yq.stat(S.CRIT_RATE), yq.stat(S.CRIT_DMG)
    k.skill(e)
    assert yq.stat(S.CRIT_RATE) - cr == pytest.approx(k.p("talent", 0))
    assert yq.stat(S.CRIT_DMG) - cd == pytest.approx(k.p("talent", 1))
    yq.energy = yq.max_energy
    k.use_ult()  # Soulsteel Sync active -> extra CRIT DMG
    ult = yq.get_mod("Amidst the Raining Bliss")
    assert ult.value(S.CRIT_DMG) == pytest.approx(k.p("ult", 1))
    b.enemy_basic_attack(e)
    assert not yq.has_mod("Soulsteel Sync")
