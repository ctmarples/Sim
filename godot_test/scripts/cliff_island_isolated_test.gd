extends Node2D

const GRASS_SHADER := preload("res://shaders/grass.gdshader")
const CLIFF_SHADER := preload("res://shaders/cliff_face.gdshader")
const CELLS := Vector2i(8, 6)
const CELL_SIZE := 26.0
const LIFT := 48.0
const OVERLAP := 2.5
const ORIGINS := [Vector2(15, 165), Vector2(245, 165), Vector2(475, 165), Vector2(705, 165)]

var curve := PackedVector2Array()
var curve_progress := PackedFloat32Array()
var grass_material: ShaderMaterial
var grass_layers: Array[CanvasItem] = []
var clipped_grid_sections: Array[Array] = []
var cliff_layer: MeshInstance2D
var show_grid := true
var show_grass := true
var show_cliff := true
var show_bottom := true
var show_top := true


func _ready() -> void:
	var background := ColorRect.new()
	background.color = Color("20262b")
	background.size = Vector2(960, 540)
	background.z_index = -20
	add_child(background)
	# Exact third cliff path from TerrainGenerationSettings, translated by (1, 14).
	var controls := PackedVector2Array([
		Vector2(1, 0), Vector2(5, 0), Vector2(7, 2), Vector2(5, 5),
		Vector2(1, 5), Vector2(0, 4), Vector2(1, 0),
	])
	curve = _rounded_closed_curve(controls, 1.5)
	_build_progress()
	grass_material = _create_grass_material()
	_build_terrain_meshes()
	_build_cliff_mesh()
	queue_redraw()


func _input(event: InputEvent) -> void:
	if not (event is InputEventKey and event.pressed and not event.echo):
		return
	if event.physical_keycode == KEY_G:
		show_grid = not show_grid
	elif event.physical_keycode == KEY_H:
		show_grass = not show_grass
		for layer in grass_layers:
			layer.visible = show_grass
	elif event.physical_keycode == KEY_C:
		show_cliff = not show_cliff
		cliff_layer.visible = show_cliff
	elif event.physical_keycode == KEY_B:
		show_bottom = not show_bottom
	elif event.physical_keycode == KEY_Y:
		show_top = not show_top
	else:
		return
	queue_redraw()
	get_viewport().set_input_as_handled()


func _draw() -> void:
	for stage in 4:
		if show_grid:
			_draw_clipped_grid(stage)
		if show_bottom:
			_draw_curve(stage, false, Color(0.15, 0.75, 1.0, 0.95))
		if stage > 0 and show_top:
			_draw_curve(stage, true, Color(1.0, 0.82, 0.18, 0.95))
	var font := ThemeDB.fallback_font
	for stage in 4:
		var names := ["1 Flat island line", "2 Flat + constant lift", "3 Projected + constant", "4 Projected + variable"]
		draw_string(font, Vector2(ORIGINS[stage].x, 48), names[stage], HORIZONTAL_ALIGNMENT_LEFT, 215, 14, Color.WHITE)
	draw_string(font, Vector2(15, 515), "Production island path: G grid  H grass  C cliff  B bottom  Y top", HORIZONTAL_ALIGNMENT_LEFT, 700, 16, Color.WHITE)


func _build_terrain_meshes() -> void:
	clipped_grid_sections.clear()
	clipped_grid_sections.resize(4)
	for stage in 4:
		clipped_grid_sections[stage] = []
	var lower_v := PackedVector2Array()
	var lower_uv := PackedVector2Array()
	var lower_i := PackedInt32Array()
	var raised_v := PackedVector2Array()
	var raised_uv := PackedVector2Array()
	var raised_i := PackedInt32Array()
	for stage in 4:
		for y in CELLS.y:
			for x in CELLS.x:
				var square := PackedVector2Array([Vector2(x, y), Vector2(x + 1, y), Vector2(x + 1, y + 1), Vector2(x, y + 1)])
				if stage == 0:
					_append_polygon(stage, square, false, lower_v, lower_uv, lower_i)
				else:
					for outside in Geometry2D.clip_polygons(square, curve):
						_append_polygon(stage, outside, false, lower_v, lower_uv, lower_i)
					for inside in Geometry2D.intersect_polygons(square, curve):
						_append_polygon(stage, inside, true, raised_v, raised_uv, raised_i)
	_add_mesh("IslandLowerSurface", lower_v, lower_uv, lower_i, -10)
	_add_mesh("IslandRaisedSurface", raised_v, raised_uv, raised_i, 3)


