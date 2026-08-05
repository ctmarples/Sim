"""Monthly production / consumption / stock ledger for the resource tracker UI."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

from seasons import YEAR_DAYS

# 12 months per year; 112-day year → 9 days per month (4 leftover days stay in Win·3).
MONTHS_PER_YEAR = 12
DAYS_PER_MONTH = max(1, YEAR_DAYS // MONTHS_PER_YEAR)
HISTORY_MONTHS = 24

MONTH_SHORT: tuple[str, ...] = (
    "Spr1",
    "Spr2",
    "Spr3",
    "Sum1",
    "Sum2",
    "Sum3",
    "Aut1",
    "Aut2",
    "Aut3",
    "Win1",
    "Win2",
    "Win3",
)


@dataclass
class MonthBucket:
    produced: dict[str, int] = field(default_factory=dict)
    consumed: dict[str, int] = field(default_factory=dict)
    stock: dict[str, int] = field(default_factory=dict)

    def add_produced(self, key: str, amount: int) -> None:
        if amount <= 0:
            return
        self.produced[key] = int(self.produced.get(key, 0)) + int(amount)

    def add_consumed(self, key: str, amount: int) -> None:
        if amount <= 0:
            return
        self.consumed[key] = int(self.consumed.get(key, 0)) + int(amount)

    def set_stock(self, amounts: dict[str, int]) -> None:
        self.stock = {str(k): int(v) for k, v in amounts.items() if int(v) > 0}

    def to_dict(self) -> dict[str, Any]:
        return {
            "produced": {k: int(v) for k, v in self.produced.items() if v},
            "consumed": {k: int(v) for k, v in self.consumed.items() if v},
            "stock": {k: int(v) for k, v in self.stock.items() if v},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> MonthBucket:
        if not data:
            return cls()
        produced = {str(k): int(v) for k, v in (data.get("produced") or {}).items()}
        consumed = {str(k): int(v) for k, v in (data.get("consumed") or {}).items()}
        stock = {str(k): int(v) for k, v in (data.get("stock") or {}).items()}
        return cls(produced=produced, consumed=consumed, stock=stock)


def month_label(absolute_month: int) -> str:
    """Short label for an absolute month index (0 = first month of year 0)."""
    m = int(absolute_month) % MONTHS_PER_YEAR
    year = int(absolute_month) // MONTHS_PER_YEAR
    base = MONTH_SHORT[m]
    if year <= 0:
        return base
    return f"Y{year} {base}"


class ResourceHistory:
    """Rolling 24-month window of produced / consumed / stock per resource key."""

    def __init__(self) -> None:
        self.total_days: int = 0
        self.months: deque[MonthBucket] = deque(maxlen=HISTORY_MONTHS)
        self.current: MonthBucket = MonthBucket()

    def reset(self) -> None:
        self.total_days = 0
        self.months.clear()
        self.current = MonthBucket()

    @property
    def current_month_index(self) -> int:
        return self.total_days // DAYS_PER_MONTH

    def advance_day(self) -> None:
        """Roll the calendar one day; close the month bucket when the month changes."""
        prev = self.current_month_index
        self.total_days += 1
        if self.current_month_index != prev:
            self.months.append(self.current)
            self.current = MonthBucket()

    def record_produced(self, key: str, amount: int = 1) -> None:
        self.current.add_produced(key, amount)

    def record_consumed(self, key: str, amount: int = 1) -> None:
        self.current.add_consumed(key, amount)

    def record_stock(self, amounts: dict[str, int]) -> None:
        """Snapshot village stock into the in-progress month (call before advance_day)."""
        self.current.set_stock(amounts)

    def _window_buckets(self) -> list[tuple[int, MonthBucket]]:
        """Up to HISTORY_MONTHS closed months plus the in-progress month."""
        cur_idx = self.current_month_index
        closed = list(self.months)
        start_idx = cur_idx - len(closed)
        out: list[tuple[int, MonthBucket]] = [
            (start_idx + i, bucket) for i, bucket in enumerate(closed)
        ]
        out.append((cur_idx, self.current))
        if len(out) > HISTORY_MONTHS:
            out = out[-HISTORY_MONTHS:]
        return out

    def series(self, key: str) -> tuple[list[str], list[int], list[int], list[int]]:
        """Labels, produced[], consumed[], stock[] for the chart window (padded to 24)."""
        window = self._window_buckets()
        labels = [month_label(idx) for idx, _ in window]
        produced = [int(b.produced.get(key, 0)) for _, b in window]
        consumed = [int(b.consumed.get(key, 0)) for _, b in window]
        stock = [int(b.stock.get(key, 0)) for _, b in window]
        pad = HISTORY_MONTHS - len(labels)
        if pad > 0:
            first = window[0][0] if window else self.current_month_index
            labels = [month_label(first - pad + i) for i in range(pad)] + labels
            produced = [0] * pad + produced
            consumed = [0] * pad + consumed
            stock = [0] * pad + stock
        return labels, produced, consumed, stock

    def totals(self, key: str) -> tuple[int, int]:
        _labels, produced, consumed, _stock = self.series(key)
        return sum(produced), sum(consumed)

    def keys_with_activity(self) -> set[str]:
        keys: set[str] = set()
        for _, bucket in self._window_buckets():
            keys.update(k for k, v in bucket.produced.items() if v)
            keys.update(k for k, v in bucket.consumed.items() if v)
            keys.update(k for k, v in bucket.stock.items() if v)
        return keys

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_days": int(self.total_days),
            "months": [b.to_dict() for b in self.months],
            "current": self.current.to_dict(),
        }

    def load_dict(self, data: dict[str, Any] | None) -> None:
        self.reset()
        if not data:
            return
        self.total_days = max(0, int(data.get("total_days", 0)))
        for entry in data.get("months") or []:
            if isinstance(entry, dict):
                self.months.append(MonthBucket.from_dict(entry))
        self.current = MonthBucket.from_dict(data.get("current"))
