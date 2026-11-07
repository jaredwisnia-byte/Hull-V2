class_name ContainerProp
extends Interactable
## Opens a container's contents in the HUD. The fridge has two: the fridge
## (E) and the freezer (R).

var cid := ""
var title := ""
var verb := "Search"
var cid2 := ""
var title2 := ""
var verb2 := ""


func prompt_primary(_p: Node) -> String:
	return "%s (%d)" % [verb, Game.container_contents(cid).size()]


func primary(p: Node) -> void:
	Game.on_container_opened(cid)
	p.hud.open_container(cid, title)


func prompt_secondary(_p: Node) -> String:
	if cid2 == "":
		return ""
	return "%s (%d)" % [verb2, Game.container_contents(cid2).size()]


func secondary(p: Node) -> void:
	if cid2 == "":
		return
	Game.on_container_opened(cid2)
	p.hud.open_container(cid2, title2)


func info(_p: Node) -> String:
	if cid == "fridge":
		var f := Game.fridge
		var fz := "frozen" if f.freezer_frozen() else "thawing"
		return "Dead since 1 a.m. Fridge about %d C, freezer %s." % [roundi(f.fridge_temp), fz]
	return ""
