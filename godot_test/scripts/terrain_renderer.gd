class_name TerrainRenderer
extends MeshInstance2D

const CLIFF_FACE_SHADER := preload("res://shaders/cliff_face.gdshader")
const CLIFF_SEAM_OVERLAP_PIXELS := 2.5

@export var generation_settings: TerrainGenerationSettings
var map_data: TerrainMapData
var terrain_weight_texture_a: ImageTexture
var terrain_weight_texture_b: ImageTexture
var terrain_weight_texture_c: ImageTexture
var height_texture: ImageTexture
var relief_shade_texture: ImageTexture
var cliff_shadow_texture: ImageTexture
var cliff_curves: Array[PackedVector2Array] = []
var cliff_curve_progresses: Array[PackedFloat32Array] = []
var cliff_curve_lengths := PackedFloat32Array()
var cliff_cell_candidates: Dictionary = {}
var cliff_vertex_offset_cache: Dictionary = {}
var terrain_height_cache: Dictionary = {}
var cliff_edge_bottoms: Array[PackedVector2Array] = []
var cliff_edge_tops: Array[PackedVector2Array] = []
var debug_base_surface_polygons: Array[PackedVector2Array] = []
var debug_cliff_bottom_polygons: Array[PackedVector2Array] = []
var debug_cliff_top_polygons: Array[PackedVector2Array] = []


func _ready() -> void:
	# Resolution is data-driven. Scaling this node would scale terrain pixels.
	scale = Vector2.ONE
	if generation_settings == null:
		generation_settings = TerrainGenerationSettings.new()
	map_data = MapGenerator.generate(generation_settings)
	_build_cliff_curve()
	_build_cliff_edge_geometry()
	_build_map_mesh()
	_upload_terrain_cells()
	_upload_heights()
	_upload_relief_shades()
	_upload_cliff_shadows()
	_build_cliff_geometry()


func regenerate() -> void:
	map_data = MapGenerator.generate(generation_settings)
	_build_cliff_curve()
	_build_cliff_edge_geometry()
	_build_map_mesh()
	_upload_terrain_cells()
	_upload_heights()
	_upload_relief_shades()
	_upload_cliff_shadows()
	_build_cliff_geometry()


func _build_map_mesh() -> void:
	var old_occluder := get_node_or_null("CliffFarSurface")
	if old_occluder:
		old_occluder.free()
	var old_foreground := get_node_or_null("CliffRaisedForeground")
	if old_foreground:
		old_foreground.free()
	var vertices := PackedVector2Array()
	var uvs := PackedVector2Array()
	var indices := PackedInt32Array()
	var foreground_vertices := PackedVector2Array()
	var foreground_uvs := PackedVector2Array()
	var foreground_indices := PackedInt32Array()
	debug_base_surface_polygons.clear()
	debug_cliff_bottom_polygons.clear()
	debug_cliff_top_polygons.clear()
	terrain_height_cache.clear()
	for cell_y in map_data.rows:
		for cell_x in map_data.columns:
			var origin := Vector2(cell_x, cell_y)
			var corners: Array = [origin, origin + Vector2.RIGHT, origin + Vector2.ONE, origin + Vector2.DOWN]
			var crossing_cliff := _crossing_cliff_for_polygon(corners)
			if crossing_cliff >= 0:
				if _is_closed_cliff(crossing_cliff):
					var square := PackedVector2Array(corners)
					for lower_polygon in Geometry2D.clip_polygons(square, cliff_curves[crossing_cliff]):
						_append_terrain_polygon(lower_polygon, crossing_cliff, false, vertices, uvs, indices)
						debug_cliff_bottom_polygons.append(_project_clipped_polygon(lower_polygon, crossing_cliff, false))
					for upper_polygon in Geometry2D.intersect_polygons(square, cliff_curves[crossing_cliff]):
						_append_terrain_polygon(upper_polygon, crossing_cliff, true, vertices, uvs, indices)
						var occluding_cliff := _far_occluder_cliff_for_polygon(upper_polygon)
						if occluding_cliff >= 0:
							_append_terrain_polygon(upper_polygon, occluding_cliff, true, foreground_vertices, foreground_uvs, foreground_indices)
						debug_cliff_top_polygons.append(_project_clipped_polygon(upper_polygon, crossing_cliff, true))
					continue
				var seam := _cliff_intersections_for_polygon(corners, crossing_cliff)
				var lower_polygon := _clip_polygon_to_cliff_side(corners, crossing_cliff, false, seam)
				var upper_polygon := _clip_polygon_to_cliff_side(corners, crossing_cliff, true, seam)
				_append_terrain_polygon(lower_polygon, crossing_cliff, false, vertices, uvs, indices)
				_append_terrain_polygon(upper_polygon, crossing_cliff, true, vertices, uvs, indices)
				var occluding_cliff := _far_occluder_cliff_for_polygon(upper_polygon)
				if occluding_cliff >= 0:
					_append_terrain_polygon(upper_polygon, occluding_cliff, true, foreground_vertices, foreground_uvs, foreground_indices)
				debug_cliff_bottom_polygons.append(_project_clipped_polygon(lower_polygon, crossing_cliff, false))
				debug_cliff_top_polygons.append(_project_clipped_polygon(upper_polygon, crossing_cliff, true))
				continue
			var projected_square := PackedVector2Array()
			for grid_position: Vector2 in corners:
				var logical := grid_position * map_data.cell_size
				var height := _terrain_height_at_grid_position(grid_position)
				projected_square.append(logical - Vector2(0.0, height * generation_settings.height_lift_pixels))
			debug_base_surface_polygons.append(projected_square)
			# Only duplicate terrain that can actually occlude an actor across a
			# far-side rim. Duplicating/scanning every elevated interior cell caused
			# the large generation-time regression on full maps.
			var foreground_cliff := _far_occluder_cliff_for_polygon(PackedVector2Array(corners))
			if foreground_cliff >= 0:
				_append_terrain_polygon(PackedVector2Array(corners), foreground_cliff, true, foreground_vertices, foreground_uvs, foreground_indices)
			for triangle in [[0, 1, 2], [0, 2, 3]]:
				var first := vertices.size()
				for corner_index in triangle:
					var grid_position: Vector2 = corners[corner_index]
					var logical := grid_position * map_data.cell_size
					var height := _terrain_height_at_grid_position(grid_position)
					vertices.append(logical - Vector2(0.0, height * generation_settings.height_lift_pixels))
					uvs.append(logical)
				indices.append_array(PackedInt32Array([first, first + 1, first + 2]))
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_TEX_UV] = uvs
	arrays[Mesh.ARRAY_INDEX] = indices
	var terrain_mesh := ArrayMesh.new()
	terrain_mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	mesh = terrain_mesh
	if not foreground_vertices.is_empty():
		var foreground_arrays := []
		foreground_arrays.resize(Mesh.ARRAY_MAX)
		foreground_arrays[Mesh.ARRAY_VERTEX] = foreground_vertices
		foreground_arrays[Mesh.ARRAY_TEX_UV] = foreground_uvs
		foreground_arrays[Mesh.ARRAY_INDEX] = foreground_indices
		var foreground_mesh := ArrayMesh.new()
		foreground_mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, foreground_arrays)
		var foreground := MeshInstance2D.new()
		foreground.name = "CliffRaisedForeground"
		foreground.z_index = 12
		foreground.mesh = foreground_mesh
		foreground.material = material
		add_child(foreground)


