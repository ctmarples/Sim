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
