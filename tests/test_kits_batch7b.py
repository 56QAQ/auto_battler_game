"""Targeted checks for Hyacine, Robin • Summeretto, Hysilens, Cerydra and Dan Heng • Permansor Terrae."""

import pytest

from hsrsim import events as E
from hsrsim import stats as S
from hsrsim.battle import Battle, BattleConfig
from hsrsim.build import Build, make_character
from hsrsim.entities import Enemy
from hsrsim.enums import ActionKind, Element

from .helpers import generic_build


def _battle(builds, enemies=None, **cfg):
    chars = [make_character(b) for b in builds]
    enemies = enemies or [Enemy("Dummy", effect_res=0.0, hp=1e12)]
    battle = Battle(chars, [enemies], BattleConfig(**cfg))
    battle.start()
    return battle, chars


def _actions(battle):
    acts = []
    battle.events.on(E.ACTION_END, lambda ev: acts.append(ev.action))
    return acts


def _lv(kit, sid):
    rec = kit.sk(sid)
    return rec["params"][kit.level_of(rec) - 1]


# -------------------------------------------------------------------- Hyacine
def test_hyacine_little_ica_after_rain_and_tally_damage():
    b, (hy, bronya) = _battle([Build("Hyacine"), generic_build("Bronya")])
    kit = hy.kit
    e0 = hy.energy
    kit.skill(b.default_target())
    ica = kit.memosprite()
    assert ica is not None and ica.name == "Little Ica" and not ica.on_timeline
    assert ica.max_hp == pytest.approx(kit.p("talent", 0) * hy.max_hp)
    summon = _lv(kit, "1140905")  # 15 Energy + 30 on the first summon, plus the Skill's own 30
    assert hy.energy - e0 == pytest.approx((summon[0] + summon[1] + 30) * (1 + hy.stat(S.ERR)))
    assert kit.tally > 0  # the Skill's healing is tallied
    stacks = ica.get_mod("First Light Heals the World")
    assert stacks is not None and stacks.stacks == int(kit.p("talent", 4))
    # Ultimate: "After Rain" raises every ally's Max HP by #3% + #4
    hp_pct, hp_flat = bronya.stat(S.HP_PCT), bronya.stat(S.HP_FLAT)
    hy.energy = hy.max_energy
    kit.use_ult()
    assert bronya.stat(S.HP_PCT) - hp_pct == pytest.approx(kit.p("ult", 2))
    assert bronya.stat(S.HP_FLAT) - hp_flat == pytest.approx(kit.p("ult", 3))
    # while "After Rain" lasts, Little Ica takes an extra turn after each of Hyacine's abilities:
    # AoE DMG = #1% of the healing tally, then #2% of the tally is cleared
    kit.tally = 50_000.0
    acts = _actions(b)
    kit.basic(b.default_target())
    b.process_queue()
    memo = [a for a in acts if a.kind == ActionKind.MEMOSPRITE and a.actor is ica]
    assert len(memo) == 1
    lv = _lv(kit, "1140901")
    hit = memo[0].hits[0]
    assert hit.base == pytest.approx(lv[0] * 50_000.0 + 0.0)
    assert hit.element == Element.WIND
    tally_before_clear = 50_000.0 + sum(0 for _ in ())  # Basic ATK heals nobody at E0
    assert kit.tally == pytest.approx(tally_before_clear * (1 - lv[1]))


def test_hyacine_ica_talent_heals_allies_that_lost_hp():
    b, (hy, bronya) = _battle([Build("Hyacine"), generic_build("Bronya")])
    kit = hy.kit
    kit.skill(b.default_target())
    ica = kit.memosprite()
    b.lose_hp(bronya, 0.5 * bronya.max_hp, None)
    hp, ica_hp = bronya.hp, ica.hp
    b.events.emit(E.TURN_START, entity=bronya, extra=False)  # "at the start of any target's turn"
    lv = _lv(kit, "1140903")
    assert ica.hp == pytest.approx(ica_hp - lv[0] * ica.max_hp)
    bonus = 1 + hy.stat(S.HEAL_PCT) + kit.tp(1, 2)  # Gloomy Grin: target at <= 50% HP
    assert bronya.hp - hp == pytest.approx((lv[1] * hy.max_hp + lv[2]) * bonus)


