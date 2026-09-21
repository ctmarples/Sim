class_name InventoryPanel
extends PanelContainer

var inventory: PlayerInventory


func bind(player_inventory: PlayerInventory) -> void:
	inventory = player_inventory
	if not inventory.inventory_updated.is_connected(_refresh):
		inventory.inventory_updated.connect(_refresh)
	_refresh()


func toggle() -> void:
	visible = not visible


func _refresh() -> void:
	var item_list := $Margin/Rows/Items
	for child in item_list.get_children():
		child.queue_free()
	if inventory.item_ids().is_empty():
		var empty_label := Label.new()
		empty_label.text = "Empty"
		item_list.add_child(empty_label)
		return
	for raw_item_id in inventory.item_ids():
		var item_id := StringName(raw_item_id)
		var definition := ItemDatabase.definition(item_id)
		var row := HBoxContainer.new()
		var icon := TextureRect.new()
		icon.custom_minimum_size = Vector2(36, 36)
		icon.texture = definition.get("texture")
		icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		row.add_child(icon)
		var button := Button.new()
		var equipped: bool = inventory.equipped_item == item_id
		button.text = "%s  ×%d%s" % [ItemDatabase.display_name(item_id), inventory.count(item_id), "  [equipped]" if equipped else ""]
		button.disabled = not ItemDatabase.can_equip(item_id)
		button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		button.pressed.connect(_equip.bind(item_id))
		row.add_child(button)
		item_list.add_child(row)


func _equip(item_id: StringName) -> void:
	inventory.equip(item_id)
