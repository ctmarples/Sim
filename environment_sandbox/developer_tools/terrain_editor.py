"""Terrain ecology authoring: statistical bands per terrain parameter.

Each terrain stores centre + spread for moisture, fertility, temperature
offset, and rainfall multiplier. Live layers sample within those bands.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

from .content_io import get_content_root

BAND_FIELDS = (
    "soil_moisture",
    "fertility",
    "temperature_offset_c",
    "rainfall_multiplier",
)

# Default half-width when migrating legacy single floats.
DEFAULT_SPREADS = {
    "soil_moisture": 0.10,
    "fertility": 0.16,
    "temperature_offset_c": 0.40,
    "rainfall_multiplier": 0.04,
}


def _band(centre: float, spread: float) -> dict[str, float]:
    return {"centre": float(centre), "spread": max(0.0, float(spread))}


def _default_row(centre_moisture, centre_fertility, temp, rain, *, barren: bool = False) -> dict:
    zero = 0.0 if barren else None
    return {
        "soil_moisture": _band(
            centre_moisture,
            0.0 if barren else DEFAULT_SPREADS["soil_moisture"],
        ),
        "fertility": _band(
            centre_fertility,
            0.0 if barren or centre_fertility <= 0 else DEFAULT_SPREADS["fertility"],
        ),
        "temperature_offset_c": _band(
            temp,
            0.0 if barren else DEFAULT_SPREADS["temperature_offset_c"],
        ),
        "rainfall_multiplier": _band(
            rain,
            0.0 if barren else DEFAULT_SPREADS["rainfall_multiplier"],
        ),
    }


DEFAULTS = {
    "SOIL": _default_row(0.48, 0.70, 0.8, 1.0),
    "FOREST_FLOOR": _default_row(0.62, 0.88, -0.8, 1.0),
    "GRASS": _default_row(0.40, 0.62, 0.0, 1.0),
    "MEADOW": _default_row(0.46, 0.72, 0.2, 1.0),
    "RIPARIAN": _default_row(0.78, 0.78, -0.8, 1.08),
    "WATER": _default_row(1.0, 0.0, 0.0, 1.0, barren=True),
    "RIVER": _default_row(1.0, 0.0, 0.0, 1.0, barren=True),
    "ROCK": _default_row(0.08, 0.0, 1.5, 1.0, barren=True),
    "URBAN": _default_row(0.04, 0.0, 2.0, 1.0, barren=True),
    "PATH": _default_row(0.12, 0.0, 0.8, 1.0, barren=True),
}

PATH = Path(get_content_root()) / "objects_data" / "terrain_ecology.json"
_VALUES = None


def _coerce_band(raw, field: str, fallback_centre: float) -> dict[str, float]:
    default_spread = DEFAULT_SPREADS.get(field, 0.0)
    if isinstance(raw, dict):
        centre = float(raw.get("centre", raw.get("mean", fallback_centre)))
        spread = float(raw.get("spread", raw.get("variation", default_spread)))
        return _band(centre, spread)
    if raw is None:
        return _band(fallback_centre, default_spread)
    return _band(float(raw), default_spread)


def load_values(path=PATH):
    values = {key: {field: dict(band) for field, band in row.items()} for key, row in DEFAULTS.items()}
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw = {}
    if isinstance(raw, dict):
        for key, row in raw.items():
            if key not in values or not isinstance(row, dict):
                continue
            for field in BAND_FIELDS:
                fallback = values[key][field]["centre"]
                values[key][field] = _coerce_band(row.get(field), field, fallback)
    return values


def terrain_key(terrain) -> str:
    return getattr(terrain, "name", str(terrain))


def terrain_band(terrain, field: str) -> tuple[float, float]:
    """Return (centre, spread) for one ecology parameter."""
    global _VALUES
    if _VALUES is None:
        _VALUES = load_values()
    key = terrain_key(terrain)
    row = _VALUES.get(key) or DEFAULTS.get(key) or {}
    band = row.get(field) or DEFAULTS.get(key, {}).get(field) or _band(0.0, 0.0)
    return float(band["centre"]), float(band["spread"])


def terrain_value(terrain, field):
    """Centre value — keeps existing call sites working."""
    return terrain_band(terrain, field)[0]


def ecology_bands_for(terrain) -> dict[str, dict[str, float]]:
    """Copy of centre/spread bands for one terrain (T-menu)."""
    global _VALUES
    if _VALUES is None:
        _VALUES = load_values()
    key = terrain_key(terrain)
    row = _VALUES.get(key) or DEFAULTS.get(key) or {}
    return {field: dict(row.get(field, DEFAULTS.get(key, {}).get(field, _band(0.0, 0.0))))
            for field in BAND_FIELDS}


def ecology_terrain_keys() -> tuple[str, ...]:
    return tuple(DEFAULTS.keys())


def _clamp_band_part(field: str, part: str, value: float) -> float:
    value = float(value)
    if part == "spread":
        # Keep mottling modest — large spreads made moisture look broken.
        if field in ("soil_moisture", "fertility"):
            return max(0.0, min(0.25, value))
        if field == "temperature_offset_c":
            return max(0.0, min(5.0, value))
        if field == "rainfall_multiplier":
            return max(0.0, min(0.25, value))
        return max(0.0, value)
    if field in ("soil_moisture", "fertility"):
        return max(0.0, min(1.0, value))
    if field == "rainfall_multiplier":
        return max(0.0, min(2.0, value))
    if field == "temperature_offset_c":
        return max(-5.0, min(5.0, value))
    return value


def set_terrain_ecology_band_part(
    terrain_key_name: str,
    field: str,
    part: str,
    value: float,
    *,
    persist: bool = False,
) -> float:
    """Set centre or spread for one terrain parameter."""
    global _VALUES
    if _VALUES is None:
        _VALUES = load_values()
    if terrain_key_name not in _VALUES:
        raise KeyError(terrain_key_name)
    if field not in BAND_FIELDS or part not in ("centre", "spread"):
        raise KeyError(f"{field}.{part}")
    clamped = _clamp_band_part(field, part, value)
    _VALUES[terrain_key_name][field][part] = clamped
    if persist:
        _write_values(_VALUES)
    return clamped


def adjust_terrain_ecology_band_part(
    terrain_key_name: str,
    field: str,
    part: str,
    delta: float,
    *,
    persist: bool = False,
) -> float:
    centre, spread = terrain_band(terrain_key_name, field)
    current = centre if part == "centre" else spread
    return set_terrain_ecology_band_part(
        terrain_key_name, field, part, current + float(delta), persist=persist
    )


# Back-compat aliases used by earlier T-menu wiring.
def ecology_values_for(terrain) -> dict:
    return {field: band["centre"] for field, band in ecology_bands_for(terrain).items()}


def set_terrain_ecology_field(terrain_key_name: str, field: str, value: float, *, persist: bool = False) -> float:
    return set_terrain_ecology_band_part(terrain_key_name, field, "centre", value, persist=persist)


def adjust_terrain_ecology_field(terrain_key_name: str, field: str, delta: float, *, persist: bool = False) -> float:
    return adjust_terrain_ecology_band_part(terrain_key_name, field, "centre", delta, persist=persist)


def _write_values(values) -> None:
    path = PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix="terrain_ecology.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(values, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def ecology_signature():
    """Stable fingerprint used to reject stale terrain-derived save grids."""
    global _VALUES
    if _VALUES is None:
        _VALUES = load_values()
    raw = json.dumps(_VALUES, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def invalidate_ecology_cache() -> None:
    global _VALUES
    _VALUES = None


class TerrainEditorService:
    def __init__(self, plants, root=None):
        self.plants = plants
        self.path = Path(root or get_content_root()) / "objects_data" / "terrain_ecology.json"
        self.values = load_values(self.path)
        self.terrain = "GRASS"

    def select(self, key):
        self.terrain = key

    def wild_plants(self):
        return [p for p in self.plants.records if p.can_grow_wild]

    def selected_plants(self):
        return {p.key for p in self.wild_plants() if self.terrain in p.wild.get("terrains", [])}

    def save(self, values, plant_keys):
        global _VALUES
        row = {field: dict(band) for field, band in self.values[self.terrain].items()}
        for field, raw in values.items():
            if field not in BAND_FIELDS:
                continue
            if isinstance(raw, dict):
                row[field] = _coerce_band(raw, field, row[field]["centre"])
            else:
                row[field] = _band(float(raw), row[field]["spread"])
        centre_ok = all(0 <= row[f]["centre"] <= 1 for f in ("soil_moisture", "fertility"))
        rain_ok = 0 <= row["rainfall_multiplier"]["centre"] <= 2
        if not (centre_ok and rain_ok):
            return False, "Moisture/fertility centres must be 0–1; rainfall centre 0–2."
        self.values[self.terrain] = row
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix="terrain_ecology.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(self.values, handle, indent=2, sort_keys=True)
                handle.write("\n")
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        self.plants.save_terrain_membership(self.terrain, set(plant_keys))
        if self.path == PATH:
            _VALUES = {key: {f: dict(b) for f, b in row.items()} for key, row in self.values.items()}
        return True, f"Saved {self.terrain.replace('_', ' ').title()} ecology and wild plants."
