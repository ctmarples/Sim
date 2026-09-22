class_name DebugOverlay
extends Node2D

var map_data: TerrainMapData
var terrain_renderer: TerrainRenderer
var show_grid := false
var show_objects := false


func bind(renderer: TerrainRenderer) -> void:
	terrain_renderer = renderer
	map_data = renderer.map_data
	queue_redraw()


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("debug_grid"):
		show_grid = not show_grid
		queue_redraw()
		get_viewport().set_input_as_handled()
	elif event.is_action_pressed("debug_objects"):
		show_objects = not show_objects
		queue_redraw()
		get_viewport().set_input_as_handled()


func _process(_delta: float) -> void:
	if show_objects:
		queue_redraw()


func _draw() -> void:
	if map_data == null:
		return
	if show_grid:
		_draw_grid()
	if show_objects:
		_draw_collision_objects()


func _draw_grid() -> void:
	var width := map_data.columns * map_data.cell_size
	var height := map_data.rows * map_data.cell_size
	var colour := Color(1.0, 1.0, 1.0, 0.22)
	for x in map_data.columns + 1:
		var points := PackedVector2Array()
		for y in map_data.rows + 1:
			points.append(_project_map_point(Vector2(x, y) * map_data.cell_size))
		draw_polyline(points, colour, 1.0)
	for y in map_data.rows + 1:
		var points := PackedVector2Array()
		for x in map_data.columns + 1:
			points.append(_project_map_point(Vector2(x, y) * map_data.cell_size))
		draw_polyline(points, colour, 1.0)
	_draw_cliff_debug()


func _draw_cliff_debug() -> void:
	if terrain_renderer == null or terrain_renderer.cliff_curves.is_empty():
		return
	var cell_classes := {}
	for curve_index in terrain_renderer.cliff_curves.size():
		var curve := terrain_renderer.cliff_curves[curve_index]
		for index in range(curve.size() - 1):
			var start: Vector2 = curve[index]
			var finish: Vector2 = curve[index + 1]
			var view_side: int = terrain_renderer._cliff_view_side(curve_index, start, finish)
			var colour := Color(1.0, 0.25, 0.15, 0.95) if view_side > 0 else (Color(0.15, 0.65, 1.0, 0.95) if view_side < 0 else Color(1.0, 0.9, 0.15, 0.95))
			var screen_start := to_local(terrain_renderer.to_global(terrain_renderer.cliff_edge_bottoms[curve_index][index]))
			var screen_finish := to_local(terrain_renderer.to_global(terrain_renderer.cliff_edge_bottoms[curve_index][index + 1]))
			draw_line(screen_start, screen_finish, colour, 3.0, true)
			draw_circle(screen_start, 2.5, colour)
			var tangent := (finish - start).normalized()
			var angle_to_y := rad_to_deg(acos(clampf(absf(tangent.dot(Vector2.DOWN)), 0.0, 1.0)))
			var label := ("N" if view_side > 0 else ("F" if view_side < 0 else "E")) + " %.1f°" % angle_to_y
			draw_string(ThemeDB.fallback_font, (screen_start + screen_finish) * 0.5 + Vector2(3, -3), label, HORIZONTAL_ALIGNMENT_LEFT, -1, 9, colour)
			var minimum := Vector2i(floori(minf(start.x, finish.x)), floori(minf(start.y, finish.y))) - Vector2i.ONE
			var maximum := Vector2i(floori(maxf(start.x, finish.x)), floori(maxf(start.y, finish.y))) + Vector2i.ONE
			for cell_y in range(maxi(0, minimum.y), mini(map_data.rows - 1, maximum.y) + 1):
				for cell_x in range(maxi(0, minimum.x), mini(map_data.columns - 1, maximum.x) + 1):
					var cell := Vector2i(cell_x, cell_y)
					if not terrain_renderer._curve_intersects_cell(curve_index, cell):
						continue
					var classes: Dictionary = cell_classes.get(cell, {})
					classes[view_side] = true
					cell_classes[cell] = classes
	for cell: Vector2i in cell_classes:
		var classes: Dictionary = cell_classes[cell]
		var fill := Color(0.8, 0.2, 0.8, 0.18) if classes.size() > 1 else (Color(1.0, 0.25, 0.15, 0.15) if classes.has(1) else (Color(0.15, 0.65, 1.0, 0.15) if classes.has(-1) else Color(1.0, 0.9, 0.15, 0.15)))
		var polygon := PackedVector2Array([
			_project_map_point(Vector2(cell) * map_data.cell_size),
			_project_map_point(Vector2(cell + Vector2i.RIGHT) * map_data.cell_size),
			_project_map_point(Vector2(cell + Vector2i.ONE) * map_data.cell_size),
			_project_map_point(Vector2(cell + Vector2i.DOWN) * map_data.cell_size),
		])
		draw_colored_polygon(polygon, fill)
		draw_polyline(PackedVector2Array([polygon[0], polygon[1], polygon[2], polygon[3], polygon[0]]), Color(fill, 0.8), 1.5)


func _project_map_point(map_position: Vector2) -> Vector2:
	if terrain_renderer == null:
		return map_position
	var logical_global := terrain_renderer.to_global(map_position)
	return to_local(terrain_renderer.project_global_position(logical_global))


func _draw_collision_objects() -> void:
	var actors := get_parent().get_node_or_null("Actors")
	if actors == null:
		return
	for actor in actors.get_children():
		_draw_actor(actor)


func _draw_actor(actor: Node) -> void:
	if actor is Node2D:
		var origin := to_local(actor.global_position)
		draw_line(origin - Vector2(5, 0), origin + Vector2(5, 0), Color.YELLOW, 2.0)
		draw_line(origin - Vector2(0, 5), origin + Vector2(0, 5), Color.YELLOW, 2.0)
		draw_string(ThemeDB.fallback_font, origin + Vector2(7, -7), actor.name, HORIZONTAL_ALIGNMENT_LEFT, -1, 12, Color.YELLOW)
	for child in actor.get_children():
		if child is CollisionShape2D and child.shape:
			_draw_shape(child)
		elif child is Area2D:
			for area_child in child.get_children():
				if area_child is CollisionShape2D and area_child.shape:
					_draw_shape(area_child)


func _draw_shape(collision: CollisionShape2D) -> void:
	var centre := to_local(collision.global_position)
	var colour := Color(1.0, 0.2, 0.2, 0.85)
	if collision.shape is CircleShape2D:
		draw_arc(centre, collision.shape.radius, 0, TAU, 24, colour, 2.0)
	elif collision.shape is RectangleShape2D:
		draw_rect(Rect2(centre - collision.shape.size * 0.5, collision.shape.size), colour, false, 2.0)
	elif collision.shape is CapsuleShape2D:
		var size := Vector2(collision.shape.radius * 2.0, collision.shape.height)
		draw_rect(Rect2(centre - size * 0.5, size), colour, false, 2.0)
