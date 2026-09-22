class_name GameHUD
extends CanvasLayer

signal assignment_requested(villager: Villager)

@onready var inventory_panel: InventoryPanel = $InventoryPanel
@onready var villager_panel: VillagerPanel = $VillagerPanel
@onready var status_label: Label = $Status
@onready var status_timer: Timer = $StatusTimer


func _ready() -> void:
	villager_panel.assignment_requested.connect(assignment_requested.emit)


func bind(player_inventory: ItemInventory, villagers: Array) -> void:
	inventory_panel.bind(player_inventory)
	villager_panel.bind(villagers)


func toggle_inventory() -> void:
	inventory_panel.toggle()


func open_container(inventory: ItemInventory, display_name: String) -> void:
	inventory_panel.open_container(inventory, display_name)


func select_villager(villager: Villager) -> void:
	villager_panel.select_villager(villager)


func show_status(message: String) -> void:
	status_label.text = message
	status_label.visible = true
	status_timer.start()


func _on_status_timer_timeout() -> void:
	status_label.visible = false
