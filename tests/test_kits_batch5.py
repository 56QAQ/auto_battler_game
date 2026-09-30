"""Targeted checks for batch-5 kits: Jiaoqiu, Feixiao, Yunli, Lingsha, Moze, March 7th (The Hunt),
Fugue, The Dahlia."""

import pytest

from hsrsim import events as E
from hsrsim import formulas as F
from hsrsim import stats as S
from hsrsim.battle import Battle, BattleConfig
from hsrsim.build import Build, make_character
from hsrsim.entities import Enemy
from hsrsim.enums import ActionKind, DmgTag, Element

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


def _dummies(n, **kw):
    kw.setdefault("hp", 1e12)
    kw.setdefault("toughness", 1e6)
    kw.setdefault("effect_res", 0.0)
    return [Enemy(f"Dummy {i}", **kw) for i in range(n)]


# ------------------------------------------------------------------- Jiaoqiu
def test_jiaoqiu_ashen_roast_stacks_vulnerability_and_ult_zone():
    b, (jq, _), (a, m, c) = _battle([Build("1218"), generic_build("Seele")], _dummies(3))
    kit = jq.kit
    kit.skill(m)
    # primary: 1 stack from the Skill + 1 from the Talent; adjacent targets: 1 Talent stack
    assert kit.roast(m) == 2 and kit.roast(a) == 1 and kit.roast(c) == 1
    # ability script order: the Talent stack lands on every target before the DMG, the Skill's own stack after it
    hits = {r.target: r for r in _recs(b, "Scorch Onslaught")}
    one_stack = F.vuln_multiplier(kit.p("talent", 1))
    assert {t: hits[t].parts.vuln_mult for t in (a.name, m.name, c.name)} == pytest.approx(
        {a.name: one_stack, m.name: one_stack, c.name: one_stack}
    )
    assert m.stat(S.VULN) == pytest.approx(kit.p("talent", 1) + kit.p("talent", 2))
    assert m.has_tag("burn")  # Ashen Roast counts as Burn
    jq.energy = jq.max_energy
    jq.kit.use_ult()
    # stacks set to the highest on the field (2), then +1 Talent stack on every enemy hit
    assert [kit.roast(e) for e in (a, m, c)] == [3, 3, 3]
    assert m.stat(f"{S.VULN}:{DmgTag.ULT}") == pytest.approx(kit.p("ult", 2))
    # the Ashen Roast DoT at the enemy's turn start: 180% ATK Fire DoT (cannot CRIT)
    vuln = m.stat(S.VULN)
    before = len(_recs(b, "Ashen Roast"))
    b.take_turn(m)
    dots = _recs(b, "Ashen Roast")
    assert len(dots) == before + 1
    boost = 1 + jq.stat_q(S.DMG_PCT, ("Fire", DmgTag.DOT, "burn", "ashen_roast"))
    expected = (
        kit.p("talent", 5)
        * jq.atk
        * boost
        * F.def_multiplier(80, F.enemy_base_def(95))
        * F.res_multiplier(0.2)
        * F.vuln_multiplier(vuln)
        * F.NOT_BROKEN_MULT
    )
    assert dots[-1].amount == pytest.approx(expected)


# ------------------------------------------------------------------- Feixiao
def test_feixiao_follow_up_once_per_turn_and_ultimate_hits():
    b, (fx, seele), (e,) = _battle([Build("1220", traces=False), generic_build("Seele")])
    kit = fx.kit
    assert fx.max_energy == 0  # Flying Aureus replaces Energy
    seele.kit.basic(e)
    b.process_queue()
    seele.kit.basic(e)
    b.process_queue()
    assert len(_recs(b, "Thunderhunt")) == 1  # once per turn
    assert kit.aureus == 1  # 3 ally attacks (2 Seele + 1 follow-up) -> 1 point, tally 1
    kit.aureus = int(kit.p("talent", 2))
    kit.use_ult()
    subs = _recs(b, "Waraxe Skyward")  # the target is not Weakness Broken
    assert len(subs) == int(kit.p("ult", 2)) and len(_recs(b, "Terrasplit")) == 1
    assert kit.aureus == 0


