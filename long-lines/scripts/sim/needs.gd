class_name Needs
extends RefCounted
## The five survival meters plus morale, 0..100.

const KEYS := ["warmth", "food", "water", "rest", "condition", "morale"]

var v := {}
var p: Dictionary
var last_cause := ""


func _init(params: Dictionary, start: Dictionary) -> void:
	p = params
	for k in KEYS:
		v[k] = float(start.get(k, 60.0))


## felt_temp is the room temperature plus clothing and heat bonuses.
func felt_temp(room_temp: float, coat: bool, asleep: bool, near_stove: bool) -> float:
	var t := room_temp + float(p.clothing_base)
	if coat:
		t += float(p.coat_bonus)
	if asleep:
		t += float(p.blanket_bonus)
	if near_stove:
		t += float(p.near_stove_bonus)
	return t


func tick(dt_h: float, ctx: Dictionary) -> void:
	var asleep: bool = ctx.get("asleep", false)
	var felt: float = ctx.get("felt_temp", 18.0)
	var co: float = ctx.get("co_ppm", 0.0)
	var light: float = ctx.get("light", 1.0)
	var radio_on: bool = ctx.get("radio_on", false)
	var dose_debt: float = ctx.get("dose_debt", 0.0)
	var co_p: Dictionary = ctx.get("air_params", {})

	# Warmth
	var comfort := float(p.comfort_temp)
	if felt >= comfort:
		v.warmth += minf((felt - comfort + 2.0) * float(p.warm_gain_per_degree), float(p.warm_gain_max)) * dt_h
	else:
		v.warmth -= (comfort - felt) * float(p.cold_loss_per_degree) * dt_h

	# Food, water, rest
	var cold_mult: float = float(p.cold_hunger_mult) if felt < comfort - 4.0 else 1.0
	var food_rate := float(p.food_per_h) * cold_mult * (float(p.asleep_food_mult) if asleep else 1.0)
	var water_rate := float(p.water_per_h) * (float(p.asleep_water_mult) if asleep else 1.0)
	v.food -= food_rate * dt_h
	v.water -= water_rate * dt_h
	if asleep:
		v.rest += float(p.rest_asleep_per_h) * dt_h
	else:
		var co_tired := 1.5 if co > float(co_p.get("co_dizzy", 150.0)) else 1.0
		v.rest -= float(p.rest_awake_per_h) * co_tired * dt_h

	_clamp()

	# Condition
	var damage := {}
	if v.food <= 0.0:
		damage["starvation"] = float(p.starving_damage_per_h)
	if v.water <= 0.0:
		damage["dehydration"] = float(p.thirst_damage_per_h)
	if v.rest <= 0.0:
		damage["exhaustion"] = float(p.exhausted_damage_per_h)
	if v.warmth <= 0.0:
		damage["hypothermia"] = float(p.hypothermia_damage_per_h)
	var co_from := float(co_p.get("co_damage_from", 100.0))
	if co > co_from:
		var mult: float = float(co_p.get("co_asleep_damage_mult", 3.0)) if asleep else 1.0
		damage["carbon monoxide poisoning"] = (co - co_from) * float(co_p.get("co_damage_per_ppm_h", 0.045)) * mult
	if dose_debt > 0.0:
		damage["fever from missed doses"] = dose_debt * float(p.fever_per_missed_dose_per_h)

	var total := 0.0
	var worst := 0.0
	for cause in damage:
		total += damage[cause]
		if damage[cause] > worst:
			worst = damage[cause]
			last_cause = cause
	if total > 0.0:
		v.condition -= total * dt_h
	elif v.food > 20.0 and v.water > 20.0 and v.warmth > 30.0:
		v.condition += (float(p.regen_asleep_per_h) if asleep else float(p.regen_per_h)) * dt_h

	# Morale drifts toward a target set by the room and the body.
	var target := 50.0
	target += lerpf(-18.0, 6.0, clampf(light, 0.0, 1.0))
	if radio_on:
		target += 10.0
	if v.food < 20.0:
		target -= 12.0
	if v.water < 20.0:
		target -= 10.0
	if v.warmth < 35.0:
		target -= 12.0
	if v.condition < 50.0:
		target -= 10.0
	if dose_debt > 0.0:
		target -= 8.0
	if not asleep:
		v.morale += clampf(target - v.morale, -1.0, 1.0) * float(p.morale_drift_per_h) * dt_h
	_clamp()


func add(k: String, amount: float) -> void:
	v[k] = clampf(v[k] + amount, 0.0, 100.0)


func _clamp() -> void:
	for k in KEYS:
		v[k] = clampf(v[k], 0.0, 100.0)
