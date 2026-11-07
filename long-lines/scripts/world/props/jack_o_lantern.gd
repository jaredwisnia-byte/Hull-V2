class_name JackOLantern
extends Carriable
## Carved on Wednesday for Terry. It rots over the first week, one of the
## game's visual clocks.

var body: MeshInstance3D
var stage := -1


func prompt_primary(_p: Node) -> String:
	return "Look at the jack-o'-lantern"


func primary(_p: Node) -> void:
	match stage:
		0:
			say("You carved it Wednesday night so Terry would laugh. The candle inside burned out sometime after the lights went.")
		1:
			say("The face is starting to sag. It smells sweet and wrong.")
		2:
			say("The grin has caved in on one side. Fruit flies, even now.")
		_:
			say("A collapsed brown thing with a face. It's been a long week.")


func _process(_d: float) -> void:
	var day := Game.clock.day()
	var s := 0 if day <= 1 else (1 if day <= 3 else (2 if day <= 5 else 3))
	if s == stage or body == null:
		return
	stage = s
	var mats := ["pumpkin", "pumpkin_soft", "pumpkin_soft", "pumpkin_rot"]
	body.material_override = Geo.mat(mats[s])
	body.scale = Vector3(1.0, [1.0, 0.92, 0.8, 0.6][s], 1.0)
