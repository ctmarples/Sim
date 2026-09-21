extends Node2D

const VILLAGER_SCENE := preload("res://scenes/villager.tscn")
const FORESTER_SCENE := preload("res://scenes/buildings/forester.tscn")
const STOREHOUSE_SCENE := preload("res://scenes/buildings/storehouse.tscn")
var forester: ContainerBuilding
var storehouse: ContainerBuilding
var villager: Villager
var pending_assignment: Villager

const RELIEF_TINT_SHADER := preload("res://shaders/relief_tint.gdshader")

const TREE_TEXTURES: Array[Texture2D] = [
	preload("res://assets/trees/tree_round_1.svg"),
	preload("res://assets/trees/tree_round_2.svg"),
	preload("res://assets/trees/tree_round_3.svg"),
	preload("res://assets/trees/tree_cone_1.svg"),
	preload("res://assets/trees/tree_cone_2.svg"),
	preload("res://assets/trees/tree_cone_3.svg"),
]
const TREE_CELLS := [
	Vector2i(2, 2), Vector2i(6, 2), Vector2i(10, 3),
	Vector2i(18, 2), Vector2i(23, 3), Vector2i(27, 2),
	Vector2i(2, 9), Vector2i(27, 8),
	Vector2i(3, 16), Vector2i(7, 17), Vector2i(12, 16),
	Vector2i(19, 17), Vector2i(24, 16), Vector2i(27, 17),
]

func _ready() -> void:
	_build_trees()
	forester = _build_container_building(FORESTER_SCENE, Vector2i(18, 10))
	storehouse = _build_container_building(STOREHOUSE_SCENE, Vector2i(18, 13))
	_spawn_world_item(&"axe", Vector2i(13, 10))
	_build_villager(Vector2i(16, 11))
	_configure_player_for_map()
	$HUD/InventoryPanel.bind($Actors/Player.inventory)
	$Actors/Player.inventory_toggle_requested.connect($HUD/InventoryPanel.toggle)
	$Actors/Player.container_open_requested.connect($HUD/InventoryPanel.open_container)
	$Actors/Player.status_requested.connect(_show_status)
	$HUD/VillagerPanel.bind([villager])
	$HUD/VillagerPanel.assignment_requested.connect(_begin_assignment)


func _process(_delta: float) -> void:
	_update_projected_actor_visuals()


func _update_projected_actor_visuals() -> void:
	var terrain: TerrainRenderer = $Ground/ProceduralTerrain
	for actor in $Actors.get_children():
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
		_apply_relief_tint(visual, terrain, terrain.projection_offset_at_global(projection_sample))
		if selection_area:
			_project_canvas_item(selection_area, projection_sample, terrain, &"projection_base_position")
		if actor is Player:
			actor.set_camera_projection_offset(terrain.projection_offset_at_global(projection_sample))


func _project_canvas_item(item: Node2D, logical_position: Vector2, terrain: TerrainRenderer, metadata_key: StringName) -> void:
	if not item.has_meta(metadata_key):
		item.set_meta(metadata_key, item.position)
	var base_position: Vector2 = item.get_meta(metadata_key)
	item.position = base_position + terrain.projection_offset_at_global(logical_position)


func _apply_relief_tint(item: CanvasItem, terrain: TerrainRenderer, projection_offset: Vector2) -> void:
	var shader_material := item.material as ShaderMaterial
	if shader_material == null or shader_material.shader != RELIEF_TINT_SHADER:
		shader_material = ShaderMaterial.new()
		shader_material.shader = RELIEF_TINT_SHADER
		item.material = shader_material
	shader_material.set_shader_parameter("relief_corner_map", terrain.relief_shade_texture)
	shader_material.set_shader_parameter("terrain_origin", terrain.global_position)
	shader_material.set_shader_parameter("terrain_grid_size", Vector2(terrain.map_data.columns, terrain.map_data.rows))
	shader_material.set_shader_parameter("terrain_cell_size", terrain.map_data.cell_size)
	shader_material.set_shader_parameter("projection_offset", projection_offset)


func _build_trees() -> void:
	var cell_size: float = $Ground/ProceduralTerrain.map_data.cell_size
	for index in TREE_CELLS.size():
		var tree := ChoppableTree.new()
		tree.cell_size = cell_size
		tree.position = Vector2(TREE_CELLS[index]) * cell_size + Vector2.ONE * cell_size * 0.5
		tree.collision_layer = 1
		tree.collision_mask = 2

		var sprite := Sprite2D.new()
		sprite.texture = TREE_TEXTURES[index % TREE_TEXTURES.size()]
		# SVG anchor (20, 60) in an 80×80 canvas lands on the trunk origin.
		sprite.position = Vector2(cell_size * 0.5, -cell_size * 0.5)
		# The SVG canvas is two cells tall; its trunk occupies the home cell.
		sprite.scale = Vector2.ONE * (cell_size / 40.0)
		sprite.texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR
		tree.add_child(sprite)

		var collision := CollisionShape2D.new()
		var trunk_shape := CircleShape2D.new()
		trunk_shape.radius = 17.0
		collision.shape = trunk_shape
		collision.position = Vector2(0, -2)
		tree.add_child(collision)
		$Actors.add_child(tree)


func _configure_player_for_map() -> void:
	var terrain: TerrainRenderer = $Ground/ProceduralTerrain
	$Actors/Player.configure_for_map(terrain.get_map_rect(), terrain.map_data.cell_size, terrain.get_projected_map_rect())
	$DebugOverlay.bind(terrain)


func _build_container_building(scene: PackedScene, cell: Vector2i) -> ContainerBuilding:
	var cell_size: float = $Ground/ProceduralTerrain.map_data.cell_size
	var building: ContainerBuilding = scene.instantiate()
	building.configure_for_cell_size(cell_size)
	# `cell` is the footprint's top-left tile; the scene origin is its centre.
	building.position = Vector2(cell) * cell_size + Vector2(building.footprint_cells) * cell_size * 0.5
	building.clicked.connect(_on_building_clicked)
	$Actors.add_child(building)
	return building


func _build_villager(cell: Vector2i) -> void:
	var cell_size: float = $Ground/ProceduralTerrain.map_data.cell_size
	villager = VILLAGER_SCENE.instantiate()
	villager.position = Vector2(cell) * cell_size + Vector2.ONE * cell_size * 0.5
	$Actors.add_child(villager)
	villager.configure(cell_size, storehouse, $Ground/ProceduralTerrain.get_map_rect())
	villager.selected.connect($HUD/VillagerPanel.select_villager)


func _begin_assignment(selected: Villager) -> void:
	pending_assignment = selected
	_show_status("Click the Forester to assign villager")


func _on_building_clicked(building: ContainerBuilding) -> void:
	if pending_assignment == null:
		return
	if building == forester:
		pending_assignment.assign_to_forester(forester)
		pending_assignment = null
		_show_status("Villager assigned to Forester")
	else:
		_show_status("This job must be assigned to the Forester")


func _spawn_world_item(item_id: StringName, cell: Vector2i, amount := 1) -> void:
	var cell_size: float = $Ground/ProceduralTerrain.map_data.cell_size
	var item := WorldItem.new()
	item.configure(item_id, amount, cell_size)
	item.position = Vector2(cell) * cell_size + Vector2.ONE * cell_size * 0.5
	$Actors.add_child(item)


func _show_status(message: String) -> void:
	$HUD/Status.text = message
	$HUD/Status.visible = true
	$HUD/StatusTimer.start()


func _on_status_timer_timeout() -> void:
	$HUD/Status.visible = false
