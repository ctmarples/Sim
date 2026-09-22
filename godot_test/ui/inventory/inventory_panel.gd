class_name InventoryPanel
extends PanelContainer

var player_inventory: ItemInventory
var container_inventory: ItemInventory


func bind(inventory: ItemInventory) -> void:
	player_inventory = inventory
	_connect_inventory(player_inventory)
	_refresh()


func toggle() -> void:
	if visible:
		visible = false
		return
	close_container()
	visible = true


func open_container(inventory: ItemInventory, display_name: String) -> void:
	if container_inventory != null and container_inventory.inventory_updated.is_connected(_refresh):
		container_inventory.inventory_updated.disconnect(_refresh)
	container_inventory = inventory
	_connect_inventory(container_inventory)
	$Margin/Root/Panes/ContainerPane/Name.text = display_name
	$Margin/Root/Panes/ContainerPane.visible = true
	$Margin/Root/Hint.text = "Click an item to transfer one"
	visible = true
	_refresh()


func close_container() -> void:
	if container_inventory != null and container_inventory.inventory_updated.is_connected(_refresh):
		container_inventory.inventory_updated.disconnect(_refresh)
	container_inventory = null
	$Margin/Root/Panes/ContainerPane.visible = false
	$Margin/Root/Hint.text = "Click a tool to equip it"
	_refresh()


func _connect_inventory(inventory: ItemInventory) -> void:
	if not inventory.inventory_updated.is_connected(_refresh):
		inventory.inventory_updated.connect(_refresh)


func _refresh() -> void:
	if player_inventory == null:
		return
	_populate($Margin/Root/Panes/PlayerPane/Items, player_inventory, true)
	if container_inventory != null:
		_populate($Margin/Root/Panes/ContainerPane/Items, container_inventory, false)


func _populate(item_list: VBoxContainer, source: ItemInventory, source_is_player: bool) -> void:
	for child in item_list.get_children():
		child.queue_free()
	if source.item_ids().is_empty():
		var empty_label := Label.new()
		empty_label.text = "Empty"
		item_list.add_child(empty_label)
		return
	for raw_item_id in source.item_ids():
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
		var equipped: bool = source_is_player and player_inventory.equipped_item == item_id
		button.text = "%s  ×%d%s" % [ItemDatabase.display_name(item_id), source.count(item_id), "  [equipped]" if equipped else ""]
		button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		if container_inventory == null:
			button.disabled = not ItemDatabase.can_equip(item_id)
			button.pressed.connect(_equip.bind(item_id))
		else:
			button.pressed.connect(_transfer.bind(source_is_player, item_id))
		row.add_child(button)
		item_list.add_child(row)


func _equip(item_id: StringName) -> void:
	player_inventory.equip(item_id)


func _transfer(from_player: bool, item_id: StringName) -> void:
	if from_player:
		player_inventory.transfer_to(container_inventory, item_id)
	else:
		container_inventory.transfer_to(player_inventory, item_id)
