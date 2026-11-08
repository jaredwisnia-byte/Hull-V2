class_name Screenshots
extends RefCounted
## Renders the slice from fixed viewpoints at chosen times of day.
## Run with a display (e.g. xvfb-run):  godot -- --shots=/path/to/dir

const SHOTS := [
	{"name": "tv1_front_room_morning", "day": 1, "time": "09:40", "pos": [1.7, 0, 2.4], "look": [0.3, 0.75, 1.6]},
	{"name": "tv2_close", "day": 1, "time": "10:30", "pos": [1.2, 0, 1.25], "look": [0.35, 0.8, 1.65]},
	{"name": "tv3_candle_night", "day": 1, "time": "21:00", "pos": [1.6, 0, 2.0], "look": [0.3, 0.75, 1.6], "candles": true},
	{"name": "k1_kitchen_morning", "day": 1, "time": "08:20", "pos": [0.75, 0, 6.85], "look": [2.9, 1.0, 8.6]},
	{"name": "k2_kitchen_door_tub", "day": 1, "time": "11:30", "pos": [2.6, 0, 7.0], "look": [1.2, 0.8, 10.1]},
	{"name": "k3_kitchen_gas_dusk", "day": 1, "time": "17:30", "pos": [1.0, 0, 7.4], "look": [3.0, 1.0, 8.2], "burners": 2},
	{"name": "k4_kitchen_candle_night", "day": 1, "time": "21:30", "pos": [0.6, 0, 7.1], "look": [1.7, 0.75, 8.6], "candles": true},
	{"name": "k5_cooler_table", "day": 1, "time": "09:00", "pos": [1.55, 0, 7.55], "look": [1.85, 0.85, 8.3]},
	{"name": "k6_range_close", "day": 1, "time": "10:30", "pos": [2.0, 0, 7.5], "look": [3.0, 0.8, 7.95]},
	{"name": "01_dawn_front_room", "day": 1, "time": "06:55", "pos": [1.0, 0, 3.6], "look": [2.0, 1.2, 0.0]},
	{"name": "02_kitchen_morning", "day": 1, "time": "09:30", "pos": [0.7, 0, 6.9], "look": [2.6, 0.9, 9.6]},
	{"name": "03_bedroom", "day": 1, "time": "11:00", "pos": [0.7, 0, 4.3], "look": [2.6, 0.6, 5.6]},
	{"name": "04_fire_escape_street", "day": 1, "time": "13:00", "pos": [1.6, 0.05, -0.5], "look": [3.0, -6.0, -12.0], "open": true},
	{"name": "05_sunset_day1", "day": 1, "time": "16:45", "pos": [1.4, 0, 2.8], "look": [1.8, 1.5, -6.0]},
	{"name": "06_night_candles", "day": 1, "time": "20:30", "pos": [0.6, 0, 7.0], "look": [1.6, 0.8, 8.5], "candles": true},
	{"name": "07_cooler_close", "day": 1, "time": "10:00", "pos": [1.75, 0, 7.45], "look": [1.95, 0.9, 8.3]},
	{"name": "09_midmorning_sun", "day": 1, "time": "10:15", "pos": [2.6, 0, 3.4], "look": [1.2, 0.0, 1.2]},
	{"name": "08_day3_haze", "day": 3, "time": "12:00", "pos": [1.0, 0, 3.6], "look": [2.0, 1.2, 0.0]},
]


func run(main: Node3D, dir: String, only := "") -> void:
	DirAccess.make_dir_recursive_absolute(dir)
	Game.sim_paused = true
	main.hud.close_panel()
	var player: Player = main.player
	for s in SHOTS:
		if only != "" and not String(s.name).begins_with(only):
			continue
		Game.clock.minutes = Game.clock.absolute(int(s.day), String(s.time))
		var pos := Vector3(s.pos[0], s.pos[1], s.pos[2])
		var look := Vector3(s.look[0], s.look[1], s.look[2])
		for n in main.get_tree().get_nodes_in_group("persist"):
			if n is WindowSash and n.outside == "fire_escape":
				n.set_open(s.get("open", false))
			if n is CandleProp:
				n.set_lit(s.get("candles", false))
		Game.set_burners(int(s.get("burners", 0)))
		player.teleport(pos)
		var eye := pos + Vector3(0, Player.EYE, 0)
		var d := look - eye
		player.set_look(atan2(-d.x, -d.z), atan2(d.y, Vector2(d.x, d.z).length()))
		for i in 8:
			await main.get_tree().process_frame
		var img := main.get_viewport().get_texture().get_image()
		img.save_png("%s/%s.png" % [dir, s.name])
		print("shot ", s.name)
	main.get_tree().quit()
