"""Character kit registry.

Each module in this package implements one or more characters and registers
them with :func:`register`. ``load_all()`` imports every module so the
registry is complete.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import TypeVar

from .base import Kit

KITS: dict[str, type[Kit]] = {}
K = TypeVar("K", bound=type[Kit])


def register(cls: K) -> K:
    KITS[cls.char_id] = cls
    return cls


def load_all() -> dict[str, type[Kit]]:
    for mod in pkgutil.iter_modules(__path__):
        if mod.name not in ("base",):
            importlib.import_module(f"{__name__}.{mod.name}")
    return KITS


def get_kit(char_id: str) -> type[Kit]:
    load_all()
    if char_id not in KITS:
        raise NotImplementedError(f"character {char_id} has no kit implementation yet; implemented: {sorted(KITS)}")
    return KITS[char_id]
