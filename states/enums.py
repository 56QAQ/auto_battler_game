from enum import Enum, auto


class GamePhase(Enum):
    MAIN_MENU = auto()
    PREPARATION = auto()
    DIFFICULTY_SELECT = auto()
    COMBAT = auto()
    MAP_NAVIGATION = auto()
    GAME_OVER = auto()
    RUN_COMPLETE = auto()
    THEME_SELECT = auto()
    EVENT_CHOICE = auto()
    SETTINGS = auto()


class UnitLocation(Enum):
    BENCH = auto()
    BOARD = auto()
    SHOP = auto()
    INVENTORY = auto()  # For items
    EQUIPPED = auto()  # For items