func _terrain_height_at_grid_position(grid_position: Vector2) -> float:
	if terrain_height_cache.has(grid_position):
		return terrain_height_cache[grid_position]
	var height := map_data.height_at_world(grid_position * map_data.cell_size)
	var cliff_height := 0.0
	for curve_index in cliff_curves.size():
		var elevated := _point_inside_cliff(grid_position, curve_index) if _is_closed_cliff(curve_index) else _nearest_cliff_point(grid_position, curve_index).w < 0.0
		if elevated:
			var nearest := _nearest_cliff_point(grid_position, curve_index)
			cliff_height = maxf(cliff_height, _cliff_separation_at_progress(curve_index, nearest.z))
	var result := height + cliff_height
	terrain_height_cache[grid_position] = result
	return result


func _elevated_cliff_at(grid_position: Vector2) -> int:
	var selected := -1
	var selected_height := 0.0
	for curve_index in cliff_curves.size():
		var elevated := _point_inside_cliff(grid_position, curve_index) if _is_closed_cliff(curve_index) else _nearest_cliff_point(grid_position, curve_index).w < 0.0
		if not elevated:
			continue
		var nearest := _nearest_cliff_point(grid_position, curve_index)
		var height := _cliff_separation_at_progress(curve_index, nearest.z)
		if height > selected_height:
			selected = curve_index
			selected_height = height
	return selected


func _build_map_mesh_legacy() -> void:
	var old_occluder := get_node_or_null("CliffFarSurface")
	if old_occluder:
		old_occluder.free()
	var vertices := PackedVector2Array()
	var uvs := PackedVector2Array()
	var indices := PackedInt32Array()
	var occluder_vertices := PackedVector2Array()
	var occluder_uvs := PackedVector2Array()
	var occluder_indices := PackedInt32Array()
	for cell_y in map_data.rows:
		for cell_x in map_data.columns:
			var cell := Vector2i(cell_x, cell_y)
			var grid_step := 1.0
			for _single_y in 1:
				for _single_x in 1:
					var grid_origin := Vector2(cell)
					var triangle_corners := _triangle_corners_for_region(grid_origin, grid_step)
					var logical_corners := [
						grid_origin * map_data.cell_size,
						(grid_origin + Vector2.RIGHT * grid_step) * map_data.cell_size,
						(grid_origin + Vector2.ONE * grid_step) * map_data.cell_size,
						(grid_origin + Vector2.DOWN * grid_step) * map_data.cell_size,
					]
					var corner_ids := [
						grid_origin,
						grid_origin + Vector2.RIGHT * grid_step,
						grid_origin + Vector2.ONE * grid_step,
						grid_origin + Vector2.DOWN * grid_step,
					]
					var crossing_cliff := _crossing_cliff_for_polygon(corner_ids)
					if crossing_cliff >= 0:
						var seam := _cliff_intersections_for_polygon(corner_ids, crossing_cliff)
						var lower_polygon := _clip_polygon_to_cliff_side(corner_ids, crossing_cliff, false, seam)
						var upper_polygon := _clip_polygon_to_cliff_side(corner_ids, crossing_cliff, true, seam)
						_append_terrain_polygon(lower_polygon, crossing_cliff, false, vertices, uvs, indices)
						_append_terrain_polygon(upper_polygon, crossing_cliff, true, vertices, uvs, indices)
						var occluding_cliff := _far_occluder_cliff_for_polygon(upper_polygon)
						if occluding_cliff >= 0:
							_append_terrain_polygon(upper_polygon, occluding_cliff, true, occluder_vertices, occluder_uvs, occluder_indices)
						continue
					for triangle in triangle_corners:
						var owner_position := Vector2.ZERO
						for corner_index in triangle:
							owner_position += corner_ids[corner_index]
						owner_position /= 3.0
						var triangle_polygon := PackedVector2Array([
							corner_ids[triangle[0]], corner_ids[triangle[1]], corner_ids[triangle[2]],
						])
						var occluding_cliff := _far_occluder_cliff_for_polygon(triangle_polygon)
						if occluding_cliff >= 0:
							_append_terrain_polygon(triangle_polygon, occluding_cliff, true, occluder_vertices, occluder_uvs, occluder_indices)
						for corner_index in triangle:
							var height := map_data.height_at_world(corner_ids[corner_index] * map_data.cell_size) + _cliff_offset_for_vertex(owner_position, corner_ids[corner_index])
							var logical: Vector2 = logical_corners[corner_index]
							indices.append(vertices.size())
							vertices.append(logical - Vector2(0.0, height * generation_settings.height_lift_pixels))
							uvs.append(logical)
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_TEX_UV] = uvs
	arrays[Mesh.ARRAY_INDEX] = indices
	var terrain_mesh := ArrayMesh.new()
	terrain_mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	mesh = terrain_mesh
	if not occluder_vertices.is_empty():
		var occluder_arrays := []
		occluder_arrays.resize(Mesh.ARRAY_MAX)
		occluder_arrays[Mesh.ARRAY_VERTEX] = occluder_vertices
		occluder_arrays[Mesh.ARRAY_TEX_UV] = occluder_uvs
		occluder_arrays[Mesh.ARRAY_INDEX] = occluder_indices
		var occluder_mesh := ArrayMesh.new()
		occluder_mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, occluder_arrays)
		var occluder := MeshInstance2D.new()
		occluder.name = "CliffFarSurface"
		occluder.z_index = 12
		occluder.mesh = occluder_mesh
		occluder.material = material
		add_child(occluder)


