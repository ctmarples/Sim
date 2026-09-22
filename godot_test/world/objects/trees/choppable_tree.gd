class_name ChoppableTree
extends StaticBody2D

@export var hits_required := 3
var hits_remaining := 3
var cell_size := 40.0
var falling := false


func _ready() -> void:
	hits_remaining = hits_required
	add_to_group(&"interactables")


func interact(actor: Node) -> void:
	if falling:
		return
	if not actor.inventory.equipped_supports(&"chop"):
		actor.show_status("Equip an axe to chop")
		return
	hits_remaining -= 1
	actor.show_status("Chopping tree… %d/%d" % [hits_required - hits_remaining, hits_required])
	var tween := create_tween()
	tween.tween_property(self, "rotation", 0.06, 0.06)
	tween.tween_property(self, "rotation", -0.06, 0.08)
	tween.tween_property(self, "rotation", 0.0, 0.06)
	if hits_remaining <= 0:
		falling = true
		remove_from_group(&"interactables")
		tween.finished.connect(_fell)


func _fell() -> void:
	var pickup := WorldItem.new()
	pickup.configure(&"wood", 1, cell_size)
	get_parent().add_child(pickup)
	pickup.global_position = global_position
	queue_free()
