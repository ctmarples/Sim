# Godot concept test

This is a deliberately small Godot 4 project for testing the existing game's visual assets and basic player movement.

## Run

1. Open this `godot_test` folder in Godot 4.
2. Press **F6** or **F5**. The main scene is already set to `scenes/game.tscn`.
3. Move with **WASD** or the **arrow keys**, interact/chop with **E**, and toggle inventory with **I**.

The map is a procedurally generated 30×20 square terrain grid. Its authoritative resolution is 40 pixels per cell, matching `CELL_SIZE` in the Pygame game, so the default map is 1200×800 pixels. `MapGenerator` uses seeded coherent noise and editable `TerrainGenerationSettings` to assign grass or soil to every logical cell. `TerrainMapData` is the authoritative map queried by gameplay code. `TerrainRenderer` derives its polygon from `columns × rows × cell_size` and converts the grid into a small shared-corner weight texture for the GPU; the shader contains no map-size or terrain-placement rules.

Grass and soil rendering ports their current world-space noise settings, 48-colour palettes, base-colour shading, spatial palette mixing, and speckles from `environment_sandbox/terrain_mottle.py`. Shared tile corners use the same bilinear coverage and smooth land-to-land blend as `compose_cell_fills`, so boundaries are continuous instead of visibly tiled.

Select `Ground/ProceduralTerrain` in the Godot editor and expand **Generation Settings** to change the seed, distribution frequency, soil threshold, fractal octaves, dimensions, cell size, grass border, or height-test settings. `Height Amplitude` controls generated corner heights, while `Height Lift Pixels` controls their visual projection without changing logical map coordinates. Call `regenerate()` on that node after changing settings at runtime. Do not scale the renderer node: its scale is fixed to 1 at runtime, and its render area is regenerated from the map settings.

Trees and the two-frame left/right dog animations use copies of the existing SVG source assets. Their render scale comes from the same `cell_size`: the dog's 40-unit viewBox occupies one tile, while a tree's 80-unit canvas occupies two tiles with its trunk anchored to a 40px home cell. Camera limits and player movement bounds are derived from the generated map dimensions as well.

The player starts with an empty inventory. An axe is placed near the starting area. Stand near it and press **E** to pick it up, open inventory with **I**, and click the axe to equip it. An equipped item must advertise the `chop` action before a tree accepts it. Press **E** three times near a tree to fell it, then stand near the dropped wood and press **E** again to collect it.

Items are registered in `ItemDatabase`; `WorldItem` handles every map pickup regardless of item type, and the inventory panel creates its rows dynamically from `PlayerInventory`. `ChoppableTree` retains only tree-specific behavior—hit state, falling, and the item it drops—while the player interacts with all nearby objects through the shared `interact(player)` contract.

A forester and storehouse are placed near the starting area. Each is a `ContainerBuilding` with its own independent `ItemInventory`. Press **E** nearby to open a two-pane view of the player and building inventories. Clicking an item transfers one unit to the opposite inventory; the same container implementation can be reused by later buildings.

Buildings are authored as scenes under `scenes/buildings`. `building.tscn` supplies the common physical-collision, selection-area, inventory, footprint, and recipe structure. Each concrete building owns a local `Visual` sprite so its SVG position and scale are freely editable in the 2D viewport. `forester.tscn` and `storehouse.tscn` inherit the shared behavior and expose their own SVG, footprint, capacity, recipes, and editable shapes. The map instantiates these scenes instead of constructing buildings in code.

Building map coordinates identify the top-left tile of their footprint. Both current buildings use a 3×2 footprint. Placement derives the scene origin from `top_left × cell_size + footprint × cell_size ÷ 2`, so their six occupied cells remain aligned to the same 40px grid. Building scenes are authored at a canonical 40px cell size and scaled only when the map's `cell_size` differs.

Open either inherited building scene in the 2D editor to see a blue 3×2 footprint preview and yellow footprint-centre origin. This preview comes from the separate `FootprintPreview` editor tool and is editor-only. Select the `Visual` child to independently change the SVG's position and scale without changing the logical footprint. Edit `PhysicalCollision` and `SelectionArea/SelectionShape` separately; neither is inferred from the artwork.

Each building scene contains a locked `FootprintPreview` editor-only background node. It stays fixed at the scene origin while the building root, `Visual`, `PhysicalCollision`, and `SelectionArea` remain freely movable and resizable. Change `Footprint Cells` and `Editor Cell Size` on the building root; edit the artwork independently on `Visual`.

Building cursor selection and actor interaction are separate. `SelectionArea` follows the visible artwork and is used only for mouse clicks. `InteractionArea` is one tile wide and sits in the central bottom cell of the 3×2 footprint; it is the building entrance for players and villagers. Villagers build an A* grid from collision-layer-1 physics shapes when travelling to a building, so they route around collision surfaces to reach an entrance on the opposite side.

One animated villager is also present. Click the villager directly, or press **V** and select it from the list. Press **Assign**, then click the forester building. The assigned villager has an inventory capacity of three total items and will wait until an axe is available in the storehouse. It then collects and equips the axe, finds and chops a tree, collects dropped wood, and returns to the forester to deposit wood whenever its inventory is full. Put the map axe into the storehouse through the two-pane transfer UI to start the automated workflow.

Press **G** to toggle the authoritative terrain-cell grid. Press **O** to toggle runtime object origins, names, physical collision shapes, and full-icon selection areas. These overlays follow moving actors and make discrepancies between a sprite, its logical position, and its collision footprint visible.

Terrain height is stored at the `(columns + 1) × (rows + 1)` shared cell corners. The terrain renderer builds a subdivided `ArrayMesh`, then the canvas shader lifts every mesh vertex by its corner height and applies interpolated slope lighting while retaining the procedural grass/soil sampling in flat logical coordinates. Height is visual-only: physics, grid coordinates, and pathfinding remain flat, as in the original game. `TerrainMapData.height_at_world()` and the terrain renderer's global projection helpers provide the shared bilinear transform for artwork and overlays.

Actor, pickup, tree, and building artwork is projected from its flat logical position with the same bilinear height lookup. Buildings sample their bottom-centre entrance as their visual foot. Cursor selection areas follow the projected artwork, while physical collision and interaction areas remain on the flat simulation plane. Terrain and artwork sample the same bilinear corner-light texture. `relief_tint.gdshader` samples that field separately for every visible asset pixel, including the pixel's vertical map position, so a shadow boundary can cross only the lower or upper part of a tall sprite. The deliberately gentle tint uses a 25% maximum shadow mix and 10% highlight mix. The **G** overlay uses the shared projection helper, providing the pattern for future placement, territory, path, and cursor overlays.