# --------------------------------------------------------------------- Yunli
def test_yunli_parry_turns_enemy_attack_into_intuit_cull():
    b, (yl, _), (e,) = _battle([Build("1221"), generic_build("Seele")], start_energy=0.0)
    kit = yl.kit
    yl.energy = kit.p("ult", 7)  # the Ultimate costs 120 of her 240 Energy
    kit.use_ult()
    assert yl.energy == pytest.approx(kit.sk("ult")["energy"] * (1 + yl.stat(S.ERR)))
    assert kit.in_parry
    b.enemy_basic_attack(e)  # Taunt: the enemy must target Yunli
    b.process_queue()
    assert not kit.in_parry
    cull = _recs(b, "Intuit: Cull")
    # blast part split into 8 hits (no adjacent enemies) + 6 random bounces, counted as Ultimate DMG
    assert len(cull) == 8 + int(kit.p("ult", 3))
    assert all(DmgTag.ULT in r.tags for r in cull)


def test_yunli_counter_without_parry():
    b, (yl, _), (e,) = _battle([Build("1221"), generic_build("Seele")], start_energy=0.0)
    yl.base[S.AGGRO] = 1e9
    b.enemy_basic_attack(e)
    b.process_queue()
    counter = _recs(b, "Counter (Flashforge)")
    assert len(counter) == 1 and DmgTag.FUA in counter[0].tags


def test_yunli_ult_waits_until_an_enemy_acts_next():
    b, (yl, seele), (e,) = _battle([Build("1221"), generic_build("Seele")], start_energy=0.0)
    kit = yl.kit
    yl.energy = kit.p("ult", 7)
    assert kit.ult_ready()
    b.set_av(yl, 30.0)
    b.set_av(seele, 10.0)
    b.set_av(e, 20.0)
    assert not kit.want_ult()  # Seele acts next: Parry would end on her turn ("Intuit: Slash")
    b.set_av(e, 5.0)
    assert kit.want_ult()
    asap = make_character(Build("1221", options={"ult_timing": "asap"}))
    b2 = Battle([asap, make_character(generic_build("Seele"))], [_dummies(1)], BattleConfig(start_energy=0.0))
    b2.start()
    asap.energy = asap.kit.p("ult", 7)
    b2.set_av(b2.enemies[0], 500.0)  # an ally acts next
    assert asap.kit.ult_ready() and asap.kit.want_ult()


# ------------------------------------------------------------------- Lingsha
def test_lingsha_skill_summons_fuyuan_with_action_count():
    b, (ls, _), (e,) = _battle([Build("1222"), generic_build("Seele")])
    kit = ls.kit
    kit.skill(e)
    fy = kit.fuyuan
    assert fy is not None and fy.alive and fy.spd == pytest.approx(kit.p("talent", 0))
    assert kit.count == int(kit.p("talent", 6))
    assert fy.gauge == pytest.approx(F.AV_BASE * (1 - kit.p("skill", 3)))
    kit.skill(e)
    assert kit.count == int(kit.p("talent", 4))  # capped at 5
    b.take_turn(fy)
    assert kit.count == int(kit.p("talent", 4)) - 1
    assert len(_recs(b, "Fuyuan")) == 2  # AoE hit + the extra single-target hit on one enemy


# ---------------------------------------------------------------------- Moze
def test_moze_departed_charge_and_follow_up():
    b, (mz, seele), (e,) = _battle([Build("1223", traces=False), generic_build("Seele")])
    kit = mz.kit
    kit.skill(e)
    assert kit.departed and not mz.targetable and e.has_mod("Prey")
    assert kit.charge == int(kit.p("skill", 1)) - 1  # his own Skill hit on Prey consumed 1 Charge
    seele.kit.basic(e)
    seele.kit.basic(e)
    b.process_queue()
    fua = _recs(b, "Cascading Featherblade")
    extra = [r for r in fua if DmgTag.ADDITIONAL in r.tags]
    fuas = [r for r in fua if DmgTag.FUA in r.tags]
    assert len(fuas) == 1  # 3 Charge consumed -> 1 Talent Follow-Up ATK
    assert len(extra) == 4  # Moze Skill, 2 Seele attacks, the Follow-Up itself
    assert kit.charge == int(kit.p("skill", 1)) - 3


