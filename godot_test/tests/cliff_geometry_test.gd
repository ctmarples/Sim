extends SceneTree


func _init() -> void:
	var renderer := TerrainRenderer.new()
	renderer.cliff_curves = [PackedVector2Array([Vector2(0, 1), Vector2(1, 0)])]
	assert(renderer._triangle_corners_for_cell(Vector2i.ZERO) == [[0, 1, 3], [1, 2, 3]])

	renderer.cliff_curves = [PackedVector2Array([Vector2.ZERO, Vector2.ONE])]
	assert(renderer._triangle_corners_for_cell(Vector2i.ZERO) == [[0, 1, 2], [0, 2, 3]])

	# Unit diagonal subdivision must retain every intermediate grid seam so the
	# two halves meet continuously rather than skipping cells at long diagonals.
	var settings := TerrainGenerationSettings.new()
	settings.columns = 8
	settings.rows = 8
	settings.cliff_paths = [PackedVector2Array([Vector2(1, 5), Vector2(5, 1)])]
	settings.cliff_heights = PackedFloat32Array([20.0])
	settings.cliff_transition_cells = PackedFloat32Array([3.0])
	renderer.generation_settings = settings
	renderer.map_data = TerrainMapData.new()
	renderer.map_data.configure(8, 8, settings.cell_size)
	renderer._build_cliff_curve()
	renderer._build_map_mesh()
	renderer._build_cliff_test()
	assert(renderer.get_node("CliffCollision").get_child_count() == renderer.cliff_render_curves[0].size() - 1)
	assert(renderer.cliff_curves[0].size() == 17)
	assert(renderer.cliff_curves[0][0] == Vector2(1, 5))
	assert(renderer.cliff_curves[0][-1] == Vector2(5, 1))
	for index in range(renderer.cliff_curves[0].size() - 1):
		var step := renderer.cliff_curves[0][index + 1] - renderer.cliff_curves[0][index]
		assert(is_equal_approx(absf(step.x), 0.25))
		assert(is_equal_approx(absf(step.y), 0.25))
	var start_height := renderer._cliff_separation_at_progress(0, 0.0)
	var quarter_height := renderer._cliff_separation_at_progress(0, 0.25)
	var middle_height := renderer._cliff_separation_at_progress(0, 0.5)
	assert(is_equal_approx(start_height, 0.0))
	assert(quarter_height > start_height and quarter_height < middle_height)
	assert(is_equal_approx(quarter_height, renderer._cliff_separation_at_progress(0, 0.75)))
	assert(middle_height > 19.0)

	settings.cliff_corner_smoothing_cells = 1.5
	var rounded := renderer._rounded_cliff_controls(PackedVector2Array([
		Vector2(1, 1), Vector2(5, 1), Vector2(8, 4),
	]))
	assert(rounded[0] == Vector2(1, 1))
	assert(rounded[rounded.size() - 1] == Vector2(8, 4))
	assert(rounded.size() > 3)
	var has_fractional_sample := false
	for point in rounded:
		if not point.is_equal_approx(point.round()):
			has_fractional_sample = true
	assert(has_fractional_sample)
	var rounded_closed := renderer._rounded_cliff_controls(PackedVector2Array([
		Vector2(1, 1), Vector2(5, 1), Vector2(5, 5), Vector2(1, 5), Vector2(1, 1),
	]))
	assert(rounded_closed[0].is_equal_approx(rounded_closed[-1]))
	assert(not Vector2(1, 1) in rounded_closed)
	renderer.cliff_curves = [PackedVector2Array([
		Vector2(1, 1), Vector2(5, 1), Vector2(5, 5), Vector2(1, 5), Vector2(1, 1),
	])]
	assert(renderer._cliff_view_side(0, Vector2(1, 1), Vector2(5, 1)) == -1)
	assert(renderer._cliff_view_side(0, Vector2(5, 5), Vector2(1, 5)) == 1)
	assert(renderer._cliff_view_side(0, Vector2(5, 1), Vector2(5, 5)) == 0)

	renderer.free()
	print("cliff geometry tests passed")
	quit()