# ----------------------------------------------------------- Robin • Summeretto
def test_robin_summeretto_songbirds_fever_and_deviated_chords():
    enemies = [Enemy(f"E{i}", effect_res=0.0, hp=1e12) for i in range(2)]
    b, (robin, seele) = _battle([Build("Robin • Summeretto"), Build("Seele")], enemies)
    kit = robin.kit
    kit.skill(b.default_target())
    band = kit.memosprite()
    assert band is not None and band.name == "Summer Songbirds" and kit.members == 1
    assert band.max_hp == pytest.approx(kit.p("talent", 0) * robin.max_hp)
    assert band.spd == pytest.approx(kit.p("talent", 1) * robin.spd)
    assert not band.on_timeline
    warble = _lv(kit, "1151203")
    assert enemies[0].stat(S.VULN) == pytest.approx(warble[2])  # Bessie alone: #3%
    # every ally attack: 1 Vibe; A2 Deviated Chords on the attacker (CRIT DMG unless its ATK beats Robin's)
    v0 = kit.vibes
    seele.kit.basic(enemies[0])
    assert kit.vibes == v0 + 1
    mod = seele.get_mod("Deviated Chords")
    assert mod is not None
    if seele.atk - mod.stats.get(S.ATK_FLAT, 0.0) > robin.atk:
        assert mod.stats[S.ATK_FLAT] == pytest.approx((kit.tp(1, 0) + kit.vibes * kit.tp(1, 1)) * robin.max_hp)
    else:
        assert mod.stats[S.CRIT_DMG] == pytest.approx(kit.tp(1, 2) + kit.vibes * kit.tp(1, 3))
    # Drummie at #6 Vibes, Paddie at #7 -> "Fever"
    kit.gain_vibes(int(kit.p("talent", 6)) - kit.vibes)
    assert kit.fever and kit.members == 3 and band.on_timeline
    assert enemies[0].stat(S.VULN) == pytest.approx(warble[4])
    assert seele.stat(S.DEF_IGNORE) == pytest.approx(kit.p("talent", 7) + kit.vibes * kit.p("talent", 8))
    dmg0 = robin.stat(S.DMG_PCT) - (warble[0] + kit.vibes * warble[1])
    assert band.stat(S.DMG_PCT) == pytest.approx(dmg0 + warble[0] + kit.vibes * warble[1])
    # Robin's own turns are skipped during Fever
    pre = b.events.emit(E.PRE_TURN, entity=robin, cancel=False)
    assert pre.data["cancel"]
    # Chirrup Quartet: #2% of the band's Max HP to all enemies
    acts = _actions(b)
    kit._band_turn(band, b)
    hits = acts[-1].hits
    assert len(hits) == 2 and all(h.mult == {"hp": pytest.approx(_lv(kit, "1151201")[1])} for h in hits)
    # the countdown drains max(#6, #10% of Vibes) until the band leaves
    v = kit.vibes
    kit._countdown_turn(kit.countdown, b)
    assert kit.vibes == max(0, v - max(int(warble[5]), int(warble[9] * v)))
    while kit.fever:
        kit._countdown_turn(kit.countdown, b)
    assert kit.memosprite() is None and kit.members == 0 and kit.vibes == 0


def test_robin_summeretto_ultimate_special_guest():
    b, (robin, seele) = _battle([Build("Robin • Summeretto"), Build("Seele")])
    kit = robin.kit
    seele.energy = 0.0
    seele.gauge = 10_000.0
    robin.energy = robin.max_energy
    kit.use_ult()
    assert seele.gauge == pytest.approx(10_000.0 * (1 - kit.p("ult", 0)))
    assert seele.energy == pytest.approx(kit.p("ult", 2) * seele.max_energy)
    assert seele.has_mod("Special Guest")
    v0 = kit.vibes
    seele.kit.basic(b.default_target())
    assert kit.vibes == v0 + 1 + int(kit.p("ult", 1))


