extends Node2D

const CELL_SIZE := 28.0
const STAGE_CELLS := Vector2i(5, 5)
const CIRCLE_CENTRE := Vector2(2.5, 2.5)
const CIRCLE_RADIUS := 1.5
const CIRCLE_SEGMENTS := 64
const CLIFF_LIFT := 42.0
const CLIFF_SEAM_OVERLAP := 2.5
const MAP_ORIGIN := Vector2(20, 72)
const ROW_PITCH := 150.0
const PLAYER_SPEED := 3.5
const GRASS_SHADER := preload("res://shaders/grass.gdshader")
const CLIFF_SHADER := preload("res://shaders/cliff_face.gdshader")

var show_grid := true
var show_cliff_shader := true
var show_grass_surface := true
var show_bottom_circle := true
var show_top_circle := true
var cliff_collision_enabled := true
var circle_polygon := PackedVector2Array()
var shallow_s_line := PackedVector2Array()
var right_angle_s_line := PackedVector2Array()
var raised_grid_lines: Array[Line2D] = []
var raised_fill_triangles: Array[CanvasItem] = []
var lower_mesh_vertices := PackedVector2Array()
var lower_mesh_uvs := PackedVector2Array()
var lower_mesh_indices := PackedInt32Array()
var raised_mesh_vertices := PackedVector2Array()
var raised_mesh_uvs := PackedVector2Array()
var raised_mesh_indices := PackedInt32Array()
var player_grid_position := Vector2(1.0, 4.0)
var player_row := 0
var cliff_surface_layer: Node2D
var terrain_surface_layer: Node2D
var raised_surface_layer: Node2D
var terrain_grid_layer: Node2D
var player_marker: Polygon2D
var grass_material: ShaderMaterial


func _ready() -> void:
	for index in CIRCLE_SEGMENTS:
		var angle := TAU * float(index) / float(CIRCLE_SEGMENTS)
		circle_polygon.append(CIRCLE_CENTRE + Vector2(cos(angle), sin(angle)) * CIRCLE_RADIUS)
	shallow_s_line = _make_shallow_s_line()
	right_angle_s_line = _make_right_angle_s_line()
	var background := ColorRect.new()
	background.color = Color("20262b")
	background.size = Vector2(960, 540)
	background.z_index = -20
	add_child(background)
	grass_material = _create_grass_material()
	_build_cliff_surface_layer()
	_build_textured_surface_layers()
	_build_player_marker()
	_update_player_marker()
	queue_redraw()


func _process(delta: float) -> void:
	var direction := Input.get_vector("move_left", "move_right", "move_up", "move_down")
	if not direction.is_zero_approx():
		var proposed_position := player_grid_position + direction * PLAYER_SPEED * delta
		proposed_position.x = clampf(proposed_position.x, 0.0, float(STAGE_CELLS.x * 4))
		proposed_position.y = clampf(proposed_position.y, 0.0, float(STAGE_CELLS.y))
		if not cliff_collision_enabled or not _crosses_cliff_edge(player_grid_position, proposed_position):
			player_grid_position = proposed_position
		_update_player_marker()


func _input(event: InputEvent) -> void:
	if event.is_action_pressed("debug_grid"):
		show_grid = not show_grid
		for grid_line in raised_grid_lines:
			grid_line.visible = show_grid
		queue_redraw()
		get_viewport().set_input_as_handled()
	elif event is InputEventKey and event.pressed and not event.echo and event.physical_keycode == KEY_C:
		show_cliff_shader = not show_cliff_shader
		cliff_surface_layer.visible = show_cliff_shader
		queue_redraw()
		get_viewport().set_input_as_handled()
	elif event is InputEventKey and event.pressed and not event.echo and event.physical_keycode == KEY_B:
		show_bottom_circle = not show_bottom_circle
		queue_redraw()
		get_viewport().set_input_as_handled()
	elif event is InputEventKey and event.pressed and not event.echo and event.physical_keycode == KEY_Y:
		show_top_circle = not show_top_circle
		queue_redraw()
		get_viewport().set_input_as_handled()
	elif event is InputEventKey and event.pressed and not event.echo and event.physical_keycode == KEY_K:
		cliff_collision_enabled = not cliff_collision_enabled
		queue_redraw()
		get_viewport().set_input_as_handled()
	elif event is InputEventKey and event.pressed and not event.echo and event.physical_keycode == KEY_H:
		show_grass_surface = not show_grass_surface
		for triangle in raised_fill_triangles:
			triangle.visible = show_grass_surface
		queue_redraw()
		get_viewport().set_input_as_handled()
	elif event is InputEventKey and event.pressed and not event.echo and event.physical_keycode in [KEY_1, KEY_2, KEY_3]:
		player_row = int(event.physical_keycode - KEY_1)
		_update_player_marker()
		get_viewport().set_input_as_handled()


