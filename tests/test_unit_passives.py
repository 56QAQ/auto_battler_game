import engine.classes as engine_classes
from data.enums import Color, DamageType, TriggerTarget, TriggerTiming
from engine.classes import Unit
from engine.game_state import GameState


BASIC_BASE_STATS = {
    "hp": 100,
    "ad": 10,
    "as": 1.0,
    "ap": 0,
    "armor": 0,
    "mr": 0,
    "range": 50,
}


def make_definition(*, passive=None, trigger=None):
    definition = {
        "rarity": "COMMON",
        "primary_color": Color.WHITE,
        "traits": [],
        "base_stats": BASIC_BASE_STATS.copy(),
        "passive": passive or {},
    }
    if trigger is not None:
        definition["trigger"] = trigger
    return definition


def test_on_any_death_passive_without_trigger_calls_resolver():
    passive_definition = {
        "timing_type": TriggerTiming.ON_ANY_DEATH,
        "target_type": TriggerTarget.SELF,
        "base_value_source": None,
        "base_value_multiplier": 0.0,
        "base_value_flat": 0,
    }
    passive_unit = Unit(
        "Passive Only", make_definition(passive=passive_definition), level=1
    )
    enemy_unit = Unit(
        "Target", make_definition(passive={}), level=1, is_enemy=True
    )

    state = GameState()
    state.player_combat_team = [passive_unit]
    state.enemy_combat_team = [enemy_unit]

    called = {}

    def fake_resolve_passive(unit, timing, game_state, event_target, event_data):
        called["unit"] = unit
        called["timing"] = timing
        called["event_target"] = event_target
        called["event_data"] = event_data

    original_resolve_passive = engine_classes.resolve_passive_func
    engine_classes.resolve_passive_func = fake_resolve_passive
    try:
        lethal_damage = enemy_unit.current_hp + 10
        enemy_unit.take_damage(
            lethal_damage, DamageType.TRUE, state, passive_unit
        )
    finally:
        engine_classes.resolve_passive_func = original_resolve_passive

    assert called
    assert called["unit"] is passive_unit
    assert called["timing"] is TriggerTiming.ON_ANY_DEATH
    assert called["event_target"] is passive_unit
    assert called["event_data"]["value"] == 0

