"""Small production-game map for testing dense habitat and floating actors."""

from __future__ import annotations

from random_map_generator import GeneratedMap, MapOptions


def build_test_map() -> GeneratedMap:
    """Return a deterministic 24x18 map with every major wildlife habitat."""
    width, height = 24, 18
    terrain = [["grass" for _x in range(width)] for _y in range(height)]

    for y in range(1, 9):
        for x in range(1, 8):
            terrain[y][x] = "forest"
    for y in range(8, 17):
        for x in range(15, 23):
            terrain[y][x] = "forest"

    for y in range(height):
        for x in range(width):
            beside_forest = any(
                0 <= nx < width
                and 0 <= ny < height
                and terrain[ny][nx] == "forest"
                for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))
            )
            if terrain[y][x] == "grass" and beside_forest:
                terrain[y][x] = "meadow"

    for y in range(5, 11):
        for x in range(9, 14):
            terrain[y][x] = "water"
    for y in range(4, 12):
        for x in range(8, 15):
            if terrain[y][x] != "water":
                terrain[y][x] = "riparian"
    for y in range(1, 5):
        for x in range(16, 22):
            terrain[y][x] = "meadow"
    for y in range(13, 17):
        for x in range(3, 8):
            terrain[y][x] = "soil"
    for x, y in ((9, 2), (10, 2), (11, 2), (21, 6), (22, 6)):
        terrain[y][x] = "rock"

    start = (11, 14)
    terrain[start[1]][start[0]] = "grass"
    elevation = [
        [4.0 + abs(x - width / 2) * 0.18 + abs(y - height / 2) * 0.12 for x in range(width)]
        for y in range(height)
    ]
    moisture = [
        [0.85 if terrain[y][x] in ("water", "riparian") else 0.62 for x in range(width)]
        for y in range(height)
    ]
    options = MapOptions(
        width=width,
        height=height,
        seed=3309,
        composition="valley",
        climate="temperate",
        temperature=0.5,
        rainfall=0.65,
        roughness=0.25,
        generate_lake=True,
        generate_river=False,
    ).normalized()
    return GeneratedMap(options, terrain, elevation, moisture, start)
