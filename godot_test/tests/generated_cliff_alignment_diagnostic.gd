extends SceneTree


func _init() -> void:
	var scene: PackedScene = load("res://scenes/game.tscn")
	var game: Node = scene.instantiate()
	root.add_child(game)
	await process_frame
	var renderer: TerrainRenderer = game.get_node("Ground/ProceduralTerrain")
	var maximum_error := 0.0
	var worst_point := Vector2.ZERO
	var seam_count := 0
	for curve_index in renderer.cliff_surface_segments.size():
		for seam: PackedVector2Array in renderer.cliff_surface_segments[curve_index]:
			for point in seam:
				var nearest := renderer._nearest_cliff_point(point, curve_index)
				var error := point.distance_to(Vector2(nearest.x, nearest.y))
				if error > maximum_error:
					maximum_error = error
					worst_point = point
			seam_count += 1
	var expected_collision_segments := 0
	for curve in renderer.cliff_render_curves:
		expected_collision_segments += curve.size() - 1
	var actual_collision_segments := renderer.get_node("CliffCollision").get_child_count()
	var mesh_arrays := renderer.mesh.surface_get_arrays(0)
	var mesh_vertices: PackedVector2Array = mesh_arrays[Mesh.ARRAY_VERTEX]
	var vertex_keys := {}
	for vertex in mesh_vertices:
		vertex_keys[Vector2i(roundi(vertex.x * 1000.0), roundi(vertex.y * 1000.0))] = true
	var missing_projected_vertices := 0
	var first_missing := Vector2.ZERO
	for curve_index in renderer.cliff_surface_segments.size():
		for section: PackedVector2Array in renderer.cliff_surface_segments[curve_index]:
			for point in section:
				var logical := point * renderer.map_data.cell_size
				for height in [
					renderer._clipped_terrain_height(point, curve_index, false),
					renderer._clipped_terrain_height(point, curve_index, true),
				]:
					var projected := logical - Vector2(0.0, height * renderer.generation_settings.height_lift_pixels)
					var key := Vector2i(roundi(projected.x * 1000.0), roundi(projected.y * 1000.0))
					if not vertex_keys.has(key):
						if missing_projected_vertices == 0:
							first_missing = projected
						missing_projected_vertices += 1
	var wall_vertex_keys := {}
	for wall_name in ["CliffFaceBacking", "CliffFaceForeground"]:
		var wall: MeshInstance2D = renderer.get_node_or_null(wall_name)
		if wall == null:
			continue
		var wall_arrays := wall.mesh.surface_get_arrays(0)
		for vertex: Vector2 in wall_arrays[Mesh.ARRAY_VERTEX]:
			wall_vertex_keys[Vector2i(roundi(vertex.x * 1000.0), roundi(vertex.y * 1000.0))] = true
	var missing_wall_vertices := 0
	for curve_index in renderer.cliff_render_curves.size():
		for point in renderer.cliff_render_curves[curve_index]:
			var progress := renderer._nearest_cliff_point(point, curve_index).z
			if renderer._cliff_separation_at_progress(curve_index, progress) <= 0.001:
				continue
			var logical := point * renderer.map_data.cell_size
			for height in [
				renderer._clipped_terrain_height(point, curve_index, false),
				renderer._clipped_terrain_height(point, curve_index, true),
			]:
				var projected := logical - Vector2(0.0, height * renderer.generation_settings.height_lift_pixels)
				var key := Vector2i(roundi(projected.x * 1000.0), roundi(projected.y * 1000.0))
				if not wall_vertex_keys.has(key):
					missing_wall_vertices += 1
	print("generated cliff alignment: seams=", seam_count,
		" max_error_cells=", maximum_error,
		" max_error_pixels=", maximum_error * renderer.map_data.cell_size,
		" worst_point=", worst_point,
		" collision=", actual_collision_segments, "/", expected_collision_segments,
		" missing_projected_vertices=", missing_projected_vertices,
		" missing_wall_vertices=", missing_wall_vertices,
		" first_missing=", first_missing)
	assert(maximum_error * renderer.map_data.cell_size < 0.001)
	assert(actual_collision_segments == expected_collision_segments)
	assert(missing_projected_vertices == 0)
	assert(missing_wall_vertices == 0)
	game.free()
	quit()
