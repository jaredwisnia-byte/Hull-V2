class_name KitchenTub
extends Interactable
## The bathtub in the kitchen, with a board lid that doubles as a counter.

var water: MeshInstance3D


func prompt_primary(_p: Node) -> String:
	return "Scoop water from the tub" if Game.tub_full else "Fill the tub from the tap (25 min)"


func primary(_p: Node) -> void:
	if Game.tub_full:
		say(Game.scoop_from_tub())
	else:
		say(Game.fill_tub())
	_refresh()


func info(_p: Node) -> String:
	return "The tub is full of water." if Game.tub_full else "A tub in the kitchen, lid down. Doubles as a counter."


func _refresh() -> void:
	if water:
		water.visible = Game.tub_full


func _process(_d: float) -> void:
	_refresh()
