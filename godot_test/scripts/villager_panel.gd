class_name VillagerPanel
extends PanelContainer

signal assignment_requested(villager: Villager)

var villagers: Array = []
var selected_villager: Villager


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("villager_list"):
		toggle()
		get_viewport().set_input_as_handled()


func bind(available_villagers: Array) -> void:
	villagers = available_villagers
	_rebuild_list()


func toggle() -> void:
	visible = not visible


func select_villager(villager: Villager) -> void:
	selected_villager = villager
	$Margin/Rows/Selected.text = "Selected: Villager"
	$Margin/Rows/Status.text = villager.status
	$Margin/Rows/Assign.disabled = false
	if not villager.status_changed.is_connected(_update_status):
		villager.status_changed.connect(_update_status)
	visible = true


func _rebuild_list() -> void:
	for child in $Margin/Rows/List.get_children():
		child.queue_free()
	for villager in villagers:
		var button := Button.new()
		button.text = "Villager"
		button.pressed.connect(select_villager.bind(villager))
		$Margin/Rows/List.add_child(button)


func _update_status() -> void:
	if selected_villager:
		$Margin/Rows/Status.text = selected_villager.status


func _on_assign_pressed() -> void:
	if selected_villager:
		assignment_requested.emit(selected_villager)
