class_name TerrainRenderer
extends MeshInstance2D

@export var generation_settings: TerrainGenerationSettings
var map_data: TerrainMapData
var corner_weight_texture: ImageTexture
var height_texture: ImageTexture
var relief_shade_texture: ImageTexture


func _ready() -> void:
	# Resolution is data-driven. Scaling this node would scale terrain pixels.
	scale = Vector2.ONE
	if generation_settings == null:
		generation_settings = TerrainGenerationSettings.new()
	map_data = MapGenerator.generate(generation_settings)
	_build_map_mesh()
	_upload_corner_weights()
	_upload_heights()
	_upload_relief_shades()


func regenerate() -> void:
	map_data = MapGenerator.generate(generation_settings)
	_build_map_mesh()
	_upload_corner_weights()
	_upload_heights()
	_upload_relief_shades()


func _build_map_mesh() -> void:
	var vertices := PackedVector2Array()
	var indices := PackedInt32Array()
	for vertex_y in map_data.rows + 1:
		for vertex_x in map_data.columns + 1:
			vertices.append(Vector2(vertex_x, vertex_y) * map_data.cell_size)
	for y in map_data.rows:
		for x in map_data.columns:
			var nw := y * (map_data.columns + 1) + x
			var ne := nw + 1
			var sw := nw + map_data.columns + 1
			var se := sw + 1
			indices.append_array(PackedInt32Array([nw, ne, se, nw, se, sw]))
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_INDEX] = indices
	var terrain_mesh := ArrayMesh.new()
	terrain_mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	mesh = terrain_mesh


func get_map_size() -> Vector2:
	return Vector2(map_data.columns * map_data.cell_size, map_data.rows * map_data.cell_size)


func get_map_rect() -> Rect2:
	return Rect2(global_position, get_map_size())


func height_lift_at_global(logical_global_position: Vector2) -> float:
	return map_data.height_at_world(to_local(logical_global_position)) * generation_settings.height_lift_pixels


func project_global_position(logical_global_position: Vector2) -> Vector2:
	return logical_global_position - Vector2(0.0, height_lift_at_global(logical_global_position))


func relief_shade_at_global(logical_global_position: Vector2) -> float:
	return map_data.relief_shade_at_world(to_local(logical_global_position))


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


func _upload_heights() -> void:
	var image := Image.create(map_data.columns + 1, map_data.rows + 1, false, Image.FORMAT_RF)
	var max_height := 0.0
	for vertex_y in map_data.rows + 1:
		for vertex_x in map_data.columns + 1:
			var height := map_data.height_at_corner(Vector2i(vertex_x, vertex_y))
			max_height = maxf(max_height, height)
			image.set_pixel(vertex_x, vertex_y, Color(height, 0.0, 0.0, 1.0))
	height_texture = ImageTexture.create_from_image(image)
	var shader_material := material as ShaderMaterial
	shader_material.set_shader_parameter("height_corner_map", height_texture)
	shader_material.set_shader_parameter("height_lift_pixels", generation_settings.height_lift_pixels)
	shader_material.set_shader_parameter("terrain_max_height", max_height)


func _upload_relief_shades() -> void:
	var image := Image.create(map_data.columns + 1, map_data.rows + 1, false, Image.FORMAT_RF)
	for vertex_y in map_data.rows + 1:
		for vertex_x in map_data.columns + 1:
			image.set_pixel(vertex_x, vertex_y, Color(map_data.relief_shade_at_corner(Vector2i(vertex_x, vertex_y)), 0.0, 0.0, 1.0))
	relief_shade_texture = ImageTexture.create_from_image(image)
	var shader_material := material as ShaderMaterial
	shader_material.set_shader_parameter("relief_corner_map", relief_shade_texture)


func _corner_touches_soil(vertex: Vector2i) -> bool:
	for offset in [Vector2i(-1, -1), Vector2i(0, -1), Vector2i(-1, 0), Vector2i.ZERO]:
		if map_data.terrain_at(vertex + offset) == TerrainMapData.Terrain.SOIL:
			return true
	return false