func _draw() -> void:
	_draw_stage(0, false, false)
	_draw_stage(1, true, false)
	_draw_stage(2, true, true)
	_draw_stage(3, true, true, true)
	_draw_line_row(1, shallow_s_line)
	_draw_line_row(2, right_angle_s_line)
	_draw_string_labels()


func _draw_stage(stage: int, extruded: bool, warped: bool, variable_extrusion: bool = false) -> void:
	var lower_polygons: Array[PackedVector2Array] = []
	var raised_polygons: Array[PackedVector2Array] = []
	for y in STAGE_CELLS.y:
		for x in STAGE_CELLS.x:
			var square := PackedVector2Array([
				Vector2(x, y), Vector2(x + 1, y),
				Vector2(x + 1, y + 1), Vector2(x, y + 1),
			])
			if not extruded:
				lower_polygons.append(square)
				continue
			for outside_polygon in Geometry2D.clip_polygons(square, circle_polygon):
				lower_polygons.append(outside_polygon)
			for inside_polygon in Geometry2D.intersect_polygons(square, circle_polygon):
				raised_polygons.append(inside_polygon)
	# Explicit surface Z order: the complete lower surface is drawn first, then
	# every raised polygon, independent of grid-cell traversal order.
	for polygon in lower_polygons:
		_draw_surface_polygon(stage, polygon, false, warped, variable_extrusion)
	for polygon in raised_polygons:
		_draw_surface_polygon(stage, polygon, true, warped, variable_extrusion)
	if show_bottom_circle:
		_draw_circle_edge(stage, false, warped, variable_extrusion)
	if extruded and show_top_circle:
		_draw_circle_edge(stage, true, warped, variable_extrusion)
	if extruded and cliff_collision_enabled:
		_draw_collision_edge(stage, warped, variable_extrusion)


func _draw_surface_polygon(stage: int, polygon: PackedVector2Array, raised: bool, warped: bool, variable_extrusion: bool) -> void:
	var clean_polygon := _clean_polygon(polygon)
	if clean_polygon.size() < 3:
		return
	var projected := PackedVector2Array()
	for point in clean_polygon:
		projected.append(_project(stage, point, raised, warped, variable_extrusion))
	var triangle_indices := Geometry2D.triangulate_polygon(projected)
	if show_grid:
		var outline := projected.duplicate()
		outline.append(projected[0])
		draw_polyline(outline, Color(1.0, 1.0, 1.0, 0.55), 1.25, true)


func _clean_polygon(polygon: PackedVector2Array) -> PackedVector2Array:
	var result := PackedVector2Array()
	for point in polygon:
		if result.is_empty() or not result[-1].is_equal_approx(point):
			result.append(point)
	if result.size() > 1 and result[0].is_equal_approx(result[-1]):
		result.remove_at(result.size() - 1)
	return result


func _draw_circle_edge(stage: int, raised: bool, warped: bool, variable_extrusion: bool) -> void:
	var projected := PackedVector2Array()
	for point in circle_polygon:
		projected.append(_project(stage, point, raised, warped, variable_extrusion))
	projected.append(projected[0])
	var colour := Color(1.0, 0.82, 0.18, 0.95) if raised else Color(0.15, 0.75, 1.0, 0.95)
	draw_polyline(projected, colour, 2.5, true)


func _draw_collision_edge(stage: int, warped: bool, variable_extrusion: bool) -> void:
	var projected := PackedVector2Array()
	for point in circle_polygon:
		projected.append(_project(stage, point, true, warped, variable_extrusion))
	projected.append(projected[0])
	draw_polyline(projected, Color(1.0, 0.2, 0.65, 0.9), 1.25, true)


