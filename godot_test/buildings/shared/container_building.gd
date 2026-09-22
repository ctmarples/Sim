@tool
class_name ContainerBuilding
extends StaticBody2D

signal clicked(building: ContainerBuilding)

@export var building_name := "Building"
@export_category("Footprint")
@export var footprint_cells := Vector2i.ONE:
	set(value):
		footprint_cells = Vector2i(maxi(1, value.x), maxi(1, value.y))
		_update_footprint_preview()
		_update_interaction_area()
@export_category("Editor Footprint Preview")
@export var show_footprint_in_editor := true:
	set(value):
		show_footprint_in_editor = value
		_update_footprint_preview()
@export_range(8.0, 256.0, 1.0) var editor_cell_size := 40.0:
	set(value):
		editor_cell_size = value
		_update_footprint_preview()
		_update_interaction_area()
@export_category("Building Data")
@export var inventory_capacity := -1
@export var recipes: Array[StringName] = []
var inventory := ItemInventory.new()


func _ready() -> void:
	_update_interaction_area()
	if Engine.is_editor_hint():
		_update_footprint_preview()
		return
	add_to_group(&"interactables")
	inventory.max_capacity = inventory_capacity
	$SelectionArea.input_event.connect(_on_selection_input_event)


func configure_for_cell_size(cell_size: float) -> void:
	scale = Vector2.ONE * (cell_size / 40.0)


func _update_footprint_preview() -> void:
	if Engine.is_editor_hint() and has_node("FootprintPreview"):
		$FootprintPreview.queue_redraw()


func _update_interaction_area() -> void:
	if not has_node("InteractionArea/InteractionShape"):
		return
	# The entrance occupies the horizontally centred cell in the bottom row.
	$InteractionArea.position = Vector2(0.0, (footprint_cells.y - 1) * editor_cell_size * 0.5)
	var shape := $InteractionArea/InteractionShape.shape as RectangleShape2D
	if shape:
		shape.size = Vector2.ONE * editor_cell_size


func interact(actor: Node) -> void:
	if actor is Player:
		actor.open_container(inventory, building_name)
		actor.show_status("Opened %s" % building_name)


func can_interact(actor: Node2D) -> bool:
	return $InteractionArea.overlaps_body(actor)


func get_interaction_position() -> Vector2:
	return $InteractionArea.global_position


func _input_event(_viewport: Node, event: InputEvent, _shape_idx: int) -> void:
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.pressed:
		clicked.emit(self)


func _on_selection_input_event(_viewport: Node, event: InputEvent, _shape_idx: int) -> void:
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.pressed:
		clicked.emit(self)