func _signed_distance_to_cliff(grid_position: Vector2, curve_index: int) -> float:
	var nearest := _nearest_cliff_point(grid_position, curve_index)
	var distance := grid_position.distance_to(Vector2(nearest.x, nearest.y))
	var elevated := _point_inside_cliff(grid_position, curve_index) if _is_closed_cliff(curve_index) else nearest.w < 0.0
	return -distance if elevated else distance


func _crossing_cliff_for_polygon(polygon: Array) -> int:
	var cell := Vector2i(floori(polygon[0].x), floori(polygon[0].y))
	var candidates: Array = cliff_cell_candidates.get(cell, [])
	for curve_index: int in candidates:
		if not _curve_intersects_cell(curve_index, cell):
			continue
		if _is_closed_cliff(curve_index):
			return curve_index
		var has_lower := false
		var has_upper := false
		for point: Vector2 in polygon:
			var signed_distance := _signed_distance_to_cliff(point, curve_index)
			has_upper = has_upper or signed_distance < -0.00001
			has_lower = has_lower or signed_distance > 0.00001
		if has_lower and has_upper:
			return curve_index
	return -1


func _curve_intersects_cell(curve_index: int, cell: Vector2i) -> bool:
	var minimum := Vector2(cell)
	var maximum := minimum + Vector2.ONE
	var top_left := minimum
	var top_right := Vector2(maximum.x, minimum.y)
	var bottom_right := maximum
	var bottom_left := Vector2(minimum.x, maximum.y)
	var curve := cliff_curves[curve_index]
	for index in range(curve.size() - 1):
		var start := curve[index]
		var finish := curve[index + 1]
		if (start.x >= minimum.x and start.x <= maximum.x and start.y >= minimum.y and start.y <= maximum.y) \
				or (finish.x >= minimum.x and finish.x <= maximum.x and finish.y >= minimum.y and finish.y <= maximum.y):
			return true
		if Geometry2D.segment_intersects_segment(start, finish, top_left, top_right) != null \
				or Geometry2D.segment_intersects_segment(start, finish, top_right, bottom_right) != null \
				or Geometry2D.segment_intersects_segment(start, finish, bottom_right, bottom_left) != null \
				or Geometry2D.segment_intersects_segment(start, finish, bottom_left, top_left) != null:
			return true
	return false


func _clip_polygon_to_cliff_side(polygon: Array, curve_index: int, elevated_side: bool, seam := PackedVector2Array()) -> PackedVector2Array:
	var result := PackedVector2Array()
	var previous: Vector2 = polygon[polygon.size() - 1]
	var previous_distance := _signed_distance_to_cliff(previous, curve_index)
	var previous_inside := previous_distance <= 0.00001 if elevated_side else previous_distance >= -0.00001
	for current: Vector2 in polygon:
		var current_distance := _signed_distance_to_cliff(current, curve_index)
		var current_inside := current_distance <= 0.00001 if elevated_side else current_distance >= -0.00001
		if current_inside != previous_inside:
			var denominator := previous_distance - current_distance
			var amount := previous_distance / denominator if absf(denominator) > 0.000001 else 0.5
			var estimated := previous.lerp(current, clampf(amount, 0.0, 1.0))
			result.append(_exact_curve_edge_intersection(previous, current, curve_index, estimated))
		if current_inside:
			result.append(current)
		previous = current
		previous_distance = current_distance
		previous_inside = current_inside
	if seam.size() == 2:
		return _insert_curve_samples_on_seam(result, seam[0], seam[1], curve_index)
	return result


func _insert_curve_samples_on_seam(polygon: PackedVector2Array, first_seam: Vector2, second_seam: Vector2, curve_index: int) -> PackedVector2Array:
	if polygon.size() < 3:
		return polygon
	var first_index := -1
	var second_index := -1
	for index in polygon.size():
		if polygon[index].is_equal_approx(first_seam):
			first_index = index
		if polygon[index].is_equal_approx(second_seam):
			second_index = index
	if first_index < 0 or second_index < 0:
		return polygon
	var edge_start := -1
	var edge_finish := -1
	if (first_index + 1) % polygon.size() == second_index:
		edge_start = first_index
		edge_finish = second_index
	elif (second_index + 1) % polygon.size() == first_index:
		edge_start = second_index
		edge_finish = first_index
	else:
		return polygon
	var start_point := polygon[edge_start]
	var finish_point := polygon[edge_finish]
	var start_progress := _nearest_cliff_point(start_point, curve_index).z
	var finish_progress := _nearest_cliff_point(finish_point, curve_index).z
	var intermediate := PackedVector2Array()
	var curve := cliff_curves[curve_index]
	var progress := cliff_curve_progresses[curve_index]
	var minimum_progress := minf(start_progress, finish_progress)
	var maximum_progress := maxf(start_progress, finish_progress)
	for index in curve.size():
		if progress[index] > minimum_progress + 0.000001 and progress[index] < maximum_progress - 0.000001:
			intermediate.append(curve[index])
	if start_progress > finish_progress:
		intermediate.reverse()
	var result := PackedVector2Array()
	for index in polygon.size():
		result.append(polygon[index])
		if index == edge_start:
			result.append_array(intermediate)
	return result