func _draw_line_row(row: int, boundary: PackedVector2Array) -> void:
	var raised_region := PackedVector2Array([Vector2(0, 0), Vector2(STAGE_CELLS.x, 0)])
	for index in range(boundary.size() - 1, -1, -1):
		raised_region.append(boundary[index])
	for stage in 4:
		var extruded := stage > 0
		var warped := stage >= 2
		var variable_extrusion := stage == 3
		var lower_polygons: Array[PackedVector2Array] = []
		var raised_polygons: Array[PackedVector2Array] = []
		for y in STAGE_CELLS.y:
			for x in STAGE_CELLS.x:
				var square := PackedVector2Array([Vector2(x, y), Vector2(x + 1, y), Vector2(x + 1, y + 1), Vector2(x, y + 1)])
				if not extruded:
					lower_polygons.append(square)
				else:
					for outside in Geometry2D.clip_polygons(square, raised_region):
						lower_polygons.append(outside)
					for inside in Geometry2D.intersect_polygons(square, raised_region):
						raised_polygons.append(inside)
		for polygon in lower_polygons:
			_draw_row_surface_polygon(stage, row, polygon, false, warped, variable_extrusion)
		for polygon in raised_polygons:
			_draw_row_surface_polygon(stage, row, polygon, true, warped, variable_extrusion)
		if show_bottom_circle:
			_draw_row_boundary(stage, row, boundary, false, warped, variable_extrusion, Color(0.15, 0.75, 1.0, 0.95))
		if extruded and show_top_circle:
			_draw_row_boundary(stage, row, boundary, true, warped, variable_extrusion, Color(1.0, 0.82, 0.18, 0.95))


func _draw_row_surface_polygon(stage: int, row: int, polygon: PackedVector2Array, raised: bool, warped: bool, variable_extrusion: bool) -> void:
	var clean_polygon := _clean_polygon(polygon)
	if clean_polygon.size() < 3:
		return
	var projected := PackedVector2Array()
	for point in clean_polygon:
		projected.append(_project_row(stage, row, point, raised, warped, variable_extrusion))
	if show_grid:
		var outline := projected.duplicate()
		outline.append(projected[0])
		draw_polyline(outline, Color(1.0, 1.0, 1.0, 0.55), 1.0, true)


func _draw_row_boundary(stage: int, row: int, boundary: PackedVector2Array, raised: bool, warped: bool, variable_extrusion: bool, colour: Color) -> void:
	var projected := PackedVector2Array()
	for point in boundary:
		projected.append(_project_row(stage, row, point, raised, warped, variable_extrusion))
	draw_polyline(projected, colour, 2.0, true)


func _project(stage: int, grid_position: Vector2, raised: bool, warped: bool, variable_extrusion: bool) -> Vector2:
	return _project_row(stage, 0, grid_position, raised, warped, variable_extrusion)


func _project_row(stage: int, row: int, grid_position: Vector2, raised: bool, warped: bool, variable_extrusion: bool) -> Vector2:
	var height := _surface_height(grid_position) if warped else 0.0
	if raised:
		height += _extrusion_height(grid_position) if variable_extrusion else CLIFF_LIFT
	var connected_position := grid_position + Vector2(stage * STAGE_CELLS.x, 0)
	return MAP_ORIGIN + Vector2(0, row * ROW_PITCH) + connected_position * CELL_SIZE - Vector2(0.0, height)


