"""Deterministic seasonal weather with persistent wet and dry spells."""

from __future__ import annotations

import random
from dataclasses import dataclass

from seasons import Season, season_for_day


@dataclass
class WeatherState:
    seed: int
    elapsed_days: int = 0
    raining: bool = False
    intensity: float = 0.0
    days_remaining: int = 0
    rain_cells: list[tuple[float, float, float, float]] | None = None

    @staticmethod
    def _balance_float(key: str, default: float) -> float:
        try:
            from balance_config import active_balance

            return float(active_balance().get_float(key))
        except Exception:
            return float(default)

    @classmethod
    def _balance_int(cls, key: str, default: int) -> int:
        return int(round(cls._balance_float(key, float(default))))

    def advance_day(self, calendar_day: int) -> float:
        """Advance one deterministic daily weather step and return rain 0–1."""
        season = season_for_day(calendar_day)
        start_chance = {
            Season.SPRING: 0.42,
            Season.SUMMER: 0.20,
            Season.AUTUMN: 0.48,
            Season.WINTER: 0.31,
        }[season]
        if self.raining:
            self.days_remaining -= 1
            if self.days_remaining > 0:
                self.elapsed_days += 1
                return self.intensity
            self.raining = False
            self.intensity = 0.0
            self.rain_cells = []
            self.elapsed_days += 1
            return 0.0

        rng = random.Random((int(self.seed) * 1_000_003) ^ self.elapsed_days)
        frequency = self._balance_float("WEATHER_FREQUENCY", 1.0)
        self.raining = rng.random() < min(1.0, start_chance * max(0.0, frequency))
        if self.raining:
            seasonal_strength = {
                Season.SPRING: 0.82,
                Season.SUMMER: 0.72,
                Season.AUTUMN: 0.92,
                Season.WINTER: 0.58,
            }[season]
            # Bias toward light/moderate rain while retaining occasional storms.
            scale = self._balance_float("WEATHER_INTENSITY", 1.0)
            self.intensity = max(
                0.08, min(1.0, (rng.random() ** 1.45) * seasonal_strength * scale)
            )
            self.days_remaining = max(
                1, self._balance_int("WEATHER_EVENT_DAYS", 3)
            )
            cell_count = max(1, self._balance_int("WEATHER_RAIN_CELLS", 4))
            radius = self._balance_float("WEATHER_CELL_RADIUS", 0.22)
            self.rain_cells = [
                (rng.random(), rng.random(), radius * rng.uniform(0.7, 1.3), rng.uniform(0.75, 1.25))
                for _ in range(cell_count)
            ]
        else:
            self.intensity = 0.0
            self.days_remaining = 0
            self.rain_cells = []
        self.elapsed_days += 1
        return self.intensity

    def localisation_grid(self, rows: int, cols: int) -> list[list[float]]:
        """Deterministic 0–~1.4 rain-cell field for the current event."""
        variation = max(
            0.0, min(1.0, self._balance_float("WEATHER_LOCAL_VARIATION", 0.9))
        )
        cells = self.rain_cells or []
        if not cells or variation <= 0.0:
            return [[1.0] * cols for _ in range(rows)]
        floor = 1.0 - variation
        grid = [[floor] * cols for _ in range(rows)]
        for y in range(rows):
            ny = (y + 0.5) / max(1, rows)
            for x in range(cols):
                nx = (x + 0.5) / max(1, cols)
                strongest = 0.0
                for cx, cy, radius, strength in cells:
                    dist2 = (nx - cx) ** 2 + (ny - cy) ** 2
                    radius2 = max(0.0025, radius * radius)
                    strongest = max(strongest, strength * max(0.0, 1.0 - dist2 / radius2))
                grid[y][x] = min(1.4, floor + variation * strongest)
        return grid

    def to_dict(self) -> dict:
        return {
            "seed": int(self.seed),
            "elapsed_days": int(self.elapsed_days),
            "raining": bool(self.raining),
            "intensity": float(self.intensity),
            "days_remaining": int(self.days_remaining),
            "rain_cells": [list(cell) for cell in (self.rain_cells or [])],
        }

    def load_dict(self, data: dict | None) -> None:
        if not isinstance(data, dict):
            return
        self.seed = int(data.get("seed", self.seed))
        self.elapsed_days = max(0, int(data.get("elapsed_days", 0)))
        self.raining = bool(data.get("raining", False))
        self.intensity = max(0.0, min(1.0, float(data.get("intensity", 0.0))))
        self.days_remaining = max(0, int(data.get("days_remaining", 0)))
        self.rain_cells = [
            tuple(float(value) for value in cell[:4])
            for cell in (data.get("rain_cells") or [])
            if isinstance(cell, (list, tuple)) and len(cell) >= 4
        ]