func _curve_section_between(start_point: Vector2, finish_point: Vector2, curve_index: int) -> PackedVector2Array:
	var start_progress := _nearest_cliff_point(start_point, curve_index).z
	var finish_progress := _nearest_cliff_point(finish_point, curve_index).z
	var section := PackedVector2Array([start_point])
	var middle := PackedVector2Array()
	var curve := cliff_curves[curve_index]
	var progress := cliff_curve_progresses[curve_index]
	var minimum_progress := minf(start_progress, finish_progress)
	var maximum_progress := maxf(start_progress, finish_progress)
	for index in curve.size():
		if progress[index] > minimum_progress + 0.000001 and progress[index] < maximum_progress - 0.000001:
			middle.append(curve[index])
	if start_progress > finish_progress:
		middle.reverse()
	section.append_array(middle)
	section.append(finish_point)
	return section


func _cliff_intersections_for_polygon(polygon: Array, curve_index: int) -> PackedVector2Array:
	var result := PackedVector2Array()
	var previous: Vector2 = polygon[polygon.size() - 1]
	var previous_distance := _signed_distance_to_cliff(previous, curve_index)
	for current: Vector2 in polygon:
		var current_distance := _signed_distance_to_cliff(current, curve_index)
		if (previous_distance < 0.0 and current_distance > 0.0) or (previous_distance > 0.0 and current_distance < 0.0):
			var amount := previous_distance / (previous_distance - current_distance)
			var estimated := previous.lerp(current, clampf(amount, 0.0, 1.0))
			result.append(_exact_curve_edge_intersection(previous, current, curve_index, estimated))
		previous = current
		previous_distance = current_distance
	return result


func _exact_curve_edge_intersection(edge_start: Vector2, edge_finish: Vector2, curve_index: int, fallback: Vector2) -> Vector2:
	var best := fallback
	var best_distance_squared := INF
	var curve := cliff_curves[curve_index]
	for index in range(curve.size() - 1):
		var intersection = Geometry2D.segment_intersects_segment(edge_start, edge_finish, curve[index], curve[index + 1])
		if intersection == null:
			continue
		var point: Vector2 = intersection
		var distance_squared := point.distance_squared_to(fallback)
		if distance_squared < best_distance_squared:
			best = point
			best_distance_squared = distance_squared
	return best


func _append_terrain_polygon(polygon: PackedVector2Array, curve_index: int, elevated_side: bool, vertices: PackedVector2Array, uvs: PackedVector2Array, indices: PackedInt32Array) -> void:
	if polygon.size() < 3:
		return
	var first := vertices.size()
	for grid_position in polygon:
		var logical := grid_position * map_data.cell_size
		vertices.append(_project_cliff_surface_point(grid_position, curve_index, elevated_side))
		uvs.append(logical)
	var triangulation := Geometry2D.triangulate_polygon(polygon)
	for local_index in triangulation:
		indices.append(first + local_index)


func _clipped_terrain_height(grid_position: Vector2, forced_curve_index: int, elevated_side: bool) -> float:
	var height := map_data.height_at_world(grid_position * map_data.cell_size)
	var cliff_height := 0.0
	for curve_index in cliff_curves.size():
		var elevated := elevated_side if curve_index == forced_curve_index else _signed_distance_to_cliff(grid_position, curve_index) < 0.0
		if elevated:
			var nearest := _nearest_cliff_point(grid_position, curve_index)
			cliff_height = maxf(cliff_height, _cliff_separation_at_progress(curve_index, nearest.z))
	return height + cliff_height


func _project_cliff_surface_point(grid_position: Vector2, forced_curve_index: int, elevated_side: bool) -> Vector2:
	# Projection is deliberately ordered as validated by the isolated test:
	# start from the flat logical grid, add the normal height projection, then
	# augment only the selected side with the configured cliff separation.
	var logical := grid_position * map_data.cell_size
	var projected_height := _clipped_terrain_height(grid_position, forced_curve_index, elevated_side)
	return logical - Vector2(0.0, projected_height * generation_settings.height_lift_pixels)


func _project_clipped_polygon(polygon: PackedVector2Array, curve_index: int, elevated_side: bool) -> PackedVector2Array:
	var projected := PackedVector2Array()
	for grid_position in polygon:
		projected.append(_project_cliff_surface_point(grid_position, curve_index, elevated_side))
	return projected


## Match a cell's triangle seam to any 45-degree cliff segment crossing it.
## Corner order is top-left, top-right, bottom-right, bottom-left.
func _triangle_corners_for_cell(cell: Vector2i) -> Array:
	return _triangle_corners_for_region(Vector2(cell), 1.0)


func _triangle_corners_for_region(top_left: Vector2, grid_step: float) -> Array:
	var top_right := top_left + Vector2.RIGHT * grid_step
	var bottom_left := top_left + Vector2.DOWN * grid_step
	for curve in cliff_curves:
		for index in range(curve.size() - 1):
			var start: Vector2 = curve[index]
			var finish: Vector2 = curve[index + 1]
			if (start.is_equal_approx(top_right) and finish.is_equal_approx(bottom_left)) \
					or (start.is_equal_approx(bottom_left) and finish.is_equal_approx(top_right)):
				return [[0, 1, 3], [1, 2, 3]]
	return [[0, 1, 2], [0, 2, 3]]