func _build_cliff_surface_layer() -> void:
	cliff_surface_layer = Node2D.new()
	cliff_surface_layer.name = "CliffSurfaceShaderLayer"
	cliff_surface_layer.z_index = 1
	cliff_surface_layer.visible = show_cliff_shader
	add_child(cliff_surface_layer)
	var segments: Array[Array] = []
	for stage in range(1, 4):
		var warped := stage >= 2
		var variable_extrusion := stage == 3
		for index in CIRCLE_SEGMENTS:
			var next_index := (index + 1) % CIRCLE_SEGMENTS
			# A circle is wound clockwise in screen coordinates. Its near side is
			# the half whose outward normal points down the screen (positive Y).
			var segment_midpoint := (circle_polygon[index] + circle_polygon[next_index]) * 0.5
			if segment_midpoint.y <= CIRCLE_CENTRE.y:
				continue
			segments.append([stage, 0, circle_polygon[index], circle_polygon[next_index], warped, variable_extrusion])
	for row_data in [[1, shallow_s_line], [2, right_angle_s_line]]:
		var row: int = row_data[0]
		var boundary: PackedVector2Array = row_data[1]
		for stage in range(1, 4):
			var warped := stage >= 2
			var variable_extrusion := stage == 3
			for index in boundary.size() - 1:
				segments.append([stage, row, boundary[index], boundary[index + 1], warped, variable_extrusion])
	var vertices := PackedVector2Array()
	var uvs := PackedVector2Array()
	var indices := PackedInt32Array()
	for segment_index in segments.size():
		var segment := segments[segment_index]
		var stage: int = segment[0]
		var row: int = segment[1]
		var start: Vector2 = segment[2]
		var finish: Vector2 = segment[3]
		var warped: bool = segment[4]
		var variable_extrusion: bool = segment[5]
		var bottom_start := _project_row(stage, row, start, false, warped, variable_extrusion) + Vector2(0, CLIFF_SEAM_OVERLAP)
		var bottom_finish := _project_row(stage, row, finish, false, warped, variable_extrusion) + Vector2(0, CLIFF_SEAM_OVERLAP)
		# Both top values come from the same projection used by the raised terrain.
		# The overlap sits underneath the Z=3 surface and lower terrain and only
		# removes sub-pixel raster cracks; it does not alter the visible cliff edge.
		var top_start := _project_row(stage, row, start, true, warped, variable_extrusion) - Vector2(0, CLIFF_SEAM_OVERLAP)
		var top_finish := _project_row(stage, row, finish, true, warped, variable_extrusion) - Vector2(0, CLIFF_SEAM_OVERLAP)
		var first := vertices.size()
		vertices.append_array(PackedVector2Array([top_start, top_finish, bottom_finish, bottom_start]))
		var u_start := float(segment_index) * CELL_SIZE * 0.25
		var u_finish := u_start + start.distance_to(finish) * CELL_SIZE
		var start_depth := bottom_start.y - top_start.y
		var finish_depth := bottom_finish.y - top_finish.y
		uvs.append_array(PackedVector2Array([Vector2(u_start, 0), Vector2(u_finish, 0), Vector2(u_finish, finish_depth), Vector2(u_start, start_depth)]))
		indices.append_array(PackedInt32Array([first, first + 1, first + 2, first, first + 2, first + 3]))
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_TEX_UV] = uvs
	arrays[Mesh.ARRAY_INDEX] = indices
	var cliff_mesh := ArrayMesh.new()
	cliff_mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	var cliff_faces := MeshInstance2D.new()
	cliff_faces.name = "UnifiedCliffFaces"
	cliff_faces.mesh = cliff_mesh
	var shader_material := ShaderMaterial.new()
	shader_material.shader = CLIFF_SHADER
	cliff_faces.material = shader_material
	cliff_surface_layer.add_child(cliff_faces)


func _create_grass_material() -> ShaderMaterial:
	var material := ShaderMaterial.new()
	material.shader = GRASS_SHADER
	var texture_size := Vector2i(STAGE_CELLS.x * 4 + 1, STAGE_CELLS.y * 3 + 1)
	var weights_a := Image.create(texture_size.x, texture_size.y, false, Image.FORMAT_RGBA8)
	weights_a.fill(Color(0.0, 0.0, 1.0, 0.0))
	var empty_weights := Image.create(texture_size.x, texture_size.y, false, Image.FORMAT_RGBA8)
	empty_weights.fill(Color(0.0, 0.0, 0.0, 0.0))
	var empty_scalar := Image.create(texture_size.x, texture_size.y, false, Image.FORMAT_RF)
	empty_scalar.fill(Color(0.0, 0.0, 0.0, 1.0))
	var neutral_relief := Image.create(texture_size.x, texture_size.y, false, Image.FORMAT_RF)
	neutral_relief.fill(Color(1.0, 0.0, 0.0, 1.0))
	material.set_shader_parameter("terrain_weight_map_a", ImageTexture.create_from_image(weights_a))
	material.set_shader_parameter("terrain_weight_map_b", ImageTexture.create_from_image(empty_weights))
	material.set_shader_parameter("terrain_weight_map_c", ImageTexture.create_from_image(empty_weights))
	material.set_shader_parameter("height_corner_map", ImageTexture.create_from_image(empty_scalar))
	material.set_shader_parameter("relief_corner_map", ImageTexture.create_from_image(neutral_relief))
	material.set_shader_parameter("cliff_shadow_map", ImageTexture.create_from_image(empty_scalar))
	material.set_shader_parameter("terrain_grid_size", Vector2i(STAGE_CELLS.x * 4, STAGE_CELLS.y * 3))
	material.set_shader_parameter("terrain_cell_size", CELL_SIZE)
	material.set_shader_parameter("height_lift_pixels", 0.0)
	material.set_shader_parameter("terrain_max_height", 1.0)
	return material


