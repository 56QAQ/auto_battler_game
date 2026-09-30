"""Targeted checks of enhanced kits that have no batch test file (Blade, Jingliu)."""

import pytest

from hsrsim import events as E
from hsrsim import stats as S
from hsrsim.battle import Battle, BattleConfig
from hsrsim.build import Build, make_character
from hsrsim.entities import Enemy
from hsrsim.enums import Element
from hsrsim.kits.blade import FUA_SPLITS, BladeEnhanced
from hsrsim.kits.jingliu import ENH_ENTRY_BONUS, MOON_SPLITS, MOONLIGHT, JingliuEnhanced


def _battle(builds, n_enemies=1):
    chars = [make_character(b) for b in builds]
    enemies = [
        Enemy(f"Dummy {i}", hp=1e12, toughness=1e6, effect_res=0.0, weaknesses=list(Element)) for i in range(n_enemies)
    ]
    b = Battle(chars, [enemies], BattleConfig())
    b.start()
    return b, chars, enemies


def _hits(b):
    out = []
    b.events.on(E.AFTER_HIT, lambda ev: out.append(ev.hit))
    return out


def test_enhanced_blade_hp_scaling_and_persistent_tally():
    b, (blade, _), (e,) = _battle([Build("Blade", enhanced=True), Build("Bronya")])
    k = blade.kit
    assert isinstance(k, BladeEnhanced)
    mh = blade.max_hp
    hits = _hits(b)
    k.skill(e)  # Hellscape (30% HP) + Forest of Swords (10% HP)
    assert blade.stat(S.AGGRO_PCT) == pytest.approx(k.p("skill", 4))
    rec = k.sk(k.forest_id)
    lv = rec["params"][k.level_of(rec) - 1]
    forest = [h for h in hits if h.label == "Forest of Swords"]
    assert len(forest) == 2 and sum(h.base for h in forest) == pytest.approx(lv[1] * mh)  # HP only, no ATK
    assert k.tally == pytest.approx(0.4 * mh) and k.charge == 2
    # Ultimate: HP set to 50% (another 10% lost), then A2 keeps half of the tally
    blade.energy = blade.max_energy
    k.use_ult()
    ult = [h for h in hits if h.label == "Death Sentence" and h.primary]
    assert ult[0].base == pytest.approx(k.p("ult", 0) * mh + k.p("ult", 4) * 0.5 * mh)
    assert k.tally == pytest.approx(0.5 * mh * (1 - k.tp(1, 0)))
    # A4: Incoming Healing boost, and a share of the HP restored by healing feeds the tally
    before = k.tally
    restored = b.heal(blade, 0.1 * mh, blade)
    assert restored == pytest.approx(0.1 * mh * (1 + k.tp(2, 1)))
    assert k.tally == pytest.approx(before + k.tp(2, 0) * restored)
    # Talent follow-up: 3 AoE hits on Max HP; A6 Energy
    k.charge = k.max_charge() - 1
    energy = blade.energy
    k.add_charge()
    b.process_queue()
    fua = [h for h in hits if h.label == "Shuhu's Gift"]
    assert [h.ratio for h in fua] == FUA_SPLITS
    assert sum(h.base for h in fua) == pytest.approx(k.p("talent", 1) * blade.max_hp)
    assert blade.energy > energy and k.charge == 0


def test_enhanced_jingliu_moonlight_and_syzygy():
    b, (jl, bro, seele), (e,) = _battle([Build("Jingliu", enhanced=True), Build("Bronya"), Build("Seele")])
    k = jl.kit
    assert isinstance(k, JingliuEnhanced)
    cr0, cd0 = jl.stat(S.CRIT_RATE), jl.stat(S.CRIT_DMG)
    k.skill(e)
    assert not k.in_transmigration and k.syzygy == 1
    k.skill(e)  # 2 Syzygy -> Spectral Transmigration with 1 extra stack and a 100% action advance
    assert k.in_transmigration and k.syzygy == 2 + ENH_ENTRY_BONUS
    assert jl.stat(S.CRIT_RATE) == pytest.approx(cr0 + k.p("talent", 6))
    hits = _hits(b)
    sp, events = b.sp, k.hp_events
    hp_b, hp_s = bro.hp, seele.hp
    k.take_turn()  # Moon On Glacial River
    assert hp_b - bro.hp == pytest.approx(k.p("talent", 1) * bro.max_hp)
    assert hp_s - seele.hp == pytest.approx(k.p("talent", 1) * seele.max_hp)
    moon = jl.get_mod(MOONLIGHT)
    assert moon is not None and moon.stacks == 2  # one per teammate that consumed HP
    assert jl.stat(S.CRIT_DMG) == pytest.approx(cd0 + 2 * k.p("talent", 2))
    assert k.hp_events == events + 2
    rec = k.sk(f"{k.prefix}09")
    lv = rec["params"][k.level_of(rec) - 1]
    main = [h for h in hits if h.primary]
    assert [h.ratio for h in main] == MOON_SPLITS
    assert sum(h.base for h in main) == pytest.approx(lv[0] * jl.max_hp)
    assert b.sp == sp and k.syzygy == 2 + ENH_ENTRY_BONUS - 1
    # leaving the state (Syzygy 0) removes Moonlight
    k.syzygy = 1
    k.take_turn()
    assert not k.in_transmigration and jl.get_mod(MOONLIGHT) is None