func _build_cliff_curve() -> void:
	cliff_curves.clear()
	cliff_curve_progresses.clear()
	cliff_curve_lengths.clear()
	cliff_cell_candidates.clear()
	cliff_vertex_offset_cache.clear()
	if not generation_settings.cliff_enabled:
		return
	for source_path in generation_settings.cliff_paths:
		if source_path.size() < 2:
			continue
		var controls := PackedVector2Array()
		for point in source_path:
			controls.append(Vector2(
				clampf(roundf(point.x), 0.0, float(map_data.columns)),
				clampf(roundf(point.y), 0.0, float(map_data.rows))
			))
		var rounded_controls := _rounded_cliff_controls(controls)
		var curve := PackedVector2Array()
		for control_index in range(rounded_controls.size() - 1):
			var start: Vector2 = rounded_controls[control_index]
			var finish: Vector2 = rounded_controls[control_index + 1]
			var delta := finish - start
			# Four samples per logical cell preserve the visual Bézier curve. These
			# are curve samples only; they no longer subdivide the terrain grid.
			var steps := maxi(1, ceili(maxf(absf(delta.x), absf(delta.y)) * 4.0))
			if steps == 0:
				continue
			for step in steps:
				var sample := start.lerp(finish, float(step) / float(steps))
				var grid_point := sample
				if curve.is_empty() or not curve[curve.size() - 1].is_equal_approx(grid_point):
					curve.append(grid_point)
		var final_point := rounded_controls[rounded_controls.size() - 1]
		if curve.is_empty() or not curve[curve.size() - 1].is_equal_approx(final_point):
			curve.append(final_point)
		if curve.size() < 2:
			continue
		var progress := PackedFloat32Array()
		progress.resize(curve.size())
		var total_length := 0.0
		for index in range(1, curve.size()):
			total_length += curve[index - 1].distance_to(curve[index])
			progress[index] = total_length
		if total_length > 0.0001:
			for index in progress.size():
				progress[index] /= total_length
		cliff_curves.append(curve)
		cliff_curve_progresses.append(progress)
		cliff_curve_lengths.append(total_length)
	_index_cliff_cells()


func _build_cliff_edge_geometry() -> void:
	cliff_edge_bottoms.clear()
	cliff_edge_tops.clear()
	for curve_index in cliff_curves.size():
		var bottoms := PackedVector2Array()
		var tops := PackedVector2Array()
		for grid_position in cliff_curves[curve_index]:
			bottoms.append(_project_cliff_surface_point(grid_position, curve_index, false))
			tops.append(_project_cliff_surface_point(grid_position, curve_index, true))
		cliff_edge_bottoms.append(bottoms)
		cliff_edge_tops.append(tops)


func _index_cliff_cells() -> void:
	cliff_cell_candidates.clear()
	for curve_index in cliff_curves.size():
		var curve := cliff_curves[curve_index]
		for index in range(curve.size() - 1):
			var start := curve[index]
			var finish := curve[index + 1]
			# Includes the maximum far-side occlusion reach (2.5 cells) plus the
			# one-cell safety extension used by _far_occluder_cliff_for_polygon.
			var candidate_margin := Vector2i.ONE * 4
			var minimum := Vector2i(floori(minf(start.x, finish.x)), floori(minf(start.y, finish.y))) - candidate_margin
			var maximum := Vector2i(floori(maxf(start.x, finish.x)), floori(maxf(start.y, finish.y))) + candidate_margin
			for y in range(maxi(0, minimum.y), mini(map_data.rows - 1, maximum.y) + 1):
				for x in range(maxi(0, minimum.x), mini(map_data.columns - 1, maximum.x) + 1):
					var cell := Vector2i(x, y)
					var candidates: Array = cliff_cell_candidates.get(cell, [])
					if not curve_index in candidates:
						candidates.append(curve_index)
						cliff_cell_candidates[cell] = candidates


func _rounded_cliff_controls(controls: PackedVector2Array) -> PackedVector2Array:
	var radius := generation_settings.cliff_corner_smoothing_cells
	if radius <= 0.001 or controls.size() < 3:
		return controls
	var closed := controls[0].is_equal_approx(controls[controls.size() - 1])
	if closed:
		var samples := PackedVector2Array()
		var corner_count := controls.size() - 1
		for index in corner_count:
			var previous := controls[(index - 1 + corner_count) % corner_count]
			var corner := controls[index]
			var following := controls[(index + 1) % corner_count]
			var incoming := corner - previous
			var outgoing := following - corner
			var trim := minf(radius, minf(incoming.length(), outgoing.length()) * 0.45)
			var entry := corner - incoming.normalized() * trim
			var exit_point := corner + outgoing.normalized() * trim
			for step in range(9):
				var t := float(step) / 8.0
				var sample := entry * (1.0 - t) * (1.0 - t) + corner * 2.0 * (1.0 - t) * t + exit_point * t * t
				if samples.is_empty() or not samples[samples.size() - 1].is_equal_approx(sample):
					samples.append(sample)
		if not samples.is_empty():
			samples.append(samples[0])
		return samples
	var samples := PackedVector2Array([controls[0]])
	for index in range(1, controls.size() - 1):
		var previous := controls[index - 1]
		var corner := controls[index]
		var following := controls[index + 1]
		var incoming := corner - previous
		var outgoing := following - corner
		if incoming.length_squared() <= 0.001 or outgoing.length_squared() <= 0.001:
			continue
		var trim := minf(radius, minf(incoming.length(), outgoing.length()) * 0.45)
		var entry := corner - incoming.normalized() * trim
		var exit_point := corner + outgoing.normalized() * trim
		for step in range(9):
			var t := float(step) / 8.0
			var sample := entry * (1.0 - t) * (1.0 - t) + corner * 2.0 * (1.0 - t) * t + exit_point * t * t
			if samples.is_empty() or not samples[samples.size() - 1].is_equal_approx(sample):
				samples.append(sample)
	if not samples[samples.size() - 1].is_equal_approx(controls[controls.size() - 1]):
		samples.append(controls[controls.size() - 1])
	return samples


## x/y are the nearest curve point, z is distance progress, and w is signed
## side. With points authored in order, the elevated terrain is on the left.
func _nearest_cliff_point(grid_position: Vector2, curve_index: int) -> Vector4:
	var best := Vector4(0.0, 0.0, 0.0, 1.0)
	var best_distance_squared := INF
	var curve := cliff_curves[curve_index]
	var progress := cliff_curve_progresses[curve_index]
	for index in range(curve.size() - 1):
		var start: Vector2 = curve[index]
		var finish: Vector2 = curve[index + 1]
		var segment := finish - start
		var length_squared := segment.length_squared()
		if length_squared <= 0.000001:
			continue
		var segment_progress := clampf((grid_position - start).dot(segment) / length_squared, 0.0, 1.0)
		var nearest := start + segment * segment_progress
		var distance_squared := grid_position.distance_squared_to(nearest)
		if distance_squared < best_distance_squared:
			best_distance_squared = distance_squared
			var path_progress := lerpf(progress[index], progress[index + 1], segment_progress)
			best = Vector4(nearest.x, nearest.y, path_progress, segment.cross(grid_position - nearest))
	return best