func _build_textured_surface_layers() -> void:
	terrain_surface_layer = Node2D.new()
	terrain_surface_layer.name = "ProductionGrassLowerSurface"
	terrain_surface_layer.z_index = -10
	add_child(terrain_surface_layer)
	raised_surface_layer = Node2D.new()
	raised_surface_layer.name = "ProductionGrassRaisedSurface"
	raised_surface_layer.z_index = 3
	add_child(raised_surface_layer)
	terrain_grid_layer = Node2D.new()
	terrain_grid_layer.name = "ProjectedSurfaceGrid"
	terrain_grid_layer.z_index = 5
	add_child(terrain_grid_layer)
	for row in 3:
		var boundary := circle_polygon if row == 0 else (shallow_s_line if row == 1 else right_angle_s_line)
		var raised_region := PackedVector2Array()
		if row > 0:
			raised_region = PackedVector2Array([Vector2(0, 0), Vector2(STAGE_CELLS.x, 0)])
			for index in range(boundary.size() - 1, -1, -1):
				raised_region.append(boundary[index])
		for stage in 4:
			var extruded := stage > 0
			for y in STAGE_CELLS.y:
				for x in STAGE_CELLS.x:
					var square := PackedVector2Array([Vector2(x, y), Vector2(x + 1, y), Vector2(x + 1, y + 1), Vector2(x, y + 1)])
					if not extruded:
						_add_textured_polygon(stage, row, square, false)
						continue
					var clip_shape := boundary if row == 0 else raised_region
					for lower in Geometry2D.clip_polygons(square, clip_shape):
						_add_textured_polygon(stage, row, lower, false)
					for upper in Geometry2D.intersect_polygons(square, clip_shape):
						_add_textured_polygon(stage, row, upper, true)
	_add_grass_mesh(terrain_surface_layer, "LowerTerrainMesh", lower_mesh_vertices, lower_mesh_uvs, lower_mesh_indices)
	_add_grass_mesh(raised_surface_layer, "RaisedTerrainMesh", raised_mesh_vertices, raised_mesh_uvs, raised_mesh_indices)


func _add_textured_polygon(stage: int, row: int, polygon: PackedVector2Array, raised: bool) -> void:
	var clean_polygon := _clean_polygon(polygon)
	if clean_polygon.size() < 3:
		return
	var warped := stage >= 2
	var variable_extrusion := stage == 3
	var projected := PackedVector2Array()
	var logical_uvs := PackedVector2Array()
	for point in clean_polygon:
		projected.append(_project_row(stage, row, point, raised, warped, variable_extrusion))
		logical_uvs.append((point + Vector2(stage * STAGE_CELLS.x, row * STAGE_CELLS.y)) * CELL_SIZE)
	var indices := Geometry2D.triangulate_polygon(projected)
	for triangle_index in range(0, indices.size(), 3):
		var a := indices[triangle_index]
		var b := indices[triangle_index + 1]
		var c := indices[triangle_index + 2]
		if raised:
			var first := raised_mesh_vertices.size()
			raised_mesh_vertices.append_array(PackedVector2Array([projected[a], projected[b], projected[c]]))
			raised_mesh_uvs.append_array(PackedVector2Array([logical_uvs[a], logical_uvs[b], logical_uvs[c]]))
			raised_mesh_indices.append_array(PackedInt32Array([first, first + 1, first + 2]))
		else:
			var first := lower_mesh_vertices.size()
			lower_mesh_vertices.append_array(PackedVector2Array([projected[a], projected[b], projected[c]]))
			lower_mesh_uvs.append_array(PackedVector2Array([logical_uvs[a], logical_uvs[b], logical_uvs[c]]))
			lower_mesh_indices.append_array(PackedInt32Array([first, first + 1, first + 2]))
	var grid_line := Line2D.new()
	grid_line.points = projected
	grid_line.closed = true
	grid_line.width = 1.0
	grid_line.default_color = Color(1.0, 1.0, 1.0, 0.55)
	grid_line.antialiased = true
	grid_line.visible = show_grid
	terrain_grid_layer.add_child(grid_line)
	raised_grid_lines.append(grid_line)


