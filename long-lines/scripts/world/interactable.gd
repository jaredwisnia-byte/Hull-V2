class_name Interactable
extends StaticBody3D
## Anything the player can look at and act on. E = primary, R = secondary.

var persist_id := ""
var display_name := ""


func prompt_primary(_p: Node) -> String:
	return ""


func prompt_secondary(_p: Node) -> String:
	return ""


func primary(_p: Node) -> void:
	pass


func secondary(_p: Node) -> void:
	pass


## Mouse wheel / [ ] while looking at it. Return true if handled.
func scroll(_p: Node, _dir: int) -> bool:
	return false


## An extra status line shown under the prompt (e.g. a thermometer).
func info(_p: Node) -> String:
	return ""


func save_data() -> Dictionary:
	return {}


func load_data(_d: Dictionary) -> void:
	pass


func say(text: String) -> void:
	if text != "":
		Game.message.emit(text)
