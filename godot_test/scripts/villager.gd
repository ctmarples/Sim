class_name Villager
extends CharacterBody2D

signal selected(villager: Villager)
signal status_changed

enum WorkState { UNASSIGNED, NEED_AXE, FIND_TREE, CHOP_TREE, COLLECT_WOOD, DEPOSIT }

@export var speed := 145.0
var inventory := ItemInventory.new()
var workplace: ContainerBuilding
var storehouse: ContainerBuilding
var work_state := WorkState.UNASSIGNED
var work_target: Node2D
var action_cooldown := 0.0
var status := "Unassigned"
var avoidance_time := 0.0
var avoidance_sign := 1.0
var navigation_cell_size := 40.0
var navigation_bounds := Rect2()
var building_path: PackedVector2Array = []
var building_path_index := 0
var building_path_target := Vector2(INF, INF)
var building_blocked_frames := 0

@onready var animated_sprite: AnimatedSprite2D = $AnimatedSprite2D


func _ready() -> void:
	inventory.max_capacity = 3
	input_pickable = true
	$SelectionArea.input_event.connect(_on_selection_input_event)


func configure(cell_size: float, available_storehouse: ContainerBuilding, map_rect: Rect2) -> void:
	storehouse = available_storehouse
	navigation_cell_size = cell_size
	navigation_bounds = map_rect
	animated_sprite.scale = Vector2.ONE * (cell_size / 400.0)
	animated_sprite.position.y = -cell_size * 0.5


func assign_to_forester(forester: ContainerBuilding) -> void:
	workplace = forester
	work_target = null
	_set_state(WorkState.NEED_AXE, "Assigned to Forester")


func _physics_process(delta: float) -> void:
	action_cooldown = maxf(0.0, action_cooldown - delta)
	avoidance_time = maxf(0.0, avoidance_time - delta)
	if workplace == null:
		_stop()
		return
	if inventory.total_count() >= inventory.max_capacity:
		_set_state(WorkState.DEPOSIT, "Returning to Forester")

	match work_state:
		WorkState.NEED_AXE:
			_fetch_axe()
		WorkState.FIND_TREE:
			_find_tree()
		WorkState.CHOP_TREE:
			_chop_tree()
		WorkState.COLLECT_WOOD:
			_collect_wood()
		WorkState.DEPOSIT:
			_deposit_wood()


func _fetch_axe() -> void:
	if inventory.has_item(&"axe"):
		inventory.equip(&"axe")
		_set_state(WorkState.FIND_TREE, "Searching for a tree")
		return
	if _move_to_building(storehouse):
		if storehouse.inventory.transfer_to(inventory, &"axe"):
			inventory.equip(&"axe")
			_set_state(WorkState.FIND_TREE, "Collected and equipped axe")
		else:
			_set_status("Waiting for an axe in Storehouse")


func _find_tree() -> void:
	work_target = _nearest_tree()
	if work_target == null:
		_set_status("No trees available")
		_stop()
	else:
		_set_state(WorkState.CHOP_TREE, "Walking to tree")


func _chop_tree() -> void:
	if not is_instance_valid(work_target) or work_target.is_queued_for_deletion():
		work_target = null
		_set_state(WorkState.COLLECT_WOOD, "Looking for dropped wood")
		return
	if _move_to(work_target.global_position, 52.0) and action_cooldown <= 0.0:
		work_target.interact(self)
		action_cooldown = 0.55


func _collect_wood() -> void:
	if inventory.total_count() >= inventory.max_capacity:
		_set_state(WorkState.DEPOSIT, "Inventory full")
		return
	if not is_instance_valid(work_target) or not (work_target is WorldItem) or work_target.item_id != &"wood":
		work_target = _nearest_wood()
	if work_target == null:
		_set_state(WorkState.FIND_TREE, "Searching for a tree")
		return
	if _move_to(work_target.global_position, 34.0):
		work_target.interact(self)
		work_target = null
		_set_state(WorkState.FIND_TREE, "Wood collected")


func _deposit_wood() -> void:
	if _move_to_building(workplace):
		var amount := inventory.count(&"wood")
		if amount > 0:
			inventory.transfer_to(workplace.inventory, &"wood", amount)
		_set_state(WorkState.FIND_TREE, "Wood deposited")


func _nearest_tree() -> ChoppableTree:
	var nearest: ChoppableTree
	var distance_limit := INF
	for node in get_tree().get_nodes_in_group(&"interactables"):
		if node is ChoppableTree:
			var distance := global_position.distance_squared_to(node.global_position)
			if distance < distance_limit:
				nearest = node
				distance_limit = distance
	return nearest


func _nearest_wood() -> WorldItem:
	var nearest: WorldItem
	var distance_limit := INF
	for node in get_tree().get_nodes_in_group(&"interactables"):
		if node is WorldItem and node.item_id == &"wood":
			var distance := global_position.distance_squared_to(node.global_position)
			if distance < distance_limit:
				nearest = node
				distance_limit = distance
	return nearest


func _move_to(destination: Vector2, arrival_distance: float) -> bool:
	var offset := destination - global_position
	if offset.length() <= arrival_distance:
		_stop()
		return true
	velocity = offset.normalized() * speed
	if avoidance_time > 0.0:
		velocity = velocity.rotated(avoidance_sign * PI * 0.5)
	if velocity.x < 0.0:
		animated_sprite.play(&"walk_left")
	elif velocity.x > 0.0:
		animated_sprite.play(&"walk_right")
	var before_move := global_position
	move_and_slide()
	if global_position.distance_squared_to(before_move) < 0.01 and avoidance_time <= 0.0:
		avoidance_sign *= -1.0
		avoidance_time = 0.65
	return false