func _add_grass_mesh(parent: Node2D, node_name: String, vertices: PackedVector2Array, uvs: PackedVector2Array, indices: PackedInt32Array) -> void:
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_TEX_UV] = uvs
	arrays[Mesh.ARRAY_INDEX] = indices
	var surface_mesh := ArrayMesh.new()
	surface_mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	var surface := MeshInstance2D.new()
	surface.name = node_name
	surface.mesh = surface_mesh
	surface.material = grass_material
	surface.visible = show_grass_surface
	parent.add_child(surface)
	raised_fill_triangles.append(surface)


func _make_shallow_s_line() -> PackedVector2Array:
	var result := PackedVector2Array([Vector2(0, 1.5), Vector2(1.0, 1.5)])
	for index in range(1, 9):
		var t := float(index) / 8.0
		result.append(_quadratic_bezier(Vector2(1.0, 1.5), Vector2(1.5, 1.5), Vector2(1.75, 1.75), t))
	# An exact one-cell 45-degree section between the two easing curves.
	result.append(Vector2(2.75, 2.75))
	for index in range(1, 9):
		var t := float(index) / 8.0
		result.append(_quadratic_bezier(Vector2(2.75, 2.75), Vector2(3.0, 3.0), Vector2(3.5, 3.0), t))
	result.append(Vector2(5.0, 3.0))
	return result


func _quadratic_bezier(start: Vector2, control: Vector2, finish: Vector2, t: float) -> Vector2:
	var inverse := 1.0 - t
	return inverse * inverse * start + 2.0 * inverse * t * control + t * t * finish


func _make_right_angle_s_line() -> PackedVector2Array:
	var result := PackedVector2Array([Vector2(0, 1.0), Vector2(1.5, 1.0)])
	for index in range(1, 9):
		var angle := lerpf(-PI * 0.5, 0.0, float(index) / 8.0)
		result.append(Vector2(1.5, 2.0) + Vector2(cos(angle), sin(angle)))
	result.append(Vector2(2.5, 3.0))
	for index in range(1, 9):
		var angle := lerpf(PI, PI * 0.5, float(index) / 8.0)
		result.append(Vector2(3.5, 3.0) + Vector2(cos(angle), sin(angle)))
	result.append(Vector2(5.0, 4.0))
	return result


func _build_player_marker() -> void:
	player_marker = Polygon2D.new()
	player_marker.name = "MovablePlayerCircle"
	player_marker.z_index = 2
	player_marker.color = Color("ff5577")
	var points := PackedVector2Array()
	for index in 24:
		var angle := TAU * float(index) / 24.0
		points.append(Vector2(cos(angle), sin(angle)) * 9.0)
	player_marker.polygon = points
	add_child(player_marker)


func _update_player_marker() -> void:
	var stage := clampi(int(floor(player_grid_position.x / float(STAGE_CELLS.x))), 0, 3)
	var local_position := player_grid_position - Vector2(stage * STAGE_CELLS.x, 0)
	var warped := stage >= 2
	var raised := false
	if stage > 0:
		if player_row == 0:
			raised = local_position.distance_to(CIRCLE_CENTRE) <= CIRCLE_RADIUS
		else:
			var boundary := shallow_s_line if player_row == 1 else right_angle_s_line
			raised = local_position.y <= _line_height_at_x(boundary, local_position.x)
	var variable_extrusion := stage == 3
	player_marker.position = _project_row(stage, player_row, local_position, raised, warped, variable_extrusion)
	# Raised terrain is the foreground mask at Z 3. A player on its top or
	# below its near edge belongs in front; lower terrain on the far side is behind.
	var behind_raised_surface := player_row == 0 and stage > 0 and not raised and local_position.y < CIRCLE_CENTRE.y
	player_marker.z_index = 2 if behind_raised_surface else 4


func _extrusion_height(grid_position: Vector2) -> float:
	var circle_left := CIRCLE_CENTRE.x - CIRCLE_RADIUS
	var circle_width := CIRCLE_RADIUS * 2.0
	return CLIFF_LIFT * clampf((grid_position.x - circle_left) / circle_width, 0.0, 1.0)


