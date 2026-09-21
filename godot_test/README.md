# Godot concept test

This is a deliberately small Godot 4 project for testing the existing game's visual assets and basic player movement.

## Run

1. Open this `godot_test` folder in Godot 4.
2. Press **F6** or **F5**. The main scene is already set to `scenes/game.tscn`.
3. Move with **WASD** or the **arrow keys**, interact/chop with **E**, and toggle inventory with **I**.

The map is a procedurally generated 30×20 square terrain grid. Its authoritative resolution is 40 pixels per cell, matching `CELL_SIZE` in the Pygame game, so the default map is 1200×800 pixels. `MapGenerator` uses seeded coherent noise and editable `TerrainGenerationSettings` to assign grass or soil to every logical cell. `TerrainMapData` is the authoritative map queried by gameplay code. `TerrainRenderer` derives its polygon from `columns × rows × cell_size` and converts the grid into a small shared-corner weight texture for the GPU; the shader contains no map-size or terrain-placement rules.

Grass and soil rendering ports their current world-space noise settings, 48-colour palettes, base-colour shading, spatial palette mixing, and speckles from `environment_sandbox/terrain_mottle.py`. Shared tile corners use the same bilinear coverage and smooth land-to-land blend as `compose_cell_fills`, so boundaries are continuous instead of visibly tiled.

Select `Ground/ProceduralTerrain` in the Godot editor and expand **Generation Settings** to change the seed, distribution frequency, soil threshold, fractal octaves, dimensions, cell size, or grass border. Call `regenerate()` on that node after changing settings at runtime. Do not scale the renderer node: its scale is fixed to 1 at runtime, and its render area is regenerated from the map settings.

Trees and the two-frame left/right dog animations use copies of the existing SVG source assets. Their render scale comes from the same `cell_size`: the dog's 40-unit viewBox occupies one tile, while a tree's 80-unit canvas occupies two tiles with its trunk anchored to a 40px home cell. Camera limits and player movement bounds are derived from the generated map dimensions as well.

The player starts with an empty inventory. An axe is placed near the starting area. Stand near it and press **E** to pick it up, open inventory with **I**, and click the axe to equip it. An equipped item must advertise the `chop` action before a tree accepts it. Press **E** three times near a tree to fell it, then stand near the dropped wood and press **E** again to collect it.

Items are registered in `ItemDatabase`; `WorldItem` handles every map pickup regardless of item type, and the inventory panel creates its rows dynamically from `PlayerInventory`. `ChoppableTree` retains only tree-specific behavior—hit state, falling, and the item it drops—while the player interacts with all nearby objects through the shared `interact(player)` contract.