# ------------------------------------------------------------------- Hysilens
def test_hysilens_zone_states_and_dot_echo():
    b, (hys, bronya) = _battle([Build("Hysilens"), generic_build("Bronya")])
    kit = hys.kit
    enemy = b.default_target()
    assert kit.zone_active()  # A2: Zone at the start of combat, +1 SP
    assert b.sp == b.cfg.start_sp + int(kit.tp(1, 1))
    assert enemy.stat(S.DEF_REDUCTION) == pytest.approx(kit.p("ult", 2))
    # Talent: an ally attack inflicts one of Wind Shear/Bleed/Burn/Shock
    bronya.kit.basic(enemy)
    states = [m for m in enemy.modifiers if m.key.startswith("Hysilens ")]
    assert len(states) == 1
    # each DoT instance taken inside the Zone echoes as a Physical DoT of #4% ATK
    n0 = sum(1 for r in b.records if r.label == "Maelstrom Rhapsody DoT")
    b.detonate(enemy, 1.0)
    echoes = [r for r in b.records if r.label == "Maelstrom Rhapsody DoT"]
    assert len(echoes) - n0 == 1
    assert echoes[-1].element == Element.PHYSICAL
    assert echoes[-1].parts.base == pytest.approx(kit.p("ult", 3) * hys.atk)


# -------------------------------------------------------------------- Cerydra
def test_cerydra_military_merit_peerage_and_coup_de_main():
    b, (cer, seele) = _battle([Build("Cerydra"), Build("Seele")], start_sp=5)
    kit = cer.kit
    atk0 = seele.atk
    kit.skill(None)
    assert kit.merit is seele and kit.charge == int(kit.p("skill", 1))
    assert seele.atk - atk0 == pytest.approx(kit.p("talent", 1) * cer.atk)
    kit.gain_charge(int(kit.p("skill", 3)))
    assert kit.peerage
    assert seele.stat(f"{S.CRIT_DMG}:skill") == pytest.approx(kit.p("skill", 0))
    # Coup de Main: the Peerage holder's Skill is used twice for one Skill's SP, then Peerage reverts
    acts = _actions(b)
    sp0 = b.sp
    seele.kit.skill(b.default_target())
    skills = [a for a in acts if a.kind == ActionKind.SKILL and a.actor is seele]
    assert len(skills) == 2
    assert b.sp == sp0 - 1
    assert not kit.peerage
    adds = [r for r in b.records if r.label == "Ave Imperator"]
    assert len(adds) == 2  # Additional DMG after each attack of the Military Merit holder


# ----------------------------------------------------- Dan Heng • Permansor Terrae
def test_dan_heng_pt_bondmate_souldragon_and_additional_dmg():
    b, (dh, seele) = _battle([Build("Dan Heng • Permansor Terrae"), Build("Seele")])
    kit = dh.kit
    kit.skill(None)
    assert kit.bondmate is seele
    dragon = kit.dragon
    assert dragon is not None and dragon.spd == pytest.approx(kit.p("talent", 4))
    shield = kit.p("skill", 0) * dh.atk + kit.p("skill", 1)
    assert b.shield_value(seele) == pytest.approx(shield * (1 + dh.stat(S.SHIELD_PCT)))
    # A2: Bondmate ATK + #1% of DHPT's ATK
    assert seele.stat(S.ATK_FLAT) >= kit.tp(1, 0) * dh.atk - 1e-6
    # enhanced Souldragon: Follow-up ATK + Additional DMG of the Bondmate's Type (#8% of the Bondmate's ATK)
    dh.energy = dh.max_energy
    kit.use_ult()
    assert kit.enhanced_left == int(kit.p("ult", 2))
    acts = _actions(b)
    kit._dragon_turn(dragon, b)
    assert acts[-1].kind == ActionKind.FUA
    add = [r for r in b.records if r.label == "Souldragon (Bondmate Additional DMG)"]
    assert len(add) == 1 and add[0].element == seele.element and add[0].owner == seele.name
    assert add[0].parts.base == pytest.approx(kit.p("ult", 7) * seele.atk)
    assert kit.enhanced_left == int(kit.p("ult", 2)) - 1