func _append_polygon(stage: int, polygon: PackedVector2Array, raised: bool, vertices: PackedVector2Array, uvs: PackedVector2Array, indices: PackedInt32Array) -> void:
	if polygon.size() < 3:
		return
	# This exact clipped polygon is the single source for the terrain triangles,
	# projected grid, and the top/bottom side of the extrusion.
	clipped_grid_sections[stage].append([polygon.duplicate(), raised])
	var projected := PackedVector2Array()
	for point in polygon:
		projected.append(_project(stage, point, raised))
	var triangles := Geometry2D.triangulate_polygon(projected)
	for triangle_index in range(0, triangles.size(), 3):
		var first := vertices.size()
		for offset in 3:
			var source := triangles[triangle_index + offset]
			vertices.append(projected[source])
			uvs.append((polygon[source] + Vector2(stage * CELLS.x, 0)) * CELL_SIZE)
		indices.append_array(PackedInt32Array([first, first + 1, first + 2]))


func _add_mesh(node_name: String, vertices: PackedVector2Array, uvs: PackedVector2Array, indices: PackedInt32Array, draw_z: int) -> void:
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_TEX_UV] = uvs
	arrays[Mesh.ARRAY_INDEX] = indices
	var array_mesh := ArrayMesh.new()
	array_mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	var instance := MeshInstance2D.new()
	instance.name = node_name
	instance.z_index = draw_z
	instance.mesh = array_mesh
	instance.material = grass_material
	instance.visible = show_grass
	add_child(instance)
	grass_layers.append(instance)


func _build_cliff_mesh() -> void:
	var vertices := PackedVector2Array()
	var uvs := PackedVector2Array()
	var indices := PackedInt32Array()
	var area := 0.0
	for index in curve.size() - 1:
		area += curve[index].cross(curve[index + 1])
	for stage in range(1, 4):
		for index in curve.size() - 1:
			var start := curve[index]
			var finish := curve[index + 1]
			var determinant := (finish - start).x * (-1.0 if area > 0.0 else 1.0)
			if determinant <= 0.0001:
				continue
			var first := vertices.size()
			vertices.append_array(PackedVector2Array([
				_project(stage, start, true) - Vector2(0, OVERLAP),
				_project(stage, finish, true) - Vector2(0, OVERLAP),
				_project(stage, finish, false) + Vector2(0, OVERLAP),
				_project(stage, start, false) + Vector2(0, OVERLAP),
			]))
			uvs.append_array(PackedVector2Array([Vector2(curve_progress[index], 0), Vector2(curve_progress[index + 1], 0), Vector2(curve_progress[index + 1], 1), Vector2(curve_progress[index], 1)]))
			indices.append_array(PackedInt32Array([first, first + 1, first + 2, first, first + 2, first + 3]))
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_TEX_UV] = uvs
	arrays[Mesh.ARRAY_INDEX] = indices
	var array_mesh := ArrayMesh.new()
	array_mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	cliff_layer = MeshInstance2D.new()
	cliff_layer.name = "UnifiedIslandCliff"
	cliff_layer.z_index = 1
	cliff_layer.mesh = array_mesh
	var cliff_material := ShaderMaterial.new()
	cliff_material.shader = CLIFF_SHADER
	cliff_layer.material = cliff_material
	cliff_layer.visible = show_cliff
	add_child(cliff_layer)


func _project(stage: int, point: Vector2, raised: bool) -> Vector2:
	var height := _surface_height(point) if stage >= 2 else 0.0
	if raised:
		height += LIFT * (_progress_at(point) if stage == 3 else 1.0)
	return ORIGINS[stage] + point * CELL_SIZE - Vector2(0, height)


