import pygame as pg

from data.constants import MAX_ITEMS_EQUIPPED  # noqa: F401 - re-exported
from data.constants import (ATTACK_ANIM_DURATION, CAST_ANIM_DURATION,
                            DEATH_ANIM_DURATION, HEAL_ANIM_DURATION,
                            HIT_ANIM_DURATION)

# Display
SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080
FPS = 60

BASE_WIDTH = 1920
BASE_HEIGHT = 1080
BASE_SLOT_SIZE = 120
_ITEM_RATIO = 0.6
# Use a serif font for a more "clockwork" feel if available
FONT_NAME = "./assets/fonts/DejaVuSerif.ttf"
FONT_SIZE = 18
SMALL_FONT_SIZE = 14
LARGE_FONT_SIZE = 24
MENU_FONT_SIZE = 48

# Asset directories
ASSET_DIR = "assets"
UNIT_IMAGE_DIR = f"{ASSET_DIR}/units"
ITEM_IMAGE_DIR = f"{ASSET_DIR}/items"
ICON_IMAGE_DIR = f"{ASSET_DIR}/icons"
ARTIFACT_IMAGE_DIR = f"{ASSET_DIR}/artifact"
PLACEHOLDER_IMAGE = f"{ASSET_DIR}/placeholder.png"
BUTTON_IMAGE = f"{ASSET_DIR}/ui/button.png"
PANEL_IMAGE = f"{ASSET_DIR}/ui/panel.png"
SHOP_BG_IMAGE = f"{ASSET_DIR}/backgrounds/shop_bg.png"
MAP_BG_IMAGE = f"{ASSET_DIR}/backgrounds/map_bg.png"
COMBAT_BG_IMAGE = f"{ASSET_DIR}/backgrounds/combat_bg.png"

def _scale_sizes() -> None:
    """Compute SLOT_SIZE and dependent constants from the current resolution."""
    global SLOT_SIZE, ITEM_SLOT_SIZE, COMBAT_UNIT_RADIUS
    factor = SCREEN_HEIGHT / BASE_HEIGHT
    SLOT_SIZE = int(BASE_SLOT_SIZE * factor)
    ITEM_SLOT_SIZE = int(SLOT_SIZE * _ITEM_RATIO)
    COMBAT_UNIT_RADIUS = SLOT_SIZE // 2

# Colors
WHITE = (240, 240, 235)
BLACK = (12, 12, 12)
GRAY = (140, 140, 140)
LIGHT_GRAY = (200, 200, 200)
DARK_GRAY = (32, 32, 32)
GOLD = (205, 168, 72)
RED = (176, 60, 60)
GREEN = (80, 170, 140)
BLUE = (70, 120, 180)
CYAN = (0, 170, 170)
PURPLE = (170, 0, 170)
MAGENTA = (170, 80, 170)
YELLOW = (200, 200, 60)
PANEL_BG = (40, 44, 52)
BUTTON_BG = (70, 70, 90)
BUTTON_HOVER = (90, 120, 130)
BUTTON_ACTIVE = (110, 150, 160)
BUTTON_DISABLED = (60, 60, 60)
HIGHLIGHT_COLOR = (0, 220, 220)  # Renamed from HIGHLIGHT
INACTIVE_SYNERGY = (100, 100, 100)
ACTIVE_SYNERGY_BRONZE = (180, 110, 0)
ACTIVE_SYNERGY_SILVER = (192, 192, 192)
ACTIVE_SYNERGY_GOLD = GOLD
HEALTH_BAR_BG = (50, 50, 50)
HEALTH_BAR_COLOR = (0, 220, 0)
ENEMY_COLOR = (220, 50, 50)
ALLY_COLOR = BLUE  # For engine mapping
MAP_NODE_BG = (60, 60, 80)
MAP_NODE_CURRENT = (100, 200, 100)
MAP_NODE_VISITED = (40, 40, 50)
MAP_PATH = (80, 80, 100)
ITEM_COLOR = (100, 50, 150)
DAMAGE_PHYSICAL_COLOR = (255, 100, 0)
DAMAGE_CRIT_COLOR = (255, 215, 0)
DAMAGE_MAGIC_COLOR = (100, 100, 255)
DAMAGE_TRUE_COLOR = WHITE
HEAL_COLOR = GREEN
BUFF_COLOR = CYAN
OVERTIME_COLOR = (255, 0, 255)
HIT_FLASH_COLOR = WHITE
HEAL_FLASH_COLOR = (100, 255, 100)
CAST_FLASH_COLOR = (100, 200, 255)
DEATH_COLOR = (80, 20, 20)
PROJECTILE_BASIC_COLOR = YELLOW
PROJECTILE_MAGIC_COLOR = MAGENTA
SLASH_COLOR = WHITE
HIT_SPARK_COLOR = (255, 200, 0)

RARITY_COLORS = {
    "COMMON": GRAY,
    "UNCOMMON": GREEN,
    "RARE": BLUE,
    "EPIC": MAGENTA,
    "LEGENDARY": GOLD,
}

