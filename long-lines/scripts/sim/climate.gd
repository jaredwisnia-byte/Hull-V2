class_name Climate
extends RefCounted
## Reads the day-by-day design curve. Lows land at 6 a.m., highs at 3 p.m.,
## with a cosine ease between them.

var days: Array = []
var sunrise := 6.42
var sunset := 16.92
var max_elevation_deg := 34.0


func _init(data: Dictionary) -> void:
	days = data.get("days", [])
	sunrise = float(data.get("sunrise", sunrise))
	sunset = float(data.get("sunset", sunset))
	max_elevation_deg = float(data.get("max_elevation_deg", max_elevation_deg))


func day_data(d: int) -> Dictionary:
	if days.is_empty():
		return {"high": 12.0, "low": 6.0, "light": 1.0, "haze": 0.0}
	return days[clampi(d, 1, days.size()) - 1]


func outdoor_temp(minutes: float) -> float:
	var h := minutes / 60.0
	var d := int(floor(h / 24.0)) + 1
	var hod := h - (d - 1) * 24.0
	var a_t: float
	var a_v: float
	var b_t: float
	var b_v: float
	if hod < 6.0:
		a_t = (d - 2) * 24.0 + 15.0
		a_v = float(day_data(d - 1).high)
		b_t = (d - 1) * 24.0 + 6.0
		b_v = float(day_data(d).low)
	elif hod < 15.0:
		a_t = (d - 1) * 24.0 + 6.0
		a_v = float(day_data(d).low)
		b_t = (d - 1) * 24.0 + 15.0
		b_v = float(day_data(d).high)
	else:
		a_t = (d - 1) * 24.0 + 15.0
		a_v = float(day_data(d).high)
		b_t = d * 24.0 + 6.0
		b_v = float(day_data(d + 1).low)
	var f := clampf((h - a_t) / (b_t - a_t), 0.0, 1.0)
	f = 0.5 - 0.5 * cos(PI * f)
	return lerpf(a_v, b_v, f)


## 0 at night, up to the day's light factor at noon.
func daylight(minutes: float) -> float:
	var d := int(floor(minutes / 1440.0)) + 1
	var hod := fposmod(minutes, 1440.0) / 60.0
	var up := smoothstep(sunrise - 0.6, sunrise + 0.7, hod)
	var down := 1.0 - smoothstep(sunset - 0.7, sunset + 0.8, hod)
	return up * down * float(day_data(d).get("light", 1.0))


## 0 at sunrise, 1 at sunset; outside that range the sun is down.
func sun_progress(minutes: float) -> float:
	var hod := fposmod(minutes, 1440.0) / 60.0
	return (hod - sunrise) / (sunset - sunrise)
