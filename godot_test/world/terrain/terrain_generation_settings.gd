class_name TerrainGenerationSettings
extends Resource

@export_category("Map Dimensions")
@export_range(2, 256, 1) var columns := 30
@export_range(2, 256, 1) var rows := 20
## One logical game tile is 40×40 render pixels, matching CELL_SIZE in Pygame.
@export_range(8.0, 256.0, 1.0) var cell_size := 40.0

@export_category("Land Distribution")
## Reusing a seed reproduces terrain, height, rivers, and forests.
@export var seed := 3896
## Feature size of the grass/soil distribution. Lower values make larger areas.
@export_range(0.01, 1.0, 0.01) var frequency := 0.10
## Higher values reduce the amount of soil.
@export_range(-1.0, 1.0, 0.01) var soil_threshold := -0.08
@export_range(1, 8, 1) var fractal_octaves := 3
@export_range(0, 4, 1) var grass_border_cells := 1

@export_category("Water and Secondary Biomes")
## Biome-noise values below this become water; lower values mean less water.
@export_range(-1.0, 1.0, 0.01) var water_threshold := -0.62
## Remaining land above this value may become meadow; lower means more meadow.
@export_range(-1.0, 1.0, 0.01) var meadow_threshold := -0.18
## Biome-noise values above this become rock; higher values mean less rock.
@export_range(-1.0, 1.0, 0.01) var rock_threshold := 0.62
## Feature size shared by meadow, rock, and water regions.
@export_range(0.005, 0.5, 0.005) var biome_frequency := 0.045
## Half-width of the generated meandering river in logical cells.
@export_range(0.0, 4.0, 0.1) var river_half_width_cells := 0.8
## Land distance around water converted to riparian terrain.
@export_range(0.0, 8.0, 0.25) var riparian_width_cells := 1.5

@export_category("Mixed Forest")
## Number of radius-three forest clusters; zero selects max(3, columns / 10).
@export_range(0, 64, 1) var forest_cluster_count := 0
## Performance/population cap applied after coherent clusters are built.
@export_range(4, 2000, 1) var maximum_trees := 600
## Minimum cardinally connected occupied trees required to create Forest Floor.
@export_range(4, 64, 1) var minimum_forest_floor_trees := 4
## Logical cells reserved for the prototype buildings and immediate spawn point.
@export var forest_exclusion_rects: Array[Rect2i] = [Rect2i(18, 10, 3, 6), Rect2i(13, 10, 4, 2)]

@export_category("Height Generation and Projection")
@export var height_enabled := true
## Logical elevation range; this is separate from screen projection strength.
@export_range(0.0, 512.0, 1.0, "or_greater") var height_amplitude := 32.0
@export_range(0.005, 0.25, 0.005) var height_frequency := 0.035
## Upward screen pixels per logical height unit.
@export_range(0.0, 16.0, 0.1, "or_greater") var height_lift_pixels := 1.0

@export_category("Cliff Test")
@export var cliff_enabled := true
## Grid-node polylines. Repeat the first point at the end to make an island.
## Segments should be horizontal, vertical, or exact 45-degree diagonals.
@export var cliff_paths: Array[PackedVector2Array] = [
	PackedVector2Array([Vector2(1, 4), Vector2(8, 4), Vector2(10, 6), Vector2(18, 6), Vector2(22, 2), Vector2(28, 2)]),
	PackedVector2Array([Vector2(1, 10), Vector2(4, 10), Vector2(5, 11), Vector2(8, 11)]),
	PackedVector2Array([Vector2(2, 14), Vector2(6, 14), Vector2(8, 16), Vector2(6, 19), Vector2(2, 19), Vector2(1, 18), Vector2(2, 14)]),
	PackedVector2Array([Vector2(27, 15), Vector2(29, 17), Vector2(27, 19), Vector2(25, 17), Vector2(27, 15)]),
]
## Maximum separation for each path. Missing entries use the last value.
@export var cliff_heights := PackedFloat32Array([18.0, 28.0, 20.0, 12.0])
## Open-path fade distance in cells: long, short, then unused for closed islands.
@export var cliff_transition_cells := PackedFloat32Array([6.0, 1.0, 0.0, 0.0])
## Radius used to round direction changes while retaining grid-safe unit seams.
@export_range(0.0, 6.0, 0.25) var cliff_corner_smoothing_cells := 1.5
