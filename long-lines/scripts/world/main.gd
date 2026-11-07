extends Node3D
## Builds the apartment slice and drives the light: dawn through the east
## windows on Sullivan Street, a blood-red sunset on day 1, then haze.
##
## Command-line options (after `--`):
##   --smoke             run a scripted playthrough headless and quit (exit 1 on failure)
##   --shots=<dir>       render screenshots from set camera positions and quit

var env: Environment
var sky_mat: ProceduralSkyMaterial
var sun: DirectionalLight3D
var player: Player
var hud: Node
var builder: ApartmentBuilder
var props_root: Node3D
var _spawn_n := 0
var _runner: RefCounted  # keeps a test runner alive while its coroutine waits


func _ready() -> void:
	_build_environment()
	builder = ApartmentBuilder.new(Data.apartment)
	builder.build(self)
	props_root = Node3D.new()
	props_root.name = "Props"
	add_child(props_root)
	for p in Data.apartment.props:
		_place_prop(p)

	player = Player.new()
	player.name = "Player"
	add_child(player)
	var ps: Dictionary = Data.apartment.player_start
	var pos: Array = ps.pos
	player.position = Vector3(pos[0], pos[1], pos[2])
	player.set_look(deg_to_rad(float(ps.yaw_deg)))

	hud = preload("res://scripts/ui/hud.gd").new()
	add_child(hud)
	hud.player = player
	player.hud = hud

	Game.spawner = spawn_prop
	_update_light()

	var args := OS.get_cmdline_user_args()
	if "--smoke" in args:
		_runner = SmokeTest.new()
		_runner.run(self)
		return
	for a in args:
		if a.begins_with("--shots="):
			_runner = Screenshots.new()
			_runner.run(self, a.substr(8))
			return
	if DisplayServer.get_name() != "headless":
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
		hud.open_help()


func _place_prop(p: Dictionary) -> Node3D:
	var n := PropFactory.make(String(p.type), String(p.id))
	props_root.add_child(n)
	var pos: Array = p.pos
	n.position = Vector3(pos[0], pos[1], pos[2])
	n.rotation.y = deg_to_rad(float(p.get("rot", 0.0)))
	if n is CoolerProp or n is CandleProp or n is Carriable:
		n.call_deferred("on_placed")
	return n


## Creates a prop that was not in the layout (e.g. a candle from the box).
func spawn_prop(type: String, id := "") -> Node:
	if id == "":
		_spawn_n += 1
		id = "spawn_%s_%d_%d" % [type, Time.get_ticks_msec(), _spawn_n]
	var n := PropFactory.make(type, id)
	props_root.add_child(n)
	if n is Carriable:
		n.spawned = true
	return n


func spawn_into_hand(type: String) -> void:
	if player.held:
		Game.message.emit("Your hands are full.")
		Game.inv.add(type)
		return
	var n := spawn_prop(type)
	player.pick_up(n)
	Game.message.emit("You take out a %s. Press E on a flat surface to set it down." % type)


# ------------------------------------------------------------ light

func _build_environment() -> void:
	env = Environment.new()
	env.background_mode = Environment.BG_SKY
	sky_mat = ProceduralSkyMaterial.new()
	var sky := Sky.new()
	sky.sky_material = sky_mat
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	env.fog_enabled = true
	env.fog_density = 0.008
	env.fog_sky_affect = 0.3
	var we := WorldEnvironment.new()
	we.environment = env
	add_child(we)

	sun = DirectionalLight3D.new()
	sun.shadow_enabled = true
	sun.directional_shadow_max_distance = 40.0
	sun.shadow_bias = 0.04
	add_child(sun)


func _process(_d: float) -> void:
	_update_light()


func _update_light() -> void:
	var c := Game.climate
	var m := Game.clock.minutes
	var dd := c.day_data(Game.clock.day())
	var light := c.daylight(m)
	var haze := float(dd.get("haze", 0.0))
	var prog := c.sun_progress(m)
	var sky_col: Array = dd.get("sky", [0.5, 0.65, 0.85])
	var tint: Array = dd.get("sunset_tint", [0.9, 0.3, 0.1])
	var sky_c := Color(sky_col[0], sky_col[1], sky_col[2])
	var low_c := Color(tint[0], tint[1], tint[2])

	# The building faces east: morning sun pours straight in the front windows.
	var elev := sin(clampf(prog, 0.0, 1.0) * PI) * deg_to_rad(c.max_elevation_deg)
	var az := clampf(prog, 0.0, 1.0) * PI
	var sun_pos := Vector3(sin(az) * cos(elev), maxf(sin(elev), 0.05), -cos(az) * cos(elev))
	sun.look_at_from_position(Vector3.ZERO, -sun_pos, Vector3.UP)
	var lowness := 1.0 - clampf(sin(elev) / sin(deg_to_rad(20.0)), 0.0, 1.0)
	var dawn_c := Color(1.0, 0.62, 0.36)
	var sun_c := Color(1.0, 0.95, 0.86).lerp(dawn_c if prog < 0.5 else low_c, lowness)
	sun_c = sun_c.lerp(Color(0.75, 0.6, 0.45), haze)
	sun.light_color = sun_c
	sun.light_energy = light * 1.35 * (1.0 - haze * 0.5)
	sun.visible = light > 0.01

	var night_sky := Color(0.03, 0.035, 0.05)
	var top := night_sky.lerp(sky_c * 0.8, light)
	var horizon := night_sky.lerp(sky_c.lerp(Color(0.9, 0.85, 0.75), 0.3), light)
	if prog > 0.75 and prog < 1.1:
		horizon = horizon.lerp(low_c, clampf((prog - 0.75) / 0.2, 0.0, 1.0) * clampf((1.1 - prog) / 0.1, 0.0, 1.0) * 0.85)
	if prog > -0.08 and prog < 0.15:
		horizon = horizon.lerp(dawn_c * 0.9, 0.5 * (1.0 - absf(prog - 0.03) / 0.12))
	sky_mat.sky_top_color = top
	sky_mat.sky_horizon_color = horizon
	sky_mat.ground_horizon_color = horizon * 0.7
	sky_mat.ground_bottom_color = Color(0.05, 0.05, 0.05)
	sky_mat.sun_angle_max = 8.0
	sky_mat.sky_energy_multiplier = 0.4 + light * 0.8

	env.ambient_light_color = Color(0.55, 0.6, 0.7).lerp(sun_c, 0.12)
	env.ambient_light_energy = 0.035 + light * 0.4
	env.fog_light_color = horizon.lerp(Color(0.5, 0.5, 0.5), 0.4)
	env.fog_density = 0.006 + haze * 0.03

	# Idling cars: headlights fade as batteries die over days 1-3.
	var day_f := m / 1440.0
	for car in builder.cars:
		var life: float = 1.0 - clampf((day_f - 0.9 - float(car.seed) * 0.8) / 1.0, 0.0, 1.0)
		var spot: SpotLight3D = car.spot
		spot.light_energy = 1.5 * life
		spot.visible = life > 0.02
		for l in car.lamps:
			l.visible = life > 0.02
