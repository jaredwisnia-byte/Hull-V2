class_name AptAir
extends RefCounted
## Single-zone heat and carbon monoxide model for the apartment.
## Venting costs heat; sealing costs air.

var p: Dictionary
var indoor_temp := 17.5
var co_ppm := 0.0


func _init(params: Dictionary, start_temp: float) -> void:
	p = params
	indoor_temp = start_temp


func tick(dt_h: float, outdoor: float, open_windows: int, burners: int, candles: int) -> void:
	var k := float(p.loss_k) * (1.0 + open_windows * float(p.window_loss_mult))
	var floor_temp := outdoor + float(p.building_buffer)
	indoor_temp += (floor_temp - indoor_temp) * (1.0 - exp(-k * dt_h))
	indoor_temp += (burners * float(p.burner_heat) + candles * float(p.candle_heat)) * dt_h

	co_ppm += (burners * float(p.burner_co) + candles * float(p.candle_co)) * dt_h
	var vent := float(p.vent_base) + open_windows * float(p.vent_per_window)
	co_ppm -= co_ppm * (1.0 - exp(-vent * dt_h))
	co_ppm = maxf(co_ppm, 0.0)


## 0 none, 1 headache, 2 dizzy, 3 drowsy/confused
func co_stage() -> int:
	if co_ppm >= float(p.co_drowsy):
		return 3
	if co_ppm >= float(p.co_dizzy):
		return 2
	if co_ppm >= float(p.co_headache):
		return 1
	return 0


func to_dict() -> Dictionary:
	return {"indoor_temp": indoor_temp, "co_ppm": co_ppm}


func from_dict(d: Dictionary) -> void:
	indoor_temp = float(d.get("indoor_temp", indoor_temp))
	co_ppm = float(d.get("co_ppm", co_ppm))
