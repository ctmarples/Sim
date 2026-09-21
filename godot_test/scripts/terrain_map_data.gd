class_name TerrainMapData
extends Resource

enum Terrain { GRASS, SOIL }

var columns: int
var rows: int
var cell_size: float
var cells := PackedInt32Array()


func configure(new_columns: int, new_rows: int, new_cell_size: float) -> void:
	columns = new_columns
	rows = new_rows
	cell_size = new_cell_size
	cells.resize(columns * rows)
	cells.fill(Terrain.GRASS)


func contains(cell: Vector2i) -> bool:
	return cell.x >= 0 and cell.y >= 0 and cell.x < columns and cell.y < rows


func terrain_at(cell: Vector2i) -> Terrain:
	if not contains(cell):
		return Terrain.GRASS
	return cells[cell.y * columns + cell.x] as Terrain


func set_terrain(cell: Vector2i, terrain: Terrain) -> void:
	if contains(cell):
		cells[cell.y * columns + cell.x] = terrain
