"""
Procedural placeholder SFX (tiny sine bleeps).
If real .wav assets exist in assets/sfx/, they override the generated tones.
"""

from __future__ import annotations

import math
import pathlib

try:
    import numpy as np
except ModuleNotFoundError:  # numpy is optional for simple placeholder SFX
    np = None  # type: ignore[assignment]
import pygame.mixer as mx

from engine.game_state import get_game_state

mx.init(frequency=22050, size=-16, channels=1, buffer=256)
ROOT = pathlib.Path(__file__).parent.parent / "assets" / "sfx"
ROOT.mkdir(parents=True, exist_ok=True)

_CACHE: dict[str, mx.Sound] = {}


def _tone(freq: int, msec: int = 120, vol: float = 0.4) -> mx.Sound:
    """Generate a sine tone sound. Works without numpy."""
    length = int(22050 * msec / 1000)
    if np is not None:
        t = np.arange(length) / 22050
        wave = (np.sin(2 * math.pi * freq * t) * 32767 * vol).astype(np.int16)
        return mx.Sound(buffer=wave)

    # Fallback implementation without numpy
    samples = bytearray()
    for i in range(length):
        value = int(math.sin(2 * math.pi * freq * i / 22050) * 32767 * vol)
        samples += value.to_bytes(2, "little", signed=True)
    return mx.Sound(buffer=bytes(samples))


def get(name: str, fall_freq: int = 800) -> mx.Sound:
    if name in _CACHE:
        return _CACHE[name]
    file = ROOT / f"{name}.wav"
    if file.exists():
        snd = mx.Sound(str(file))
    else:
        snd = _tone(fall_freq)
    _CACHE[name] = snd
    return snd


# convenient façade
def play(name: str, vol: float | None = None):
    s = get(name)
    if vol is None:
        vol = get_game_state().volume
    s.set_volume(vol)
    s.play()