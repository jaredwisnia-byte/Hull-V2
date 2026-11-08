class_name GasRange
extends Interactable
## The gas range still works: gas mains don't need Con Ed's electricity and the
## pilot lights stayed lit. It cooks, and it heats, and it fills the room with
## carbon monoxide if you shut the windows.

var flames: Array = []   # MeshInstance3D per burner
var glow: OmniLight3D


func _ready() -> void:
	add_to_group("persist")
	_refresh()


func prompt_primary(_p: Node) -> String:
	if Game.burners >= 4:
		return "Turn all the burners off"
	return "Light a burner (%d of 4 lit)" % Game.burners


func primary(_p: Node) -> void:
	if Game.burners >= 4:
		Game.set_burners(0)
		say("You turn the knobs back. The blue rings vanish.")
	else:
		Game.set_burners(Game.burners + 1)
		if Game.burners == 1:
			say("The pilot catches with a soft whump. Gas pressure is still there.")
	_refresh()


func prompt_secondary(_p: Node) -> String:
	if Game.burners == 0:
		return ""
	return "Cook or brew"


func secondary(_p: Node) -> void:
	say(Game.cook())


func info(_p: Node) -> String:
	if Game.burners > 0:
		return "%d burner%s lit. Air: %s." % [Game.burners, "" if Game.burners == 1 else "s", _air_text()]
	return ""


func _air_text() -> String:
	match Game.air.co_stage():
		0:
			return "seems fine"
		1:
			return "stuffy"
		2:
			return "close and sickly"
	return "poisonous"


func _refresh() -> void:
	for i in flames.size():
		flames[i].visible = i < Game.burners
	if glow:
		glow.visible = Game.burners > 0
		glow.light_energy = 0.08 * Game.burners


func _process(_d: float) -> void:
	_refresh()
	var p := get_tree().get_first_node_in_group("player") as Node3D
	Game.near_stove = p != null and p.global_position.distance_to(global_position) < 1.6


func save_data() -> Dictionary:
	return {}