func _crosses_cliff_edge(from_position: Vector2, to_position: Vector2) -> bool:
	var from_stage := clampi(int(floor(from_position.x / float(STAGE_CELLS.x))), 0, 3)
	var to_stage := clampi(int(floor(to_position.x / float(STAGE_CELLS.x))), 0, 3)
	if from_stage != to_stage or from_stage == 0:
		return false
	var stage_offset := Vector2(from_stage * STAGE_CELLS.x, 0)
	var from_local := from_position - stage_offset
	var to_local := to_position - stage_offset
	var from_inside: bool
	var to_inside: bool
	if player_row == 0:
		from_inside = from_local.distance_to(CIRCLE_CENTRE) < CIRCLE_RADIUS
		to_inside = to_local.distance_to(CIRCLE_CENTRE) < CIRCLE_RADIUS
	else:
		var boundary := shallow_s_line if player_row == 1 else right_angle_s_line
		from_inside = from_local.y < _line_height_at_x(boundary, from_local.x)
		to_inside = to_local.y < _line_height_at_x(boundary, to_local.x)
	return from_inside != to_inside


func _line_height_at_x(boundary: PackedVector2Array, x_position: float) -> float:
	for index in boundary.size() - 1:
		var start := boundary[index]
		var finish := boundary[index + 1]
		if x_position >= start.x and x_position <= finish.x:
			var span := finish.x - start.x
			if is_zero_approx(span):
				return maxf(start.y, finish.y)
			return lerpf(start.y, finish.y, (x_position - start.x) / span)
	return boundary[-1].y


func _surface_height(grid_position: Vector2) -> float:
	# Analytic surface sampled at every original or clipped polygon vertex.
	return 24.0 + sin(grid_position.x * 0.9) * 18.0 + cos(grid_position.y * 0.75) * 13.0


func _draw_string_labels() -> void:
	var font := ThemeDB.fallback_font
	draw_string(font, Vector2(20, 48), "1  Flat", HORIZONTAL_ALIGNMENT_LEFT, 140, 14, Color.WHITE)
	draw_string(font, Vector2(160, 48), "2  Constant lift", HORIZONTAL_ALIGNMENT_LEFT, 140, 14, Color.WHITE)
	draw_string(font, Vector2(300, 48), "3  Height surface", HORIZONTAL_ALIGNMENT_LEFT, 140, 14, Color.WHITE)
	draw_string(font, Vector2(440, 48), "4  Variable lift", HORIZONTAL_ALIGNMENT_LEFT, 150, 14, Color.WHITE)
	draw_string(font, Vector2(600, 80), "Row 1: circle", HORIZONTAL_ALIGNMENT_LEFT, 170, 15, Color.WHITE)
	draw_string(font, Vector2(600, 230), "Row 2: shallow S / 45°", HORIZONTAL_ALIGNMENT_LEFT, 220, 15, Color.WHITE)
	draw_string(font, Vector2(600, 380), "Row 3: 90° S bend", HORIZONTAL_ALIGNMENT_LEFT, 220, 15, Color.WHITE)
	draw_string(font, Vector2(600, 455), "Move: WASD/arrows", HORIZONTAL_ALIGNMENT_LEFT, 300, 14, Color(0.9, 0.92, 0.95))
	draw_string(font, Vector2(600, 478), "1/2/3 rows   G grid   H grass", HORIZONTAL_ALIGNMENT_LEFT, 340, 14, Color(0.9, 0.92, 0.95))
	draw_string(font, Vector2(600, 501), "C cliff colour   B/Y curves   K collision", HORIZONTAL_ALIGNMENT_LEFT, 350, 14, Color(0.9, 0.92, 0.95))
	draw_string(font, Vector2(800, 455), "Grass: %s" % ("ON" if show_grass_surface else "OFF"), HORIZONTAL_ALIGNMENT_LEFT, 140, 14, Color("7ee86f") if show_grass_surface else Color("ff7777"))
	draw_string(font, Vector2(800, 478), "Cliff: %s" % ("ON" if show_cliff_shader else "OFF"), HORIZONTAL_ALIGNMENT_LEFT, 140, 14, Color("d89a62") if show_cliff_shader else Color("ff7777"))
