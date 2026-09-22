class_name Game
extends Node

var forester: ContainerBuilding
var storehouse: ContainerBuilding
var villager: Villager
var pending_assignment: Villager

@onready var world: GameWorld = $World
@onready var hud: GameHUD = $HUD


func _ready() -> void:
	world.population.populate(world)
	forester = world.population.forester
	storehouse = world.population.storehouse
	villager = world.population.villager
	_configure_player_for_map()
	hud.bind(world.player.inventory, [villager])
	world.player.inventory_toggle_requested.connect(hud.toggle_inventory)
	world.player.container_open_requested.connect(hud.open_container)
	world.player.status_requested.connect(hud.show_status)
	hud.assignment_requested.connect(_begin_assignment)
	world.population.building_clicked.connect(_on_building_clicked)
	villager.selected.connect(hud.select_villager)


func _process(_delta: float) -> void:
	_update_projected_actor_visuals()


func _update_projected_actor_visuals() -> void:
	var terrain := world.terrain
	for actor in world.actors.get_children():
		var dynamic_projection := actor is Player or actor is Villager
		if not dynamic_projection and actor.has_meta(&"terrain_projection_complete"):
			continue
		var visual: Node2D
		var selection_area: Node2D
		var projection_sample: Vector2 = (actor as Node2D).global_position
		if actor is Player or actor is Villager:
			visual = actor.get_node_or_null("AnimatedSprite2D")
			selection_area = actor.get_node_or_null("SelectionArea")
		elif actor is ContainerBuilding:
			visual = actor.get_node_or_null("Visual")
			selection_area = actor.get_node_or_null("SelectionArea")
			projection_sample = actor.get_interaction_position()
		elif actor is ChoppableTree or actor is WorldItem:
			for child in actor.get_children():
				if child is Sprite2D:
					visual = child
					break
		if visual == null:
			continue
		_project_canvas_item(visual, projection_sample, terrain, &"projection_base_position")
		if selection_area:
			_project_canvas_item(selection_area, projection_sample, terrain, &"projection_base_position")
		if actor is Player:
			actor.set_camera_projection_offset(terrain.projection_offset_at_global(projection_sample))
		if not dynamic_projection:
			actor.set_meta(&"terrain_projection_complete", true)


func _project_canvas_item(item: Node2D, logical_position: Vector2, terrain: TerrainRenderer, metadata_key: StringName) -> void:
	if not item.has_meta(metadata_key):
		item.set_meta(metadata_key, item.position)
	var position_key := StringName(String(metadata_key) + "_logical_position")
	if item.has_meta(position_key):
		var previous_position: Vector2 = item.get_meta(position_key)
		if previous_position.is_equal_approx(logical_position):
			return
	item.set_meta(position_key, logical_position)
	var base_position: Vector2 = item.get_meta(metadata_key)
	item.position = base_position + terrain.projection_offset_at_global(logical_position)
	item.z_index = 3 if terrain.should_actor_render_above_cliff(logical_position) else 0


func _configure_player_for_map() -> void:
	var terrain := world.terrain
	world.player.configure_for_map(terrain.get_map_rect(), terrain.map_data.cell_size, terrain.get_projected_map_rect(), terrain)
	world.debug_overlay.bind(terrain)


func _begin_assignment(selected: Villager) -> void:
	pending_assignment = selected
	hud.show_status("Click the Forester to assign villager")


func _on_building_clicked(building: ContainerBuilding) -> void:
	if pending_assignment == null:
		return
	if building == forester:
		pending_assignment.assign_to_forester(forester)
		pending_assignment = null
		hud.show_status("Villager assigned to Forester")
	else:
		hud.show_status("This job must be assigned to the Forester")