## 1 is a visible near-side wall, -1 is a far-side rim, and 0 is edge-on.
func _cliff_view_side(curve_index: int, start: Vector2, finish: Vector2) -> int:
	var delta := finish - start
	if delta.length_squared() <= 0.000001 or absf(delta.x) <= 0.0001:
		return 0
	var near_determinant := delta.x
	if _is_closed_cliff(curve_index):
		var area_twice := 0.0
		var curve := cliff_curves[curve_index]
		for index in range(curve.size() - 1):
			area_twice += curve[index].cross(curve[index + 1])
		# Positive signed area in screen coordinates places the interior on the
		# screen-left normal; reverse-wound islands invert the determinant.
		near_determinant *= -1.0 if area_twice > 0.0 else 1.0
	return 1 if near_determinant > 0.0 else -1


func _nearest_cliff_segment_index(grid_position: Vector2, curve_index: int) -> int:
	var best_index := -1
	var best_distance_squared := INF
	var curve := cliff_curves[curve_index]
	for index in range(curve.size() - 1):
		var start := curve[index]
		var finish := curve[index + 1]
		var segment := finish - start
		var length_squared := segment.length_squared()
		if length_squared <= 0.000001:
			continue
		var amount := clampf((grid_position - start).dot(segment) / length_squared, 0.0, 1.0)
		var distance_squared := grid_position.distance_squared_to(start + segment * amount)
		if distance_squared < best_distance_squared:
			best_distance_squared = distance_squared
			best_index = index
	return best_index


func _far_occluder_cliff_for_polygon(polygon: PackedVector2Array) -> int:
	if polygon.is_empty():
		return -1
	var centre := Vector2.ZERO
	for point in polygon:
		centre += point
	centre /= polygon.size()
	var cell := Vector2i(floori(centre.x), floori(centre.y))
	var candidates: Array = cliff_cell_candidates.get(cell, [])
	for curve_index: int in candidates:
		var elevated := _point_inside_cliff(centre, curve_index) if _is_closed_cliff(curve_index) else _nearest_cliff_point(centre, curve_index).w < 0.0
		if not elevated:
			continue
		var segment_index := _nearest_cliff_segment_index(centre, curve_index)
		if segment_index < 0:
			continue
		var curve := cliff_curves[curve_index]
		# Edge-on segments belong to the far-side surface mask. Excluding them
		# leaves a wedge precisely where a curve changes from near to far.
		var has_far_or_edge_segment := _cliff_view_side(curve_index, curve[segment_index], curve[segment_index + 1]) <= 0
		for neighbour_offset in [-1, 1]:
			var neighbour: int = segment_index + neighbour_offset
			if _is_closed_cliff(curve_index):
				neighbour = posmod(neighbour, curve.size() - 1)
			if neighbour >= 0 and neighbour < curve.size() - 1:
				has_far_or_edge_segment = has_far_or_edge_segment or _cliff_view_side(curve_index, curve[neighbour], curve[neighbour + 1]) <= 0
		if not has_far_or_edge_segment:
			continue
		var nearest := _nearest_cliff_point(centre, curve_index)
		var distance := centre.distance_to(Vector2(nearest.x, nearest.y))
		var projected_depth := _cliff_separation_at_progress(curve_index, nearest.z) * generation_settings.height_lift_pixels / map_data.cell_size
		if distance <= projected_depth + 1.0:
			return curve_index
	return -1


func _cliff_setting(values: PackedFloat32Array, index: int, fallback: float) -> float:
	if values.is_empty():
		return fallback
	return values[mini(index, values.size() - 1)]


func _is_closed_cliff(curve_index: int) -> bool:
	var curve := cliff_curves[curve_index]
	return curve.size() > 2 and curve[0].is_equal_approx(curve[curve.size() - 1])


func _cliff_separation_at_progress(curve_index: int, progress: float) -> float:
	var height := _cliff_setting(generation_settings.cliff_heights, curve_index, 24.0)
	if _is_closed_cliff(curve_index):
		return height
	var transition := _cliff_setting(generation_settings.cliff_transition_cells, curve_index, 1.0)
	if transition <= 0.0001:
		return height
	var distance_from_end := minf(progress, 1.0 - progress) * cliff_curve_lengths[curve_index]
	var fade := smoothstep(0.0, transition, distance_from_end)
	return height * fade


func _point_inside_cliff(grid_position: Vector2, curve_index: int) -> bool:
	var curve := cliff_curves[curve_index]
	var inside := false
	var previous := curve.size() - 1
	for current in curve.size():
		var a: Vector2 = curve[current]
		var b: Vector2 = curve[previous]
		if (a.y > grid_position.y) != (b.y > grid_position.y):
			var crossing_x := (b.x - a.x) * (grid_position.y - a.y) / (b.y - a.y) + a.x
			if grid_position.x < crossing_x:
				inside = not inside
		previous = current
	return inside


func _cliff_offset_for_vertex(owner_position: Vector2, vertex: Vector2) -> float:
	if not generation_settings.cliff_enabled or cliff_curves.is_empty():
		return 0.0
	if cliff_vertex_offset_cache.has(vertex):
		return cliff_vertex_offset_cache[vertex]
	var offset := 0.0
	var touches_boundary := false
	for curve_index in cliff_curves.size():
		var nearest := _nearest_cliff_point(Vector2(vertex), curve_index)
		var on_boundary := vertex.distance_squared_to(Vector2(nearest.x, nearest.y)) < 0.0000001
		touches_boundary = touches_boundary or on_boundary
		# Classify the whole triangle from its centroid. Classifying each vertex
		# independently can make a triangle straddle two sides near a bend, which
		# folds it over and leaves a background-coloured hole.
		var elevated := false
		if _is_closed_cliff(curve_index):
			elevated = _point_inside_cliff(owner_position, curve_index)
		else:
			elevated = (_nearest_cliff_point(owner_position, curve_index).w < 0.0) if on_boundary else nearest.w < 0.0
		if elevated:
			offset = maxf(offset, _cliff_separation_at_progress(curve_index, nearest.z))
	if not touches_boundary:
		cliff_vertex_offset_cache[vertex] = offset
	return offset


