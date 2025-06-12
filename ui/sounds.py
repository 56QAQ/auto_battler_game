"""
Procedural placeholder SFX (tiny sine bleeps).
If real .wav assets exist in assets/sfx/, they override the generated tones.
"""
from __future__ import annotations
import pygame.mixer as mx
import numpy as np
import pathlib, math

mx.init(frequency=22050, size=-16, channels=1, buffer=256)
ROOT = pathlib.Path(__file__).parent.parent/'assets'/'sfx'
ROOT.mkdir(parents=True, exist_ok=True)

_CACHE: dict[str, mx.Sound] = {}

def _tone(freq:int, msec:int=120, vol:float=.4) -> mx.Sound:
    length = int(22050*msec/1000)
    t = np.arange(length)/22050
    wave = (np.sin(2*math.pi*freq*t)*32767*vol).astype(np.int16)
    return mx.Sound(buffer=wave)

def get(name:str, fall_freq:int=800) -> mx.Sound:
    if name in _CACHE: return _CACHE[name]
    file = ROOT/f'{name}.wav'
    if file.exists(): snd = mx.Sound(str(file))
    else:             snd = _tone(fall_freq)
    _CACHE[name] = snd
    return snd

# convenient façade
def play(name:str, vol:float=.6):
    s = get(name)
    s.set_volume(vol)
    s.play()
