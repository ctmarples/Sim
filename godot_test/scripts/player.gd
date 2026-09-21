class_name Player
extends CharacterBody2D

signal inventory_toggle_requested
signal status_requested(message: String)
signal container_open_requested(container_inventory: ItemInventory, container_name: String)

@export var speed := 210.0
var map_bounds := Rect2(20.0, 20.0, 1160.0, 760.0)
var interaction_range := 60.0
var inventory := ItemInventory.new()


func open_container(container_inventory: ItemInventory, container_name: String) -> void:
	container_open_requested.emit(container_inventory, container_name)

@onready var animated_sprite: AnimatedSprite2D = $AnimatedSprite2D


func _ready() -> void:
	animated_sprite.play("walk_right")
	animated_sprite.pause()


func _physics_process(_delta: float) -> void:
	if Input.is_action_just_pressed("inventory"):
		inventory_toggle_requested.emit()
	if Input.is_action_just_pressed("interact"):
		_interact()
	var direction := Input.get_vector("move_left", "move_right", "move_up", "move_down")
	velocity = direction * speed

	if direction.x < 0.0:
		animated_sprite.play("walk_left")
	elif direction.x > 0.0:
		animated_sprite.play("walk_right")
	elif direction != Vector2.ZERO and not animated_sprite.is_playing():
		animated_sprite.play()

	if direction == Vector2.ZERO:
		animated_sprite.pause()

	move_and_slide()
	position.x = clampf(position.x, map_bounds.position.x, map_bounds.end.x)
	position.y = clampf(position.y, map_bounds.position.y, map_bounds.end.y)


func configure_for_map(map_rect: Rect2, cell_size: float) -> void:
	map_bounds = map_rect.grow(-cell_size * 0.5)
	interaction_range = cell_size * 1.5
	# Dog SVG import is 400px around a 40-unit logical viewBox.
	$AnimatedSprite2D.scale = Vector2.ONE * (cell_size / 400.0)
	$AnimatedSprite2D.position.y = -cell_size * 0.5
	$Camera2D.position.y = -cell_size * 0.5
	$Camera2D.limit_left = roundi(map_rect.position.x)
	$Camera2D.limit_top = roundi(map_rect.position.y)
	$Camera2D.limit_right = roundi(map_rect.end.x)
	$Camera2D.limit_bottom = roundi(map_rect.end.y)


func _interact() -> void:
	var nearest: Node2D
	var nearest_distance := interaction_range
	for candidate in get_tree().get_nodes_in_group(&"interactables"):
		if candidate.has_method("can_interact") and not candidate.can_interact(self):
			continue
		var target_position: Vector2 = candidate.get_interaction_position() if candidate.has_method("get_interaction_position") else candidate.global_position
		var distance := global_position.distance_to(target_position)
		if distance <= nearest_distance:
			nearest = candidate
			nearest_distance = distance
	if nearest:
		nearest.interact(self)
	else:
		show_status("Nothing to interact with")


func show_status(message: String) -> void:
	status_requested.emit(message)
