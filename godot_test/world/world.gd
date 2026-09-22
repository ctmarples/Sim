class_name GameWorld
extends Node2D

@onready var terrain: TerrainRenderer = $Ground/ProceduralTerrain
@onready var actors: Node2D = $Actors
@onready var player: Player = $Actors/Player
@onready var debug_overlay: DebugOverlay = $DebugOverlay
@onready var population: PrototypeWorldPopulator = $Population


func add_actor(actor: Node2D) -> void:
	actors.add_child(actor)
