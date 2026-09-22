class_name PrototypeWorldPopulator
extends Node

signal building_clicked(building: ContainerBuilding)

const VILLAGER_SCENE := preload("res://scenes/villager.tscn")
const FORESTER_SCENE := preload("res://scenes/buildings/forester.tscn")
const STOREHOUSE_SCENE := preload("res://scenes/buildings/storehouse.tscn")
const TREE_TEXTURES: Array[Texture2D] = [
	preload("res://assets/trees/tree_round_1.svg"),
	preload("res://assets/trees/tree_round_2.svg"),
	preload("res://assets/trees/tree_round_3.svg"),
	preload("res://assets/trees/tree_cone_1.svg"),
	preload("res://assets/trees/tree_cone_2.svg"),
	preload("res://assets/trees/tree_cone_3.svg"),
]

var forester: ContainerBuilding
var storehouse: ContainerBuilding
var villager: Villager
var _world: GameWorld


func populate(world: GameWorld) -> void:
	_world = world
	_build_trees()
	forester = _build_container_building(FORESTER_SCENE, Vector2i(18, 10))
	storehouse = _build_container_building(STOREHOUSE_SCENE, Vector2i(18, 13))
	_spawn_world_item(&"axe", Vector2i(13, 10))
	villager = _build_villager(Vector2i(16, 11))


func _build_trees() -> void:
	var cell_size := _world.terrain.map_data.cell_size
	for index in _world.terrain.map_data.tree_cells.size():
		var tree_cell := _world.terrain.map_data.tree_cells[index]
		var tree := ChoppableTree.new()
		tree.cell_size = cell_size
		tree.position = Vector2(tree_cell) * cell_size + Vector2.ONE * cell_size * 0.5
		tree.collision_layer = 1
		tree.collision_mask = 2

		var sprite := Sprite2D.new()
		sprite.texture = TREE_TEXTURES[_world.terrain.map_data.tree_variants[index] % TREE_TEXTURES.size()]
		# SVG anchor (20, 60) in an 80×80 canvas lands on the trunk origin.
		sprite.position = Vector2(cell_size * 0.5, -cell_size * 0.5)
		sprite.scale = Vector2.ONE * (cell_size / 40.0)
		sprite.texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR
		tree.add_child(sprite)

		var collision := CollisionShape2D.new()
		var trunk_shape := CircleShape2D.new()
		trunk_shape.radius = 17.0
		collision.shape = trunk_shape
		collision.position = Vector2(0, -2)
		tree.add_child(collision)
		_world.add_actor(tree)


func _build_container_building(scene: PackedScene, cell: Vector2i) -> ContainerBuilding:
	var cell_size := _world.terrain.map_data.cell_size
	var building: ContainerBuilding = scene.instantiate()
	building.configure_for_cell_size(cell_size)
	# Building coordinates identify the top-left tile of their footprint.
	building.position = Vector2(cell) * cell_size + Vector2(building.footprint_cells) * cell_size * 0.5
	building.clicked.connect(building_clicked.emit)
	_world.add_actor(building)
	return building


func _build_villager(cell: Vector2i) -> Villager:
	var cell_size := _world.terrain.map_data.cell_size
	var spawned_villager: Villager = VILLAGER_SCENE.instantiate()
	spawned_villager.position = Vector2(cell) * cell_size + Vector2.ONE * cell_size * 0.5
	_world.add_actor(spawned_villager)
	spawned_villager.configure(
		cell_size,
		storehouse,
		_world.terrain.get_map_rect(),
		_world.terrain,
	)
	return spawned_villager


func _spawn_world_item(item_id: StringName, cell: Vector2i, amount := 1) -> WorldItem:
	var cell_size := _world.terrain.map_data.cell_size
	var item := WorldItem.new()
	item.configure(item_id, amount, cell_size)
	item.position = Vector2(cell) * cell_size + Vector2.ONE * cell_size * 0.5
	_world.add_actor(item)
	return item