func _build_cliff_geometry() -> void:
	for old_node_name in [&"CliffFaceBacking", &"CliffFaceForeground", &"CliffFaceNear", &"CliffFaces", &"CliffFacesForeground", &"CliffTopOccluders", &"CliffCollision"]:
		var old_node := get_node_or_null(NodePath(old_node_name))
		if old_node:
			old_node.free()
	if not generation_settings.cliff_enabled or cliff_curves.is_empty():
		return
	var backing_vertices := PackedVector2Array()
	var backing_uvs := PackedVector2Array()
	var backing_indices := PackedInt32Array()
	var backing_foreground_vertices := PackedVector2Array()
	var backing_foreground_uvs := PackedVector2Array()
	var backing_foreground_indices := PackedInt32Array()
	var collision_body := StaticBody2D.new()
	collision_body.name = "CliffCollision"
	collision_body.collision_layer = 1
	collision_body.collision_mask = 2
	add_child(collision_body)
	# Physics follows the complete ordered curve. Render seam fragments are
	# cell-local and can be absent where a curve merely touches a cell corner.
	for curve in cliff_curves:
		for index in range(curve.size() - 1):
			var collision := CollisionShape2D.new()
			var shape := SegmentShape2D.new()
			shape.a = curve[index] * map_data.cell_size
			shape.b = curve[index + 1] * map_data.cell_size
			collision.shape = shape
			collision_body.add_child(collision)
	for curve_index in cliff_curves.size():
		var curve := cliff_curves[curve_index]
		var edge_bottoms := cliff_edge_bottoms[curve_index]
		var edge_tops := cliff_edge_tops[curve_index]
		# A complete wall behind the terrain fills corner-touch cases. The clipped
		# seam faces below remain the visible edge wherever terrain overlaps it.
		for index in range(curve.size() - 1):
			var start := curve[index]
			var finish := curve[index + 1]
			var start_progress := _nearest_cliff_point(start, curve_index).z
			var finish_progress := _nearest_cliff_point(finish, curve_index).z
			var start_separation := _cliff_separation_at_progress(curve_index, start_progress)
			var finish_separation := _cliff_separation_at_progress(curve_index, finish_progress)
			if start_separation <= 0.001 and finish_separation <= 0.001:
				continue
			# The terrain top/bottom and wall originate from these same edge arrays.
			# Extend beneath both terrain surfaces to cover independent edge AA.
			var quad := PackedVector2Array([
				edge_tops[index] - Vector2(0.0, CLIFF_SEAM_OVERLAP_PIXELS),
				edge_tops[index + 1] - Vector2(0.0, CLIFF_SEAM_OVERLAP_PIXELS),
				edge_bottoms[index + 1] + Vector2(0.0, CLIFF_SEAM_OVERLAP_PIXELS),
				edge_bottoms[index] + Vector2(0.0, CLIFF_SEAM_OVERLAP_PIXELS),
			])
			var start_path_pixel := start_progress * cliff_curve_lengths[curve_index] * map_data.cell_size
			var finish_path_pixel := finish_progress * cliff_curve_lengths[curve_index] * map_data.cell_size
			var start_depth_pixel := start_separation * generation_settings.height_lift_pixels
			var finish_depth_pixel := finish_separation * generation_settings.height_lift_pixels
			var quad_uvs := PackedVector2Array([
				Vector2(start_path_pixel, 0), Vector2(finish_path_pixel, 0),
				Vector2(finish_path_pixel, finish_depth_pixel), Vector2(start_path_pixel, start_depth_pixel),
			])
			if _cliff_view_side(curve_index, start, finish) > 0:
				var first := backing_foreground_vertices.size()
				backing_foreground_vertices.append_array(quad)
				backing_foreground_uvs.append_array(quad_uvs)
				backing_foreground_indices.append_array(PackedInt32Array([first, first + 1, first + 2, first, first + 2, first + 3]))
			else:
				var first := backing_vertices.size()
				backing_vertices.append_array(quad)
				backing_uvs.append_array(quad_uvs)
				backing_indices.append_array(PackedInt32Array([first, first + 1, first + 2, first, first + 2, first + 3]))
	# Only the screen-near wall is visible, and it remains behind actors standing
	# on the lower/southern side. Far-side depth comes from CliffFarSurface.
	# ProceduralTerrain is z=-10 in the scene. Relative z=1 places the wall at
	# effective z=-9: above overlapping terrain, but still below actors at z=0.
	_add_cliff_face_mesh(&"CliffFaceNear", backing_foreground_vertices, backing_foreground_uvs, backing_foreground_indices, 1)


func _add_cliff_face_mesh(node_name: StringName, vertices: PackedVector2Array, uvs: PackedVector2Array, indices: PackedInt32Array, draw_z: int) -> void:
	if vertices.is_empty():
		return
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_TEX_UV] = uvs
	arrays[Mesh.ARRAY_INDEX] = indices
	var face_mesh := ArrayMesh.new()
	face_mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	var faces := MeshInstance2D.new()
	faces.name = node_name
	faces.z_index = draw_z
	faces.mesh = face_mesh
	var face_material := ShaderMaterial.new()
	face_material.shader = CLIFF_FACE_SHADER
	faces.material = face_material
	add_child(faces)


func get_map_size() -> Vector2:
	return Vector2(map_data.columns * map_data.cell_size, map_data.rows * map_data.cell_size)


func get_map_rect() -> Rect2:
	return Rect2(global_position, get_map_size())


