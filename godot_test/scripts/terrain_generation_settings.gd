class_name TerrainGenerationSettings
extends Resource

@export_category("Map")
@export_range(2, 256, 1) var columns := 30
@export_range(2, 256, 1) var rows := 20
# One logical game tile is 40×40 render pixels, matching CELL_SIZE in Pygame.
@export_range(8.0, 256.0, 1.0) var cell_size := 40.0

@export_category("Distribution")
@export var seed := 3896
@export_range(0.01, 1.0, 0.01) var frequency := 0.10
@export_range(-1.0, 1.0, 0.01) var soil_threshold := -0.08
@export_range(1, 8, 1) var fractal_octaves := 3
@export_range(0, 4, 1) var grass_border_cells := 1
