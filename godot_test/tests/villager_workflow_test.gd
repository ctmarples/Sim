extends SceneTree


func _init() -> void:
	var scene: Node = load("res://scenes/game.tscn").instantiate()
	root.add_child(scene)
	await process_frame
	# Bypass UI only; exercise the same assignment and inventory/job paths.
	scene.storehouse.inventory.add_item(&"axe")
	scene.villager.assign_to_forester(scene.forester)
	for frame in 1800:
		await process_frame
		if frame % 120 == 0:
			print("frame=", frame, " state=", scene.villager.work_state,
				" status=", scene.villager.status, " pos=", scene.villager.position,
				" carried=", scene.villager.inventory.items,
				" deposited=", scene.forester.inventory.items)
	print("FINAL status=", scene.villager.status, " carried=", scene.villager.inventory.items,
		" deposited=", scene.forester.inventory.items)
	quit()
