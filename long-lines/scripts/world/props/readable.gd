class_name Readable
extends Interactable

var doc_id := ""
var verb := "Read"


func prompt_primary(_p: Node) -> String:
	return "%s the %s" % [verb, display_name]


func primary(p: Node) -> void:
	p.hud.open_reader(doc_id)
