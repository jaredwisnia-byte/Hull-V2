class_name CoatHook
extends Interactable

var coat: Node3D


func _ready() -> void:
	add_to_group("persist")


func prompt_primary(_p: Node) -> String:
	return "Hang up your coat" if Game.wearing_coat else "Put on your pea coat"


func primary(_p: Node) -> void:
	Game.wearing_coat = not Game.wearing_coat
	if coat:
		coat.visible = not Game.wearing_coat
	say("You button up the wool pea coat from the surplus store. Better." if Game.wearing_coat else "You hang the coat back on its hook.")


func save_data() -> Dictionary:
	return {}


func _process(_d: float) -> void:
	if coat:
		coat.visible = not Game.wearing_coat
