class_name ItemDatabase
extends RefCounted

const ITEMS := {
	&"axe": {
		"name": "Axe",
		"texture": preload("res://assets/items/axe.svg"),
		"equippable": true,
		"actions": [&"chop"],
	},
	&"wood": {
		"name": "Wood",
		"texture": preload("res://assets/items/wood.svg"),
		"equippable": false,
		"actions": [],
	},
}


static func definition(item_id: StringName) -> Dictionary:
	return ITEMS.get(item_id, {})


static func display_name(item_id: StringName) -> String:
	return str(definition(item_id).get("name", item_id))


static func can_equip(item_id: StringName) -> bool:
	return bool(definition(item_id).get("equippable", false))


static func supports_action(item_id: StringName, action: StringName) -> bool:
	return action in definition(item_id).get("actions", [])
