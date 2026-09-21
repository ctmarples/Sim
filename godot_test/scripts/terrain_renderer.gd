class_name TerrainRenderer
extends Polygon2D

@export var generation_settings: TerrainGenerationSettings
var map_data: TerrainMapData
var corner_weight_texture: ImageTexture


func _ready() -> void:
	# Resolution is data-driven. Scaling this node would scale terrain pixels.
	scale = Vector2.ONE
	if generation_settings == null:
		generation_settings = TerrainGenerationSettings.new()
	map_data = MapGenerator.generate(generation_settings)
	_build_map_polygon()
	_upload_corner_weights()


func regenerate() -> void:
	map_data = MapGenerator.generate(generation_settings)
	_upload_corner_weights()


func _build_map_polygon() -> void:
	var size := get_map_size()
	polygon = PackedVector2Array([Vector2.ZERO, Vector2(size.x, 0), size, Vector2(0, size.y)])


func get_map_size() -> Vector2:
	return Vector2(map_data.columns * map_data.cell_size, map_data.rows * map_data.cell_size)


func get_map_rect() -> Rect2:
	return Rect2(global_position, get_map_size())


func _upload_corner_weights() -> void:
	var image := Image.create(map_data.columns + 1, map_data.rows + 1, false, Image.FORMAT_R8)
	for vertex_y in map_data.rows + 1:
		for vertex_x in map_data.columns + 1:
			var is_soil := _corner_touches_soil(Vector2i(vertex_x, vertex_y))
			image.set_pixel(vertex_x, vertex_y, Color(1.0 if is_soil else 0.0, 0.0, 0.0))
	corner_weight_texture = ImageTexture.create_from_image(image)
	var shader_material := material as ShaderMaterial
	shader_material.set_shader_parameter("soil_corner_map", corner_weight_texture)
	shader_material.set_shader_parameter("terrain_grid_size", Vector2i(map_data.columns, map_data.rows))
	shader_material.set_shader_parameter("terrain_cell_size", map_data.cell_size)


func _corner_touches_soil(vertex: Vector2i) -> bool:
	for offset in [Vector2i(-1, -1), Vector2i(0, -1), Vector2i(-1, 0), Vector2i.ZERO]:
		if map_data.terrain_at(vertex + offset) == TerrainMapData.Terrain.SOIL:
			return true
	return false
