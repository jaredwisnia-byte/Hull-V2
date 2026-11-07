class_name Bed
extends Interactable


func prompt_primary(_p: Node) -> String:
	return "Sleep"


func primary(p: Node) -> void:
	p.hud.open_sleep()


func info(_p: Node) -> String:
	if Game.air.co_stage() >= 1:
		return "Your head is pounding. Sleeping in this air would be a mistake."
	return ""
