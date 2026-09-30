"""Damage reports: totals per character / source / damage type / cycle."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .battle import Battle, DamageRecord


@dataclass
class Report:
    battle: Battle

    @property
    def records(self) -> list[DamageRecord]:
        return self.battle.records

    @property
    def av(self) -> float:
        return self.battle.time

    @property
    def total(self) -> float:
        return sum(r.amount for r in self.records)

    @property
    def effective_total(self) -> float:
        """Total minus overkill (damage beyond remaining HP)."""
        return sum(r.amount - r.overkill for r in self.records)

    @property
    def cycles(self) -> float:
        """Cycles elapsed, fractional (MoC counting: first cycle 150 AV, then 100)."""
        b = self.battle
        first, per = b.cfg.first_cycle_av, b.cfg.cycle_av
        t = b.cleared_at if b.cleared_at is not None else b.time
        return t / first if t <= first else 1.0 + (t - first) / per

    def by(self, attr: str) -> dict[str, float]:
        out: dict[str, float] = defaultdict(float)
        for r in self.records:
            out[str(getattr(r, attr))] += r.amount
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))

    def by_owner(self) -> dict[str, float]:
        return self.by("owner")

    def by_source(self) -> dict[str, float]:
        out: dict[str, float] = defaultdict(float)
        for r in self.records:
            out[f"{r.owner} | {r.label}"] += r.amount
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))

    def by_tag(self) -> dict[str, float]:
        out: dict[str, float] = defaultdict(float)
        for r in self.records:
            key = "+".join(sorted(t for t in r.tags if t in _MAIN_TAGS)) or "other"
            out[key] += r.amount
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))

    def by_cycle(self) -> dict[int, float]:
        out: dict[int, float] = defaultdict(float)
        for r in self.records:
            out[r.cycle + 1] += r.amount
        return dict(sorted(out.items()))

    def dpav(self) -> float:
        return self.total / self.av if self.av > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        b = self.battle
        return {
            "total": self.total,
            "effective_total": self.effective_total,
            "av": self.av,
            "cycles": self.cycles,
            "cleared": b.cleared_at is not None,
            "cleared_at_av": b.cleared_at,
            "dpav": self.dpav(),
            "by_character": self.by_owner(),
            "by_source": self.by_source(),
            "by_type": self.by_tag(),
            "by_cycle": self.by_cycle(),
            "turns": dict(b.turn_counts),
            "notes": {c.name: c.build_notes for c in b.team if c.build_notes},
        }

    def to_text(self, top: int = 25) -> str:
        b = self.battle
        lines = []
        state = f"cleared at {b.cleared_at:.1f} AV" if b.cleared_at is not None else f"stopped at {b.time:.1f} AV"
        lines.append(f"Total DMG {self.total:,.0f}  ({state}, {self.cycles:.2f} cycles, {self.dpav():,.0f} DMG/AV)")
        lines.append("")
        lines.append("By character:")
        tot = self.total or 1.0
        for k, v in self.by_owner().items():
            lines.append(f"  {k:<28} {v:>16,.0f}  {v / tot:6.1%}")
        lines.append("")
        lines.append("By damage type:")
        for k, v in self.by_tag().items():
            lines.append(f"  {k:<28} {v:>16,.0f}  {v / tot:6.1%}")
        lines.append("")
        lines.append(f"By source (top {top}):")
        for k, v in list(self.by_source().items())[:top]:
            lines.append(f"  {k:<48} {v:>16,.0f}  {v / tot:6.1%}")
        lines.append("")
        lines.append("Turns: " + ", ".join(f"{k} {v}" for k, v in b.turn_counts.items()))
        for c in b.team:
            for note in c.build_notes:
                lines.append(f"note [{c.name}]: {note}")
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.to_text()


_MAIN_TAGS = {
    "basic",
    "skill",
    "ult",
    "fua",
    "dot",
    "break",
    "super_break",
    "additional",
    "memosprite",
    "elation",
    "true",
}
