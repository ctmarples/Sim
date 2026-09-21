class_name TerrainMapData
extends Resource

enum Terrain { GRASS, SOIL }

var columns: int
var rows: int
var cell_size: float
var cells := PackedInt32Array()
var corner_heights := PackedFloat32Array()
var height_peak := 0.0


func configure(new_columns: int, new_rows: int, new_cell_size: float) -> void:
	columns = new_columns
	rows = new_rows
	cell_size = new_cell_size
	cells.resize(columns * rows)
	cells.fill(Terrain.GRASS)
	corner_heights.resize((columns + 1) * (rows + 1))
	corner_heights.fill(0.0)
	height_peak = 0.0


func contains(cell: Vector2i) -> bool:
	return cell.x >= 0 and cell.y >= 0 and cell.x < columns and cell.y < rows


func terrain_at(cell: Vector2i) -> Terrain:
	if not contains(cell):
		return Terrain.GRASS
	return cells[cell.y * columns + cell.x] as Terrain


func set_terrain(cell: Vector2i, terrain: Terrain) -> void:
	if contains(cell):
		cells[cell.y * columns + cell.x] = terrain


func height_at_corner(vertex: Vector2i) -> float:
	var safe := Vector2i(clampi(vertex.x, 0, columns), clampi(vertex.y, 0, rows))
	return corner_heights[safe.y * (columns + 1) + safe.x]


func set_corner_height(vertex: Vector2i, height: float) -> void:
	if vertex.x >= 0 and vertex.y >= 0 and vertex.x <= columns and vertex.y <= rows:
		var safe_height := maxf(0.0, height)
		corner_heights[vertex.y * (columns + 1) + vertex.x] = safe_height
		height_peak = maxf(height_peak, safe_height)


func recalculate_height_peak() -> void:
	height_peak = 0.0
	for height in corner_heights:
		height_peak = maxf(height_peak, height)


func height_at_world(world_position: Vector2) -> float:
	var grid_position := world_position / cell_size
	var cell := Vector2i(floori(grid_position.x), floori(grid_position.y))
	cell.x = clampi(cell.x, 0, columns - 1)
	cell.y = clampi(cell.y, 0, rows - 1)
	var fraction := Vector2(clampf(grid_position.x - cell.x, 0.0, 1.0), clampf(grid_position.y - cell.y, 0.0, 1.0))
	var top := lerpf(height_at_corner(cell), height_at_corner(cell + Vector2i.RIGHT), fraction.x)
	var bottom := lerpf(height_at_corner(cell + Vector2i.DOWN), height_at_corner(cell + Vector2i.ONE), fraction.x)
	return lerpf(top, bottom, fraction.y)


func relief_shade_at_world(world_position: Vector2) -> float:
	var grid_position := world_position / cell_size
	var cell := Vector2i(clampi(floori(grid_position.x), 0, columns - 1), clampi(floori(grid_position.y), 0, rows - 1))
	var fraction := Vector2(clampf(grid_position.x - cell.x, 0.0, 1.0), clampf(grid_position.y - cell.y, 0.0, 1.0))
	var top := lerpf(relief_shade_at_corner(cell), relief_shade_at_corner(cell + Vector2i.RIGHT), fraction.x)
	var bottom := lerpf(relief_shade_at_corner(cell + Vector2i.DOWN), relief_shade_at_corner(cell + Vector2i.ONE), fraction.x)
	return lerpf(top, bottom, fraction.y)


func relief_shade_at_corner(vertex: Vector2i) -> float:
	var safe := Vector2i(clampi(vertex.x, 0, columns), clampi(vertex.y, 0, rows))
	var height := height_at_corner(safe)
	var east := height_at_corner(safe + Vector2i.RIGHT) if safe.x < columns else height
	var west := height_at_corner(safe + Vector2i.LEFT) if safe.x > 0 else height
	var south := height_at_corner(safe + Vector2i.DOWN) if safe.y < rows else height
	var north := height_at_corner(safe + Vector2i.UP) if safe.y > 0 else height
	var gx := east - height if safe.x == 0 else (height - west if safe.x == columns else (east - west) * 0.5)
	var gy := south - height if safe.y == 0 else (height - north if safe.y == rows else (south - north) * 0.5)
	var lit := (gx - gy * 0.35) / 1.35 / maxf(8.0, height_peak * 0.15)
	var response := lit * 0.28 * 4.0
	if response < 0.0:
		response *= 1.5
	return clampf(1.0 + response, 0.55, 1.10)