func _surface_height(point: Vector2) -> float:
	return 18.0 + sin(point.x * 0.72) * 12.0 + cos(point.y * 0.83) * 9.0


func _progress_at(point: Vector2) -> float:
	return clampf(point.x / float(CELLS.x), 0.0, 1.0)


func _draw_curve(stage: int, raised: bool, colour: Color) -> void:
	var points := PackedVector2Array()
	for point in curve:
		points.append(_project(stage, point, raised))
	draw_polyline(points, colour, 2.0, true)


func _draw_clipped_grid(stage: int) -> void:
	for section in clipped_grid_sections[stage]:
		var polygon: PackedVector2Array = section[0]
		var raised: bool = section[1]
		var projected := PackedVector2Array()
		for point in polygon:
			projected.append(_project(stage, point, raised))
		projected.append(projected[0])
		draw_polyline(projected, Color(1, 1, 1, 0.45), 1.0, true)


func _rounded_closed_curve(controls: PackedVector2Array, radius: float) -> PackedVector2Array:
	var rounded := PackedVector2Array()
	var count := controls.size() - 1
	for index in count:
		var previous := controls[(index - 1 + count) % count]
		var corner := controls[index]
		var following := controls[(index + 1) % count]
		var incoming := corner - previous
		var outgoing := following - corner
		var trim := minf(radius, minf(incoming.length(), outgoing.length()) * 0.45)
		var entry := corner - incoming.normalized() * trim
		var exit_point := corner + outgoing.normalized() * trim
		for step in 9:
			var t := float(step) / 8.0
			var sample := entry * (1.0 - t) * (1.0 - t) + corner * 2.0 * (1.0 - t) * t + exit_point * t * t
			if rounded.is_empty() or not rounded[-1].is_equal_approx(sample):
				rounded.append(sample)
	rounded.append(rounded[0])
	return rounded


func _build_progress() -> void:
	curve_progress.resize(curve.size())
	var length := 0.0
	for index in range(1, curve.size()):
		length += curve[index - 1].distance_to(curve[index])
		curve_progress[index] = length
	for index in curve_progress.size():
		curve_progress[index] /= length


func _create_grass_material() -> ShaderMaterial:
	var material := ShaderMaterial.new()
	material.shader = GRASS_SHADER
	var size := Vector2i(CELLS.x * 4 + 1, CELLS.y + 1)
	var grass := Image.create(size.x, size.y, false, Image.FORMAT_RGBA8)
	grass.fill(Color(0, 0, 1, 0))
	var empty := Image.create(size.x, size.y, false, Image.FORMAT_RGBA8)
	empty.fill(Color.TRANSPARENT)
	var scalar := Image.create(size.x, size.y, false, Image.FORMAT_RF)
	scalar.fill(Color(0, 0, 0, 1))
	var neutral_relief := Image.create(size.x, size.y, false, Image.FORMAT_RF)
	neutral_relief.fill(Color(1, 0, 0, 1))
	material.set_shader_parameter("terrain_weight_map_a", ImageTexture.create_from_image(grass))
	material.set_shader_parameter("terrain_weight_map_b", ImageTexture.create_from_image(empty))
	material.set_shader_parameter("terrain_weight_map_c", ImageTexture.create_from_image(empty))
	material.set_shader_parameter("height_corner_map", ImageTexture.create_from_image(scalar))
	material.set_shader_parameter("relief_corner_map", ImageTexture.create_from_image(neutral_relief))
	material.set_shader_parameter("cliff_shadow_map", ImageTexture.create_from_image(scalar))
	material.set_shader_parameter("terrain_grid_size", Vector2i(CELLS.x * 4, CELLS.y))
	material.set_shader_parameter("terrain_cell_size", CELL_SIZE)
	material.set_shader_parameter("height_lift_pixels", 0.0)
	material.set_shader_parameter("terrain_max_height", 1.0)
	return material