func _move_to_building(building: ContainerBuilding) -> bool:
	var destination := building.get_interaction_position()
	if building.can_interact(self):
		building_path = []
		building_blocked_frames = 0
		_stop()
		return true
	if building_path.is_empty() or not building_path_target.is_equal_approx(destination):
		building_path = _make_collision_aware_path(destination)
		building_path_index = 0
		building_path_target = destination
	if building_path.is_empty():
		_stop()
		return false
	while building_path_index < building_path.size() - 1 and global_position.distance_to(building_path[building_path_index]) < navigation_cell_size * 0.18:
		building_path_index += 1
	var before_move := global_position
	_move_to_path_waypoint(building_path[building_path_index])
	if global_position.distance_squared_to(before_move) < 0.04:
		building_blocked_frames += 1
		if building_blocked_frames >= 20:
			# A collision changed or the sampled route was too tight. Rebuild from
			# the villager's current position instead of steering into the wall.
			building_path = []
			building_blocked_frames = 0
	else:
		building_blocked_frames = 0
	return false


func _move_to_path_waypoint(waypoint: Vector2) -> void:
	var offset := waypoint - global_position
	if offset.length() < navigation_cell_size * 0.08:
		_stop()
		return
	velocity = offset.normalized() * speed
	if velocity.x < 0.0:
		animated_sprite.play(&"walk_left")
	elif velocity.x > 0.0:
		animated_sprite.play(&"walk_right")
	move_and_slide()


func _make_collision_aware_path(destination: Vector2) -> PackedVector2Array:
	var grid := AStarGrid2D.new()
	var path_cell_size := navigation_cell_size * 0.5
	var grid_size := Vector2i(ceili(navigation_bounds.size.x / path_cell_size), ceili(navigation_bounds.size.y / path_cell_size))
	grid.region = Rect2i(Vector2i.ZERO, grid_size)
	grid.cell_size = Vector2.ONE * path_cell_size
	grid.offset = navigation_bounds.position + Vector2.ONE * path_cell_size * 0.5
	grid.diagonal_mode = AStarGrid2D.DIAGONAL_MODE_ONLY_IF_NO_OBSTACLES
	grid.update()

	var probe_shape := CircleShape2D.new()
	# Inflate obstacles by the villager body radius plus a small safety margin.
	probe_shape.radius = navigation_cell_size * 0.34
	var query := PhysicsShapeQueryParameters2D.new()
	query.shape = probe_shape
	query.collision_mask = 1
	query.exclude = [get_rid()]
	for y in grid_size.y:
		for x in grid_size.x:
			var cell := Vector2i(x, y)
			query.transform = Transform2D(0.0, grid.get_point_position(cell))
			if not get_world_2d().direct_space_state.intersect_shape(query, 1).is_empty():
				grid.set_point_solid(cell)

	var start := _world_to_navigation_cell(global_position, grid_size, path_cell_size)
	var desired_finish := _world_to_navigation_cell(destination, grid_size, path_cell_size)
	grid.set_point_solid(start, false)
	var finish := _nearest_open_cell(grid, desired_finish, grid_size)
	if finish.x < 0:
		return PackedVector2Array()
	var points := grid.get_point_path(start, finish)
	return points


func _nearest_open_cell(grid: AStarGrid2D, desired: Vector2i, grid_size: Vector2i) -> Vector2i:
	var best := Vector2i(-1, -1)
	var best_distance := INF
	for radius in range(0, 5):
		for y in range(desired.y - radius, desired.y + radius + 1):
			for x in range(desired.x - radius, desired.x + radius + 1):
				var candidate := Vector2i(x, y)
				if x < 0 or y < 0 or x >= grid_size.x or y >= grid_size.y or grid.is_point_solid(candidate):
					continue
				# This building convention places entrances on the bottom edge.
				# Prefer a clear cell directly below it over equally near side/top cells.
				var distance := float(candidate.distance_squared_to(desired) * 10 + absi(candidate.x - desired.x) * 3)
				if candidate.y < desired.y:
					distance += 1000.0
				if distance < best_distance:
					best = candidate
					best_distance = distance
		if best.x >= 0:
			return best
	return best


func _world_to_navigation_cell(world_position: Vector2, grid_size: Vector2i, path_cell_size: float) -> Vector2i:
	var local := (world_position - navigation_bounds.position) / path_cell_size
	return Vector2i(clampi(floori(local.x), 0, grid_size.x - 1), clampi(floori(local.y), 0, grid_size.y - 1))


func _stop() -> void:
	velocity = Vector2.ZERO
	animated_sprite.pause()


func _set_state(new_state: WorkState, message: String) -> void:
	work_state = new_state
	_set_status(message)


func _set_status(message: String) -> void:
	if status != message:
		status = message
		status_changed.emit()


func show_status(message: String) -> void:
	_set_status(message)


func _input_event(_viewport: Node, event: InputEvent, _shape_idx: int) -> void:
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.pressed:
		selected.emit(self)


func _on_selection_input_event(_viewport: Node, event: InputEvent, _shape_idx: int) -> void:
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.pressed:
		selected.emit(self)
