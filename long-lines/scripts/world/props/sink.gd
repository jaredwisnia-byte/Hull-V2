class_name Sink
extends Interactable


func prompt_primary(_p: Node) -> String:
	return "Drink from the tap"


func primary(_p: Node) -> void:
	say(Game.drink_from_tap())


func prompt_secondary(_p: Node) -> String:
	return "Fill empty containers"


func secondary(_p: Node) -> void:
	say(Game.fill_containers())
