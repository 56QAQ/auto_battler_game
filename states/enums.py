from enum import Enum, auto

class GamePhase(Enum):
    MAIN_MENU = auto() 
    PREPARATION = auto()
    COMBAT = auto()
    MAP_NAVIGATION = auto()
    GAME_OVER = auto()
    RUN_COMPLETE = auto() 
    EVENT_CHOICE = auto() 

class UnitLocation(Enum):
    BENCH = auto()
    BOARD = auto()
    SHOP = auto()
    INVENTORY = auto() # For items
    EQUIPPED = auto()  # For items