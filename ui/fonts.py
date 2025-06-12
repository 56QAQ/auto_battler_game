from __future__ import annotations
import pygame as pg
from ui.constants import FONT_NAME, FONT_SIZE, SMALL_FONT_SIZE, LARGE_FONT_SIZE, MENU_FONT_SIZE,SCALE, FONT_S, TINY_FONT_S
pg.font.init()
_default = pg.font.get_default_font()
def load(size:int, bold:bool=False) -> pg.font.Font:
    return pg.font.SysFont(_default, int(size*SCALE), bold=bold)
REG   = load(FONT_S)
REG_B = load(FONT_S, bold=True)
SMALL = load(TINY_FONT_S)
SMALL_B = load(TINY_FONT_S, bold=True)
def load_fonts():
     """Initializes and returns a dictionary of fonts."""
     if not pg.font.get_init():
          pg.font.init()
     try:
        return {
            "default": pg.font.Font(FONT_NAME, FONT_SIZE),
            "small": pg.font.Font(FONT_NAME, SMALL_FONT_SIZE),
            "large": pg.font.Font(FONT_NAME, LARGE_FONT_SIZE),
            "menu": pg.font.Font(FONT_NAME, MENU_FONT_SIZE),
        }
     except Exception as e:
         print(f"Error loading fonts: {e}")
         # Fallback to basic system font if necessary
         return {
             "default": pg.font.SysFont("Arial", FONT_SIZE),
             "small": pg.font.SysFont("Arial", SMALL_FONT_SIZE),
             "large": pg.font.SysFont("Arial", LARGE_FONT_SIZE),
             "menu": pg.font.SysFont("Arial", MENU_FONT_SIZE),
         }