func get_projected_map_rect() -> Rect2:
	var first := true
	var minimum := Vector2.ZERO
	var maximum := Vector2.ZERO
	for y in map_data.rows + 1:
		for x in map_data.columns + 1:
			var logical := to_global(Vector2(x, y) * map_data.cell_size)
			var projected := project_global_position(logical)
			if first:
				minimum = projected
				maximum = projected
				first = false
			else:
				minimum = minimum.min(projected)
				maximum = maximum.max(projected)
	return Rect2(minimum, maximum - minimum)


func height_lift_at_global(logical_global_position: Vector2) -> float:
	return map_data.height_at_world(to_local(logical_global_position)) * generation_settings.height_lift_pixels


func projection_offset_at_global(logical_global_position: Vector2) -> Vector2:
	var local_position := to_local(logical_global_position)
	var height := map_data.height_at_world(local_position) + _cliff_offset_at_world(local_position)
	return Vector2(0.0, -height * generation_settings.height_lift_pixels)


func _cliff_offset_at_world(local_position: Vector2) -> float:
	if not generation_settings.cliff_enabled or cliff_curves.is_empty():
		return 0.0
	var grid_position := local_position / map_data.cell_size
	var offset := 0.0
	for curve_index in cliff_curves.size():
		var nearest := _nearest_cliff_point(grid_position, curve_index)
		var elevated := _point_inside_cliff(grid_position, curve_index) if _is_closed_cliff(curve_index) else nearest.w < 0.0
		if elevated:
			offset = maxf(offset, _cliff_separation_at_progress(curve_index, nearest.z))
	return offset


func project_global_position(logical_global_position: Vector2) -> Vector2:
	return logical_global_position + projection_offset_at_global(logical_global_position)


func should_actor_render_above_cliff(logical_global_position: Vector2) -> bool:
	var grid_position := to_local(logical_global_position) / map_data.cell_size
	if _elevated_cliff_at(grid_position) >= 0:
		return true
	for curve_index in cliff_curves.size():
		var segment_index := _nearest_cliff_segment_index(grid_position, curve_index)
		if segment_index < 0:
			continue
		var curve := cliff_curves[curve_index]
		if _cliff_view_side(curve_index, curve[segment_index], curve[segment_index + 1]) <= 0:
			continue
		var nearest := _nearest_cliff_point(grid_position, curve_index)
		var distance := grid_position.distance_to(Vector2(nearest.x, nearest.y))
		var visible_depth := _cliff_separation_at_progress(curve_index, nearest.z) * generation_settings.height_lift_pixels / map_data.cell_size
		if distance <= visible_depth + 1.0:
			return true
	return false


func relief_shade_at_global(logical_global_position: Vector2) -> float:
	return map_data.relief_shade_at_world(to_local(logical_global_position))


func _upload_terrain_cells() -> void:
	var image_a := Image.create(map_data.columns + 1, map_data.rows + 1, false, Image.FORMAT_RGBA8)
	var image_b := Image.create(map_data.columns + 1, map_data.rows + 1, false, Image.FORMAT_RGBA8)
	var image_c := Image.create(map_data.columns + 1, map_data.rows + 1, false, Image.FORMAT_RGBA8)
	for vertex_y in map_data.rows + 1:
		for vertex_x in map_data.columns + 1:
			var weights := PackedFloat32Array()
			weights.resize(10)
			var contributors := 0.0
			for offset: Vector2i in [Vector2i(-1, -1), Vector2i(0, -1), Vector2i(-1, 0), Vector2i.ZERO]:
				var cell: Vector2i = Vector2i(vertex_x, vertex_y) + offset
				if map_data.contains(cell):
					weights[map_data.terrain_at(cell)] += 1.0
					contributors += 1.0
			if contributors > 0.0:
				for index in weights.size():
					weights[index] /= contributors
			image_a.set_pixel(vertex_x, vertex_y, Color(weights[0], weights[1], weights[2], weights[3]))
			image_b.set_pixel(vertex_x, vertex_y, Color(weights[4], weights[5], weights[6], weights[7]))
			image_c.set_pixel(vertex_x, vertex_y, Color(weights[8], weights[9], 0.0, 0.0))
	terrain_weight_texture_a = ImageTexture.create_from_image(image_a)
	terrain_weight_texture_b = ImageTexture.create_from_image(image_b)
	terrain_weight_texture_c = ImageTexture.create_from_image(image_c)
	var shader_material := material as ShaderMaterial
	shader_material.set_shader_parameter("terrain_weight_map_a", terrain_weight_texture_a)
	shader_material.set_shader_parameter("terrain_weight_map_b", terrain_weight_texture_b)
	shader_material.set_shader_parameter("terrain_weight_map_c", terrain_weight_texture_c)
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


func _upload_cliff_shadows() -> void:
	var image := Image.create(map_data.columns + 1, map_data.rows + 1, false, Image.FORMAT_R8)
	for vertex_y in map_data.rows + 1:
		for vertex_x in map_data.columns + 1:
			var position := Vector2(vertex_x, vertex_y)
			var shadow := 0.0
			for curve_index in cliff_curves.size():
				var nearest := _nearest_cliff_point(position, curve_index)
				# Open cliffs elevate the negative signed side. Closed cliffs use
				# polygon containment, so their lower side is outside the loop.
				var on_lower_side := not _point_inside_cliff(position, curve_index) if _is_closed_cliff(curve_index) else nearest.w > 0.0001
				if not on_lower_side:
					continue
				var distance := position.distance_to(Vector2(nearest.x, nearest.y))
				var height := _cliff_separation_at_progress(curve_index, nearest.z)
				var reach := clampf(height * generation_settings.height_lift_pixels / map_data.cell_size, 0.35, 2.5)
				shadow = maxf(shadow, (1.0 - smoothstep(0.0, reach, distance)) * 0.32)
			image.set_pixel(vertex_x, vertex_y, Color(shadow, 0.0, 0.0))
	cliff_shadow_texture = ImageTexture.create_from_image(image)
	var shader_material := material as ShaderMaterial
	shader_material.set_shader_parameter("cliff_shadow_map", cliff_shadow_texture)
