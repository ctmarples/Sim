"""Seeded, configurable terrain generation used by the random-map tool.

The module deliberately has no pygame dependency, which makes it useful from
the GUI, tests, and future new-game screens alike.
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


TERRAINS = ("water", "grass", "meadow", "soil", "forest", "rock")
OUTPUT_TERRAINS = (*TERRAINS, "riparian")
CLIMATES = ("temperate", "arid", "tropical", "cold", "continental")
COMPOSITIONS = ("valley", "plains", "highlands", "archipelago")


@dataclass(slots=True)
class MapOptions:
    width: int = 96
    height: int = 72
    seed: int = 1
    composition: str = "valley"
    climate: str = "temperate"
    temperature: float = 0.5
    rainfall: float = 0.55
    roughness: float = 0.5
    generate_lake: bool = True
    generate_river: bool = True
    terrain_mix: dict[str, float] = field(
        default_factory=lambda: {
            "water": 0.12,
            "grass": 0.27,
            "meadow": 0.16,
            "soil": 0.16,
            "forest": 0.21,
            "rock": 0.08,
        }
    )

    def normalized(self) -> "MapOptions":
        self.width = max(16, min(256, int(self.width)))
        self.height = max(16, min(256, int(self.height)))
        self.temperature = _clamp(self.temperature)
        self.rainfall = _clamp(self.rainfall)
        self.roughness = _clamp(self.roughness)
        if self.composition not in COMPOSITIONS:
            raise ValueError(f"Unknown composition: {self.composition}")
        if self.climate not in CLIMATES:
            raise ValueError(f"Unknown climate: {self.climate}")
        clean = {name: max(0.0, float(self.terrain_mix.get(name, 0.0))) for name in TERRAINS}
        total = sum(clean.values())
        if total <= 0:
            raise ValueError("At least one terrain proportion must be greater than zero")
        self.terrain_mix = {name: value / total for name, value in clean.items()}
        return self


@dataclass(slots=True)
class GeneratedMap:
    options: MapOptions
    terrain: list[list[str]]
    elevation: list[list[float]]
    moisture: list[list[float]]

    def counts(self) -> dict[str, int]:
        result = {name: 0 for name in OUTPUT_TERRAINS}
        for row in self.terrain:
            for name in row:
                result[name] += 1
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": "sim-random-map-v1",
            "options": asdict(self.options),
            "terrain": self.terrain,
            "elevation": self.elevation,
            "moisture": self.moisture,
        }

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "GeneratedMap":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if data.get("format") != "sim-random-map-v1":
            raise ValueError("Not a Sim random-map file")
        options = MapOptions(**data["options"]).normalized()
        terrain = data["terrain"]
        elevation = data["elevation"]
        moisture = data["moisture"]
        if len(terrain) != options.height or any(len(row) != options.width for row in terrain):
            raise ValueError("Map terrain dimensions do not match its options")
        for label, grid in (("elevation", elevation), ("moisture", moisture)):
            if len(grid) != options.height or any(len(row) != options.width for row in grid):
                raise ValueError(f"Map {label} dimensions do not match its options")
        if any(name not in OUTPUT_TERRAINS for row in terrain for name in row):
            raise ValueError("Map contains an unknown terrain type")
        return cls(options, terrain, elevation, moisture)

    def apply_to_world(self, world: Any) -> None:
        """Replace terrain/elevation on an existing ``world.World`` instance."""
        import random

        from trees import pick_tree_species, resolve_tree
        from world import FeatureType, TerrainType

        if world.cols != self.options.width or world.rows != self.options.height:
            raise ValueError("Generated map dimensions do not match the World")
        names = {
            "water": TerrainType.WATER,
            "grass": TerrainType.GRASS,
            "meadow": TerrainType.MEADOW,
            "soil": TerrainType.SOIL,
            "forest": TerrainType.FOREST_FLOOR,
            "rock": TerrainType.ROCK,
            "riparian": TerrainType.RIPARIAN,
        }
        rng = random.Random(self.options.seed ^ 0x4D4150)
        for y, row in enumerate(self.terrain):
            for x, name in enumerate(row):
                cell = world.cells[y][x]
                cell.terrain = names[name]
                cell.feature = FeatureType.NONE
                cell.deposit = 0
                cell.tree_species = None
                if name == "forest" and rng.random() < 0.68:
                    species = pick_tree_species(rng)
                    cell.feature = FeatureType.TREE
                    cell.tree_species = species
                    cell.deposit = resolve_tree(species).yield_amount
                elif name == "rock" and rng.random() < 0.30:
                    cell.feature = FeatureType.ROCK
                    cell.deposit = rng.randint(2, 8)
        # Keep the inherited settlement entrance usable even when a requested
        # water/rock mix ranks that coordinate highly.
        for cx, cy in (world.home_pos, world.start_pos, world.workstation_pos):
            if 0 <= cx < world.cols and 0 <= cy < world.rows:
                cell = world.cells[cy][cx]
                cell.terrain = TerrainType.GRASS
                cell.feature = FeatureType.NONE
                cell.deposit = 0
                cell.tree_species = None
        _seed_starter_deposits(world, rng)
        # Convert cell-centre elevation to the corner grid expected by the game.
        world.height_corners = _centres_to_corners(self.elevation)
        world.bump_terrain()
        world.init_fertility()


def generate_map(options: MapOptions) -> GeneratedMap:
    """Generate a deterministic map from terrain, structure, and climate options."""
    opt = options.normalized()
    rng = random.Random(opt.seed)
    elevation = _structure_field(opt, rng)
    moisture = _noise_grid(opt.width, opt.height, rng, 7, 0.62)
    detail = _noise_grid(opt.width, opt.height, rng, 5, 0.48)
    heat = _latitude_heat(opt.width, opt.height, opt.temperature, detail)

    climate_rain, climate_temp = {
        "temperate": (0.55, 0.52), "arid": (0.18, 0.72),
        "tropical": (0.82, 0.82), "cold": (0.46, 0.20),
        "continental": (0.42, 0.45),
    }[opt.climate]
    rain = _clamp((opt.rainfall + climate_rain) * 0.5)
    temp = _clamp((opt.temperature + climate_temp) * 0.5)
    for y in range(opt.height):
        for x in range(opt.width):
            # Orographic drying and a small elevation lapse-rate.
            moisture[y][x] = _clamp(moisture[y][x] * 0.65 + rain * 0.55 - elevation[y][x] * 0.16)
            heat[y][x] = _clamp(heat[y][x] * 0.55 + temp * 0.55 - elevation[y][x] * 0.22)

    terrain = _assign_by_mix(opt, elevation, moisture, heat, detail)
    _paint_riparian(terrain)
    return GeneratedMap(opt, terrain, elevation, moisture)


def _assign_by_mix(opt: MapOptions, elevation, moisture, heat, detail):
    """Assign exact-ish requested counts while retaining spatial coherence."""
    scores: dict[str, list[tuple[float, int, int]]] = {name: [] for name in TERRAINS}
    lake, river = _hydrology_shapes(opt)
    for y in range(opt.height):
        for x in range(opt.width):
            e, m, t, d = elevation[y][x], moisture[y][x], heat[y][x], detail[y][x]
            water_score = 1.0 - e + d * .08
            u, v = x / max(1, opt.width - 1), y / max(1, opt.height - 1)
            if opt.generate_lake:
                water_score += _lake_score(u, v, d, lake) * 2.5
            if opt.generate_river:
                river_d, along = _distance_to_path(u, v, river)
                width = .018 + detail[y][x] * .026 + ((int(along * 11) * 37 + opt.seed) % 13) / 1800
                water_score += max(0.0, 1.0 - river_d / width) * 2.2
            scores["water"].append((water_score, x, y))
            scores["rock"].append((e * 1.15 + (1.0 - m) * .25 + d * .08, x, y))
            scores["forest"].append((m * .85 + (1.0 - abs(t - .55)) * .25 + d * .12, x, y))
            scores["meadow"].append((m * .35 + t * .25 + (1.0 - abs(e - .45)) * .25 + d * .12, x, y))
            scores["soil"].append(((1.0 - m) * .45 + t * .15 + (1.0 - abs(e - .42)) * .25 + d * .1, x, y))
            scores["grass"].append(((1.0 - abs(m - .52)) * .5 + (1.0 - abs(e - .48)) * .3 + d * .1, x, y))

    total = opt.width * opt.height
    targets = {name: round(opt.terrain_mix[name] * total) for name in TERRAINS}
    targets["grass"] += total - sum(targets.values())
    result = [["" for _ in range(opt.width)] for _ in range(opt.height)]
    unassigned = {(x, y) for y in range(opt.height) for x in range(opt.width)}
    # Constrained types claim their best cells first; versatile grass fills gaps.
    for name in ("water", "rock", "forest", "soil", "meadow", "grass"):
        ranked = sorted(scores[name], reverse=True)
        claimed = 0
        for _, x, y in ranked:
            if (x, y) not in unassigned:
                continue
            result[y][x] = name
            unassigned.remove((x, y))
            claimed += 1
            if claimed >= targets[name]:
                break
    for x, y in unassigned:
        result[y][x] = "grass"
    return result


def _hydrology_shapes(opt: MapOptions):
    """Seed-stable organic lake outline and wandering piecewise river."""
    rng = random.Random(opt.seed ^ 0x48594452)
    lake = {
        "x": rng.uniform(.24, .76),
        "y": rng.uniform(.25, .72),
        "radius": rng.uniform(.105, .155),
        "phase1": rng.random() * math.tau,
        "phase2": rng.random() * math.tau,
        "phase3": rng.random() * math.tau,
    }
    # A biased random walk across the map. Control points avoid the mechanical
    # periodicity of a sine curve while interpolation keeps the channel joined.
    horizontal = rng.random() < .5
    points = []
    cross = rng.uniform(.22, .78)
    count = 9
    for i in range(count):
        along = i / (count - 1)
        cross = max(.08, min(.92, cross + rng.uniform(-.16, .16)))
        points.append((cross, along) if not horizontal else (along, cross))
    return lake, points


def _lake_score(u: float, v: float, noise: float, lake: dict[str, float]) -> float:
    dx, dy = u - lake["x"], v - lake["y"]
    angle = math.atan2(dy, dx)
    # Several incommensurate lobes plus local coherent noise create coves and
    # peninsulas instead of an oval boundary.
    boundary = lake["radius"] * (
        1.0
        + .23 * math.sin(angle * 3 + lake["phase1"])
        + .14 * math.sin(angle * 5 + lake["phase2"])
        + .09 * math.sin(angle * 7 + lake["phase3"])
        + (noise - .5) * .28
    )
    distance = math.hypot(dx, dy * 1.08)
    return max(0.0, 1.0 - distance / max(.025, boundary))


def _distance_to_path(u: float, v: float, points: list[tuple[float, float]]) -> tuple[float, float]:
    best, best_along = 9.0, 0.0
    for index, ((x0, y0), (x1, y1)) in enumerate(zip(points, points[1:])):
        dx, dy = x1 - x0, y1 - y0
        length2 = dx * dx + dy * dy
        t = 0.0 if length2 <= 1e-9 else max(0.0, min(1.0, ((u-x0)*dx + (v-y0)*dy) / length2))
        distance = math.hypot(u - (x0 + dx*t), v - (y0 + dy*t))
        if distance < best:
            best = distance
            best_along = (index + t) / max(1, len(points) - 1)
    return best, best_along


def _paint_riparian(terrain: list[list[str]]) -> None:
    """Derive a one-cell vegetated bank around all standing/flowing water."""
    rows, cols = len(terrain), len(terrain[0])
    banks: set[tuple[int, int]] = set()
    for y in range(rows):
        for x in range(cols):
            if terrain[y][x] != "water":
                continue
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < cols and 0 <= ny < rows and terrain[ny][nx] in (
                        "grass", "meadow", "soil", "forest"
                    ):
                        banks.add((nx, ny))
    for x, y in banks:
        terrain[y][x] = "riparian"


def _seed_starter_deposits(world: Any, rng: random.Random) -> None:
    """Guarantee accessible loose wood and small rocks near the settlement."""
    from resource_balance import ROCK_SMALL_MAX, ROCK_SMALL_MIN, WOOD_BUSH_YIELD
    from world import FeatureType, PLANTABLE_LAND

    hx, hy = world.home_pos
    reserved = {world.home_pos, world.start_pos, world.workstation_pos}
    candidates = []
    for y in range(max(0, hy - 6), min(world.rows, hy + 7)):
        for x in range(max(0, hx - 6), min(world.cols, hx + 7)):
            cell = world.cells[y][x]
            if (x, y) not in reserved and cell.feature == FeatureType.NONE and cell.terrain in PLANTABLE_LAND:
                candidates.append((max(abs(x-hx), abs(y-hy)), rng.random(), x, y))
    candidates.sort()
    pool = [(x, y) for _distance, _roll, x, y in candidates[:50]]
    rng.shuffle(pool)
    wood_count = min(7, len(pool))
    for _ in range(wood_count):
        x, y = pool.pop()
        cell = world.cells[y][x]
        cell.feature = FeatureType.WOOD_BUSH
        cell.crop_kind = "wood_bush"
        cell.deposit = WOOD_BUSH_YIELD
        cell.growth_ticks = world._fallen_wood_lifetime_ticks()
    for _ in range(min(6, len(pool))):
        x, y = pool.pop()
        cell = world.cells[y][x]
        cell.feature = FeatureType.ROCK
        cell.deposit = rng.randint(ROCK_SMALL_MIN, ROCK_SMALL_MAX)


def _structure_field(opt: MapOptions, rng: random.Random) -> list[list[float]]:
    noise = _noise_grid(opt.width, opt.height, rng, 6, 0.54)
    field = [[0.0] * opt.width for _ in range(opt.height)]
    for y in range(opt.height):
        v = y / max(1, opt.height - 1)
        for x in range(opt.width):
            u = x / max(1, opt.width - 1)
            n = noise[y][x]
            if opt.composition == "valley":
                axis = .5 + math.sin(u * math.tau * 1.35 + opt.seed) * .11
                base = .28 + min(1.0, abs(v - axis) * 2.2) * .62
            elif opt.composition == "highlands":
                base = .42 + n * .48
            elif opt.composition == "archipelago":
                edge = min(u, v, 1-u, 1-v) * 2.0
                base = n * .78 + min(.22, edge * .18)
            else:  # plains
                base = .38 + n * .25
            field[y][x] = _clamp(base * (0.72 + opt.roughness * .42) + (n - .5) * opt.roughness * .35)
    return field


def _noise_grid(width: int, height: int, rng: random.Random, spacing: int, persistence: float):
    result = [[0.0] * width for _ in range(height)]
    amplitude, total_amp = 1.0, 0.0
    while spacing >= 1:
        gw, gh = width // spacing + 2, height // spacing + 2
        knots = [[rng.random() for _ in range(gw)] for _ in range(gh)]
        for y in range(height):
            fy, iy = y / spacing, y // spacing
            ty = _smooth(fy - iy)
            for x in range(width):
                fx, ix = x / spacing, x // spacing
                tx = _smooth(fx - ix)
                a = knots[iy][ix] * (1-tx) + knots[iy][ix+1] * tx
                b = knots[iy+1][ix] * (1-tx) + knots[iy+1][ix+1] * tx
                result[y][x] += (a * (1-ty) + b * ty) * amplitude
        total_amp += amplitude
        amplitude *= persistence
        spacing //= 2
    return [[value / total_amp for value in row] for row in result]


def _latitude_heat(width, height, temperature, detail):
    return [[_clamp(temperature + .18 - abs((y / max(1, height-1)) - .5) * .35 + (detail[y][x]-.5)*.18)
             for x in range(width)] for y in range(height)]


def _centres_to_corners(values):
    rows, cols = len(values), len(values[0])
    corners = [[0.0] * (cols + 1) for _ in range(rows + 1)]
    for cy in range(rows + 1):
        for cx in range(cols + 1):
            nearby = [values[y][x] for y in range(max(0, cy-1), min(rows, cy+1))
                      for x in range(max(0, cx-1), min(cols, cx+1))]
            corners[cy][cx] = round(sum(nearby) / len(nearby) * 80.0, 3)
    return corners


def _smooth(value: float) -> float:
    return value * value * (3.0 - 2.0 * value)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
