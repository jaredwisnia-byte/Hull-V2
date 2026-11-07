class_name ColdChain
extends RefCounted
## The medicine cooler: an insulated box, some ice, sixty vials, and a dial
## thermometer. Vials lose potency above 8 C and are ruined by freezing.

var p: Dictionary
var temp := 3.4
var ice_kg := 0.75
var vials := 60
var potency := 100.0


func _init(params: Dictionary) -> void:
	p = params
	temp = float(p.start_temp)
	ice_kg = float(p.start_ice_kg)
	vials = int(p.vials)


func tick(dt_h: float, ambient: float) -> void:
	var target := ambient
	if ice_kg > 0.0 and ambient > 0.0:
		ice_kg = maxf(0.0, ice_kg - ambient * float(p.melt_k) * dt_h)
		target = 1.0 + ambient * 0.05
	temp += (target - temp) * (1.0 - exp(-dt_h / float(p.tau_h)))
	if temp > float(p.safe_max):
		potency -= (temp - float(p.safe_max)) * float(p.heat_loss_per_degree_h) * dt_h
	elif temp < 0.0:
		potency -= float(p.freeze_loss_per_h) * minf(1.0, -temp / 2.0) * dt_h
	potency = clampf(potency, 0.0, 100.0)


func add_ice(kg: float) -> void:
	ice_kg += kg


func status() -> String:
	if temp < 0.0:
		return "FREEZING"
	if temp < float(p.safe_min):
		return "cold"
	if temp <= float(p.safe_max):
		return "safe"
	return "TOO WARM"


func ice_text() -> String:
	if ice_kg <= 0.0:
		return "no ice left, just cold water"
	if ice_kg < 0.2:
		return "a few slivers of ice"
	if ice_kg < 0.5:
		return "ice half melted"
	return "plenty of ice"


func to_dict() -> Dictionary:
	return {"temp": temp, "ice_kg": ice_kg, "vials": vials, "potency": potency}


func from_dict(d: Dictionary) -> void:
	temp = float(d.get("temp", temp))
	ice_kg = float(d.get("ice_kg", ice_kg))
	vials = int(d.get("vials", vials))
	potency = float(d.get("potency", potency))
