class_name PlayerInventory
extends Resource

signal inventory_updated

var items: Dictionary = {}
var equipped_item: StringName = &""


func add_item(item_id: StringName, amount := 1) -> void:
	items[item_id] = count(item_id) + amount
	inventory_updated.emit()


func has_item(item_id: StringName, amount := 1) -> bool:
	return count(item_id) >= amount


func count(item_id: StringName) -> int:
	return int(items.get(item_id, 0))


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