# Map color keys from engine to actual colors
KEY_TO_COLOR = {
    "WHITE": WHITE,
    "RED": RED,
    "GREEN": GREEN,
    "BLUE": BLUE,
    "YELLOW": YELLOW,
    "CYAN": CYAN,
    "MAGENTA": MAGENTA,
    "BLACK": BLACK,
    "ALLY_COLOR": ALLY_COLOR,
    "ENEMY_COLOR": ENEMY_COLOR,
    "DAMAGE_PHYSICAL_COLOR": DAMAGE_PHYSICAL_COLOR,
    "DAMAGE_CRIT_COLOR": DAMAGE_CRIT_COLOR,
    "DAMAGE_MAGIC_COLOR": DAMAGE_MAGIC_COLOR,
    "DAMAGE_TRUE_COLOR": DAMAGE_TRUE_COLOR,
    "HEAL_COLOR": HEAL_COLOR,
    "BUFF_COLOR": BUFF_COLOR,
    "OVERTIME_COLOR": OVERTIME_COLOR,
    "HIT_FLASH_COLOR": HIT_FLASH_COLOR,
    "HEAL_FLASH_COLOR": HEAL_FLASH_COLOR,
    "CAST_FLASH_COLOR": CAST_FLASH_COLOR,
    "DEATH_COLOR": DEATH_COLOR,
    "PROJECTILE_BASIC_COLOR": PROJECTILE_BASIC_COLOR,
    "PROJECTILE_MAGIC_COLOR": PROJECTILE_MAGIC_COLOR,
    "SLASH_COLOR": SLASH_COLOR,
    "HIT_SPARK_COLOR": HIT_SPARK_COLOR,
}
STATUS_ICON_SIZE = 14
STATUS_ICON_SPACING = 2
STATUS_ICON_KEYS = {
    "DOT": "status_dot",
    "HOT": "status_hot",
    "STUN": "status_stun",
    "SHIELD": "status_shield",
    "BUFF": "status_buff",
    "DEBUFF": "status_debuff",
}
# Layout
BENCH_SLOTS = 8
BENCH_Y = SCREEN_HEIGHT - 60
BENCH_X_START = 250
SLOT_SIZE = BASE_SLOT_SIZE
SLOT_MARGIN = 10

BOARD_ROWS = 3
BOARD_COLS = 6
BOARD_X_START = (SCREEN_WIDTH - (BOARD_COLS * (SLOT_SIZE + SLOT_MARGIN))) // 2 + 50
BOARD_Y_START = SCREEN_HEIGHT - 280 - (BOARD_ROWS * (SLOT_SIZE + SLOT_MARGIN))
PREVIEW_Y_START = BOARD_Y_START + BOARD_ROWS * (SLOT_SIZE + SLOT_MARGIN)
BOARD_Y_START = SCREEN_HEIGHT - 280

SHOP_SLOTS = 5
SHOP_Y = 100
SHOP_X_START = 250

INFO_PANEL_X = 10
INFO_PANEL_Y = 10
SYNERGY_PANEL_X = 10
SYNERGY_PANEL_Y = 300
SYNERGY_LINE_HEIGHT = 40

MAX_ITEMS_INVENTORY = 6
INVENTORY_X_START = SHOP_X_START
INVENTORY_Y = BOARD_Y_START - SLOT_SIZE + 40
ITEM_SLOT_SIZE = int(SLOT_SIZE * _ITEM_RATIO)
RELIC_ICON_SIZE = 24

BUTTON_HEIGHT = 40

COMBAT_ARENA_X = 220
COMBAT_ARENA_Y = 100
COMBAT_ARENA_WIDTH = SCREEN_WIDTH - 400
COMBAT_ARENA_HEIGHT = SCREEN_HEIGHT - 200
COMBAT_UNIT_RADIUS = SLOT_SIZE // 2
ARENA_MIN_X = COMBAT_ARENA_X + COMBAT_UNIT_RADIUS
ARENA_MAX_X = COMBAT_ARENA_X + COMBAT_ARENA_WIDTH - COMBAT_UNIT_RADIUS
ARENA_MIN_Y = COMBAT_ARENA_Y + COMBAT_UNIT_RADIUS
ARENA_MAX_Y = COMBAT_ARENA_Y + COMBAT_ARENA_HEIGHT - COMBAT_UNIT_RADIUS
DESIGN_HEIGHT = 900  # logical reference canvas (16:9)
SCALE = round(max(0.75, SCREEN_HEIGHT / DESIGN_HEIGHT) * 4) / 4
MAP_WIDTH = int(SCREEN_WIDTH * 0.9)
MAP_HEIGHT = int(SCREEN_HEIGHT * 0.8)
MAP_X_START = (SCREEN_WIDTH - MAP_WIDTH) // 2
MAP_Y_START = (SCREEN_HEIGHT - MAP_HEIGHT) // 2
MAP_NODE_RADIUS = int(15 * SCALE)

