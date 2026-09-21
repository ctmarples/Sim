class_name ChoppableTree
extends StaticBody2D

@export var hits_required := 3
var hits_remaining := 3
var cell_size := 40.0


func _ready() -> void:
	hits_remaining = hits_required
	add_to_group(&"interactables")


func interact(player: Player) -> void:
	if not player.inventory.equipped_supports(&"chop"):
		player.show_status("Equip an axe to chop")
		return
	hits_remaining -= 1
	player.show_status("Chopping tree… %d/%d" % [hits_required - hits_remaining, hits_required])
	var tween := create_tween()
	tween.tween_property(self, "rotation", 0.06, 0.06)
	tween.tween_property(self, "rotation", -0.06, 0.08)
	tween.tween_property(self, "rotation", 0.0, 0.06)
	if hits_remaining <= 0:
		tween.finished.connect(_fell)


func _fell() -> void:
	var pickup := WorldItem.new()
	pickup.configure(&"wood", 1, cell_size)
	get_parent().add_child(pickup)
	pickup.global_position = global_position
	queue_free()
