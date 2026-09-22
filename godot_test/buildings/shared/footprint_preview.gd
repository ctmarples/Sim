@tool
extends Node2D


func _ready() -> void:
	top_level = true
	show_behind_parent = true
	set_process(Engine.is_editor_hint())
	queue_redraw()


func _process(_delta: float) -> void:
	if not Engine.is_editor_hint():
		return
	# Keep the guide at the scene origin regardless of edits to the building root.
	global_transform = Transform2D.IDENTITY


func _draw() -> void:
	if not Engine.is_editor_hint():
		return
	var building := get_parent() as ContainerBuilding
	if building == null or not building.show_footprint_in_editor:
		return
	var cells := building.footprint_cells
	var cell_size := building.editor_cell_size
	var footprint_size := Vector2(cells) * cell_size
	var top_left := -footprint_size * 0.5
	draw_rect(Rect2(top_left, footprint_size), Color(0.15, 0.65, 1.0, 0.12), true)
	draw_rect(Rect2(top_left, footprint_size), Color(0.15, 0.75, 1.0, 0.9), false, 2.0)
	for x in range(1, cells.x):
		var px := top_left.x + x * cell_size
		draw_line(Vector2(px, top_left.y), Vector2(px, top_left.y + footprint_size.y), Color(0.2, 0.7, 1.0, 0.65), 1.0)
	for y in range(1, cells.y):
		var py := top_left.y + y * cell_size
		draw_line(Vector2(top_left.x, py), Vector2(top_left.x + footprint_size.x, py), Color(0.2, 0.7, 1.0, 0.65), 1.0)
	draw_line(Vector2(-6, 0), Vector2(6, 0), Color.YELLOW, 2.0)
	draw_line(Vector2(0, -6), Vector2(0, 6), Color.YELLOW, 2.0)
