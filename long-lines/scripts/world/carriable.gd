class_name Carriable
extends Interactable
## A prop you can pick up (R), carry, and set down on any flat surface (E).
## Big things take both hands: no flashlight while you carry them.

var two_handed := false
var spawned := false
var prop_type := ""
var held := false
var doc_id := ""
var world_parent: Node3D
var _layer := 1


func _ready() -> void:
	add_to_group("persist")
	world_parent = get_parent()
	_layer = collision_layer


func prompt_primary(_p: Node) -> String:
	if doc_id != "":
		return "Look at the %s" % display_name
	return ""


func primary(p: Node) -> void:
	if doc_id != "":
		p.hud.open_reader(doc_id)


func prompt_secondary(p: Node) -> String:
	if p.held == null:
		return "Pick up the %s" % display_name
	return ""


func secondary(p: Node) -> void:
	if p.held == null:
		p.pick_up(self)


func set_held(on: bool) -> void:
	held = on
	collision_layer = 0 if on else _layer
	if on:
		on_picked_up()
	else:
		on_placed()


func on_picked_up() -> void:
	pass


func on_placed() -> void:
	pass


func save_data() -> Dictionary:
	var t := global_transform
	return {
		"pos": [t.origin.x, t.origin.y, t.origin.z],
		"rot_y": global_rotation.y,
		"held": held,
		"spawned": spawned,
		"type": prop_type,
	}


func load_data(d: Dictionary) -> void:
	var player := get_tree().get_first_node_in_group("player")
	if held and player:
		player.force_release(self)
	if d.has("pos"):
		var pos: Array = d.pos
		global_position = Vector3(pos[0], pos[1], pos[2])
		global_rotation = Vector3(0, float(d.get("rot_y", 0.0)), 0)
	if d.get("held", false) and player:
		player.pick_up(self, true)
	else:
		on_placed()