# ------------------------------------------------------------ March 7th (Hunt)
def test_march_7th_hunt_shifu_additional_dmg_and_enhanced_basic():
    no_ult = {"ult": False}
    b, (m7, seele), (e,) = _battle(
        [Build("1224", traces=False, options=no_ult), generic_build("Seele", options=no_ult)]
    )
    kit = m7.kit
    spd0 = seele.spd
    kit.skill(e)
    assert seele.spd == pytest.approx(spd0 + seele.raw(S.BASE_SPD) * kit.p("skill", 0))
    kit.basic(e)
    add = _recs(b, "Shifu (Additional DMG)")  # Seele is The Hunt -> Additional DMG of her type
    assert len(add) == 1 and add[0].element == Element.QUANTUM
    assert kit.charge == 1
    for _ in range(6):  # Shifu attacks -> Charge; at 7 March 7th immediately takes an extra action
        seele.kit.basic(e)
        b.process_queue()
    enhanced = _recs(b, "Brows Be Smitten, Heart Be Bitten")
    assert len(enhanced) >= 3 and kit.charge == 0


# --------------------------------------------------------------------- Fugue
def test_fugue_foxian_prayer_reduces_toughness_of_non_weak_enemies():
    enemy = Enemy("Dummy", hp=1e12, toughness=100, effect_res=0.0, weaknesses=[Element.FIRE])
    b, (fg, seele), (e,) = _battle([Build("1225"), generic_build("Seele")], [enemy])
    kit = fg.kit
    assert kit.luster[e.uid] == pytest.approx(kit.p("talent", 1) * e.max_toughness)
    kit.skill(e)
    assert seele.has_mod("Foxian Prayer")
    assert seele.get_mod("Foxian Prayer").value(S.BREAK_EFFECT) == pytest.approx(kit.p("skill", 1))
    t0 = e.toughness
    seele.kit.basic(e)  # Quantum attack on a Fire-only enemy: 50% of the Toughness Reduction
    assert t0 - e.toughness == pytest.approx(10 * kit.p("skill", 5))
    assert e.has_mod("Virtue Beckons Bliss (DEF Reduction)")


# ---------------------------------------------------------------- The Dahlia
def test_dahlia_wilt_implants_weakness_and_a6_toughness():
    enemy = Enemy("Dummy", hp=1e12, toughness=300, effect_res=0.0, weaknesses=[])
    b, (dh, seele), (e,) = _battle([Build("1321"), generic_build("Seele")], [enemy])
    kit = dh.kit
    assert kit.partner is seele
    assert not e.is_weak_to(Element.FIRE)
    dh.energy = dh.max_energy
    kit.use_ult()
    wilt = e.get_mod("Wilt")
    assert wilt is not None and wilt.value(S.DEF_REDUCTION) == pytest.approx(kit.p("ult", 2))
    assert e.is_weak_to(Element.FIRE) and e.is_weak_to(Element.QUANTUM)  # both Dance Partners' types
    # 20 Toughness from the Ultimate + A6: 20 fixed Fire Toughness Reduction after the attack
    assert e.max_toughness - e.toughness == pytest.approx(kit.toughness("ult", 1) + kit.tp(3, 4))
    # the Dance Partner's attack triggers the follow-up (5 bounces)
    seele.kit.basic(e)
    b.process_queue()
    assert len(_recs(b, "Who's Afraid of Constance?")) == int(kit.p("talent", 1))


def test_dahlia_recasts_zone_only_when_it_expired():
    b, (dh, _), (e,) = _battle([Build("1321"), generic_build("Seele")], start_energy=0.0)
    kinds = []
    b.events.on(E.ACTION_START, lambda ev: ev.action.actor is dh and kinds.append(ev.action.kind))
    b.sp = b.max_sp
    for _ in range(4):
        b.take_turn(dh)  # the Zone lasts 3 turns and counts down at the start of her turns
    assert [k for k in kinds if k in (ActionKind.SKILL, ActionKind.BASIC)] == [
        ActionKind.SKILL,
        ActionKind.BASIC,
        ActionKind.BASIC,
        ActionKind.SKILL,
    ]
