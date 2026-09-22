class_name ItemInventory
extends Resource

signal inventory_updated

var items: Dictionary = {}
var equipped_item: StringName = &""
var max_capacity := -1


func add_item(item_id: StringName, amount := 1) -> bool:
	if not can_add(amount):
		return false
	items[item_id] = count(item_id) + amount
	inventory_updated.emit()
	return true


func remove_item(item_id: StringName, amount := 1) -> bool:
	if not has_item(item_id, amount):
		return false
	var remaining := count(item_id) - amount
	if remaining <= 0:
		items.erase(item_id)
		if equipped_item == item_id:
			equipped_item = &""
	else:
		items[item_id] = remaining
	inventory_updated.emit()
	return true


func transfer_to(target: ItemInventory, item_id: StringName, amount := 1) -> bool:
	if not target.can_add(amount):
		return false
	if not remove_item(item_id, amount):
		return false
	target.add_item(item_id, amount)
	return true


func has_item(item_id: StringName, amount := 1) -> bool:
	return count(item_id) >= amount


func count(item_id: StringName) -> int:
	return int(items.get(item_id, 0))


func total_count() -> int:
	var total := 0
	for amount in items.values():
		total += int(amount)
	return total


func can_add(amount := 1) -> bool:
	return max_capacity < 0 or total_count() + amount <= max_capacity


func item_ids() -> Array:
	var result := items.keys()
	result.sort_custom(func(a, b): return ItemDatabase.display_name(a) < ItemDatabase.display_name(b))
	return result


func equip(item_id: StringName) -> bool:
	if not has_item(item_id) or not ItemDatabase.can_equip(item_id):
		return false
	equipped_item = item_id
	inventory_updated.emit()
	return true


func equipped_supports(action: StringName) -> bool:
	return equipped_item != &"" and ItemDatabase.supports_action(equipped_item, action)
