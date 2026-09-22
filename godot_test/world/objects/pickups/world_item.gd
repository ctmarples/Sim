class_name WorldItem
extends Area2D

var item_id: StringName
var amount := 1
var cell_size := 40.0


func configure(new_item_id: StringName, new_amount := 1, new_cell_size := 40.0) -> void:
	item_id = new_item_id
	amount = new_amount
	cell_size = new_cell_size


func _ready() -> void:
	add_to_group(&"interactables")
	collision_layer = 0
	collision_mask = 0
	var definition := ItemDatabase.definition(item_id)
	var sprite := Sprite2D.new()
	sprite.texture = definition.get("texture")
	sprite.scale = Vector2.ONE * (cell_size / 400.0)
	sprite.position.y = -cell_size * 0.25
	add_child(sprite)


func interact(actor: Node) -> void:
	if actor.inventory.add_item(item_id, amount):
		actor.show_status("Picked up %s" % ItemDatabase.display_name(item_id))
		queue_free()
	else:
		actor.show_status("Inventory is full")