EVENT_CHOICE_WIDTH = 500
EVENT_CHOICE_HEIGHT = 300
EVENT_CHOICE_RECT = pg.Rect(
    SCREEN_WIDTH // 2 - EVENT_CHOICE_WIDTH // 2,
    SCREEN_HEIGHT // 2 - EVENT_CHOICE_HEIGHT // 2,
    EVENT_CHOICE_WIDTH,
    EVENT_CHOICE_HEIGHT,
)
EVENT_BUTTON_WIDTH = 400
EVENT_BUTTON_HEIGHT = 60
# ------------------------------------------------------------------ #
#  Adaptive scaling
# ------------------------------------------------------------------ #

_pg_info = pg.display.Info()  # valid only *after* pg.init()!
SCREEN_HEIGHT = _pg_info.current_h if _pg_info.current_h else BASE_HEIGHT
# 1 × on a 900‑px tall screen, 2 × on 1800 px, etc. (rounded .25 steps)
SCALE = round(max(0.75, SCREEN_HEIGHT / DESIGN_HEIGHT) * 4) / 4
_scale_sizes()

def update_resolution(width: int, height: int) -> None:
    """Update layout constants to match a new resolution."""
    global SCREEN_WIDTH, SCREEN_HEIGHT, SCALE
    global BENCH_Y, BOARD_X_START, BOARD_Y_START, PREVIEW_Y_START, INVENTORY_Y
    global COMBAT_ARENA_WIDTH, COMBAT_ARENA_HEIGHT
    global ARENA_MAX_X, ARENA_MAX_Y
    global MAP_WIDTH, MAP_HEIGHT, MAP_X_START, MAP_Y_START, MAP_NODE_RADIUS
    global EVENT_CHOICE_RECT

    SCREEN_WIDTH = width
    SCREEN_HEIGHT = height
    SCALE = round(max(0.75, SCREEN_HEIGHT / DESIGN_HEIGHT) * 4) / 4

    BENCH_Y = SCREEN_HEIGHT - 60
    BOARD_X_START = (SCREEN_WIDTH - (BOARD_COLS * (SLOT_SIZE + SLOT_MARGIN))) // 2 + 50
    BOARD_Y_START = SCREEN_HEIGHT - 280 - (BOARD_ROWS * (SLOT_SIZE + SLOT_MARGIN))
    PREVIEW_Y_START = BOARD_Y_START + BOARD_ROWS * (SLOT_SIZE + SLOT_MARGIN)
    INVENTORY_Y = BOARD_Y_START - SLOT_SIZE + 40

    COMBAT_ARENA_WIDTH = SCREEN_WIDTH - 400
    COMBAT_ARENA_HEIGHT = SCREEN_HEIGHT - 200
    ARENA_MAX_X = COMBAT_ARENA_X + COMBAT_ARENA_WIDTH - COMBAT_UNIT_RADIUS
    ARENA_MAX_Y = COMBAT_ARENA_Y + COMBAT_ARENA_HEIGHT - COMBAT_UNIT_RADIUS

    MAP_WIDTH = int(SCREEN_WIDTH * 0.9)
    MAP_HEIGHT = int(SCREEN_HEIGHT * 0.8)
    MAP_X_START = (SCREEN_WIDTH - MAP_WIDTH) // 2
    MAP_Y_START = (SCREEN_HEIGHT - MAP_HEIGHT) // 2
    MAP_NODE_RADIUS = int(15 * SCALE)

    EVENT_CHOICE_RECT.update(
        SCREEN_WIDTH // 2 - EVENT_CHOICE_WIDTH // 2,
        SCREEN_HEIGHT // 2 - EVENT_CHOICE_HEIGHT // 2,
        EVENT_CHOICE_WIDTH,
        EVENT_CHOICE_HEIGHT,
    )


# ------------------------------------------------------------------ #
#  Colours
# ------------------------------------------------------------------ #
def _c(r, g, b):
    """Convenience for creating colour tuples."""
    return pg.Color(r, g, b)


# Muted steampunk inspired palette
WHITE, BLACK = _c(240, 240, 235), _c(12, 12, 12)
GREY, DGREY = _c(140, 140, 140), _c(32, 32, 32)
# Brass/gold accent and a warm red
GOLD, RED = _c(205, 168, 72), _c(176, 60, 60)
GREEN, BLUE = _c(80, 170, 140), _c(70, 120, 180)
# Default backgrounds
BG = _c(24, 26, 30)
PANEL_BG = _c(40, 44, 52)
GRID_LINE = _c(80, 85, 95)

RARITY_COL = [GREY, GREEN, BLUE, GOLD, RED]  # 0‑4 stars

# ------------------------------------------------------------------ #
#  Layout (logical units)
# ------------------------------------------------------------------ #
BAR_H = 14
STATUS_W = 280
SHOP_H = 160
BENCH_H = 110
SYNERGY_W = 240
PADDING = 8
ICON = 24
FONT_S = 18
TINY_FONT_S = 14
# Animation Durations (imported from data for lerping)
ANIM_DURATIONS = {
    "ATTACKING": ATTACK_ANIM_DURATION,
    "HIT": HIT_ANIM_DURATION,
    "HEALED": HEAL_ANIM_DURATION,
    "CASTING": CAST_ANIM_DURATION,
    "DYING": DEATH_ANIM_DURATION,
}