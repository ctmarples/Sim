"""Selectable calendar policies sharing one seasonal simulation coordinate.

The ecological coordinate deliberately remains the historical 0..112 scale so
existing annual curves keep their tuning.  A displayed day is only a day/night
cycle: flexible calendars may fit any number of those cycles into each 28-unit
season without changing what a simulation year means.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from seasons import DAYS_PER_SEASON, SEASON_ORDER, YEAR_DAYS, Season, season_for_day


class CalendarMode(str, Enum):
    LEGACY = "legacy"
    FLEXIBLE = "flexible"


DEFAULT_FLEXIBLE_DAYS = 4


@dataclass
class CalendarPolicy:
    mode: CalendarMode = CalendarMode.LEGACY
    season_days: dict[Season, int] = field(
        default_factory=lambda: {s: DEFAULT_FLEXIBLE_DAYS for s in SEASON_ORDER}
    )
    pending_mode: CalendarMode | None = None
    pending_season_days: dict[Season, int] = field(default_factory=dict)
    active_days_in_season: int = DAYS_PER_SEASON

    def days_for(self, season: Season, *, mode: CalendarMode | None = None) -> int:
        selected = self.mode if mode is None else mode
        if selected == CalendarMode.LEGACY:
            return DAYS_PER_SEASON
        return max(1, int(self.season_days.get(season, DEFAULT_FLEXIBLE_DAYS)))

    def begin(self, season: Season) -> None:
        """Establish the duration of a newly-created/current season."""
        self.active_days_in_season = self.days_for(season)

    def queue(self, mode: CalendarMode, season_days: dict[Season, int]) -> None:
        """Queue preferences; they become active only as seasons begin."""
        self.pending_mode = mode if mode != self.mode else None
        self.pending_season_days = {
            season: max(1, int(value))
            for season, value in season_days.items()
            if max(1, int(value)) != self.season_days.get(season)
        }

    def enter_season(self, season: Season) -> None:
        """Apply a mode switch at the next boundary and this season's new length."""
        if self.pending_mode is not None:
            self.mode = self.pending_mode
            self.pending_mode = None
        if season in self.pending_season_days:
            self.season_days[season] = self.pending_season_days.pop(season)
        self.active_days_in_season = self.days_for(season)

    @property
    def ecology_units_per_day(self) -> float:
        return DAYS_PER_SEASON / max(1, self.active_days_in_season)

    def snapshot(self, calendar_position: float, day_fraction: float = 0.0) -> dict:
        season = season_for_day(calendar_position)
        season_start = SEASON_ORDER.index(season) * DAYS_PER_SEASON
        season_progress = ((calendar_position - season_start) % YEAR_DAYS) / DAYS_PER_SEASON
        displayed = min(
            self.active_days_in_season - 1,
            int(season_progress * self.active_days_in_season),
        )
        return {
            "mode": self.mode.value,
            "season": season,
            "season_progress": max(0.0, min(1.0, season_progress)),
            "year_position": (calendar_position % YEAR_DAYS) / YEAR_DAYS,
            "day_in_season": displayed,
            "days_in_season": self.active_days_in_season,
            "time_of_day": max(0.0, min(1.0, day_fraction)),
        }

    def to_dict(self) -> dict:
        return {
            "mode": self.mode.value,
            "pending_mode": self.pending_mode.value if self.pending_mode else None,
            "season_days": {s.name: self.season_days[s] for s in SEASON_ORDER},
            "pending_season_days": {s.name: n for s, n in self.pending_season_days.items()},
            "active_days_in_season": self.active_days_in_season,
        }

    @classmethod
    def from_dict(cls, data: object, season: Season) -> "CalendarPolicy":
        if not isinstance(data, dict):
            policy = cls()
            policy.begin(season)
            return policy
        try:
            mode = CalendarMode(str(data.get("mode", CalendarMode.LEGACY.value)))
        except ValueError:
            mode = CalendarMode.LEGACY
        policy = cls(mode=mode)
        raw_days = data.get("season_days", {})
        if isinstance(raw_days, dict):
            for item in SEASON_ORDER:
                try:
                    policy.season_days[item] = max(1, int(raw_days.get(item.name, DEFAULT_FLEXIBLE_DAYS)))
                except (TypeError, ValueError):
                    pass
        raw_pending = data.get("pending_season_days", {})
        if isinstance(raw_pending, dict):
            for name, value in raw_pending.items():
                try:
                    policy.pending_season_days[Season[str(name)]] = max(1, int(value))
                except (KeyError, TypeError, ValueError):
                    pass
        pending_mode = data.get("pending_mode")
        if pending_mode:
            try:
                policy.pending_mode = CalendarMode(str(pending_mode))
            except ValueError:
                pass
        policy.active_days_in_season = max(
            1, int(data.get("active_days_in_season", policy.days_for(season)))
        )
        return policy
