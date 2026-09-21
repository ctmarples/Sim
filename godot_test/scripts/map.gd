extends Node2D

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
	_spawn_world_item(&"axe", Vector2i(13, 10))
	_configure_player_for_map()
	$HUD/InventoryPanel.bind($Actors/Player.inventory)
	$Actors/Player.inventory_toggle_requested.connect($HUD/InventoryPanel.toggle)
	$Actors/Player.status_requested.connect(_show_status)


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
	$Actors/Player.configure_for_map(terrain.get_map_rect(), terrain.map_data.cell_size)


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
