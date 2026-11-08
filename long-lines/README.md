# Long Lines: apartment test slice

A first playable slice of *Long Lines*, built from the game design document. It covers only Nick Lombardi's apartment: 4A, a front railroad flat in an old-law tenement on Sullivan Street. Play starts at 6:40 a.m. on Friday, October 31, 1975, the morning after the comet. Stepping out the hall door ends the slice.

It is a Godot 4.4 project, as the design doc's technical plan specifies. Systems are data-driven from the first file, and every prop is generated in code (bevelled meshes and a painterly toon shader), so there are no art assets to import.

![The kitchen in the morning](docs/kitchen_pass/k1_kitchen_morning.png)

## Art pass: the kitchen

The kitchen is the test room for the final look. It combines 1970s New York apartment references with The Long Dark's rendering style:

- **Period dressing.** Octagon sheet linoleum, gold glazed tile up to 1.25 m, painted wooden cabinets with chrome pulls, a round-shouldered 1950s fridge, an apartment gas range with a clock in its back panel, a formica and chrome dinette, a tub on claw feet with a board lid, a yellow rotary phone, a milk-glass ceiling globe, cafe curtains, a curtain hung in the doorway, paper grocery bags, jars, and a percolator.
- **Chunky, bevelled props.** `Geo.rounded_box_mesh` rounds every edge. Edge vertices are tagged so the shader can lighten and chip them like painted wear.
- **Painted surfaces.** Procedural patterns, painted grain, grime blotches, and a dirty band low on the walls (`shaders/paint.gdshader`).
- **Lighting.** Forward+ renderer with ambient occlusion, a little bounced light, volumetric fog and glow. Warm practical lights against a cool teal ambient. Soft daylight spills in through each window, and the corners stay dark.
- **Grade.** Teal shadows, warm highlights, vignette and film grain (`shaders/grade.gdshader`).

The front room and bedroom have the new lighting and bevelled props but not yet their own dressing pass.

| Range, mid-morning | Candlelight, 9:30 p.m. |
| --- | --- |
| ![](docs/kitchen_pass/k6_range_close.png) | ![](docs/kitchen_pass/k4_kitchen_candle_night.png) |

## Run it

1. Install [Godot 4.4](https://godotengine.org/download) (the standard build, not .NET).
2. Open Godot, choose **Import**, and select `long-lines/project.godot`.
3. Press **F5** (Run Project).

Or from a terminal:

```bash
godot --path long-lines
```

## Controls

| Key | Action |
| --- | --- |
| WASD, mouse | Move, look |
| E | Use / primary action (also sets down whatever you're carrying) |
| R | Secondary action: pick up, climb out of an open window, open the freezer, cook |
| Q | Rotate the thing you're carrying |
| Mouse wheel or `[` `]` | Tune the radio (while looking at it or holding it) |
| F | Flashlight, once you've found it and only with a free hand |
| Tab | Inventory |
| C | Crouch |
| F5 / F9 | Quick save / quick load |
| Esc | Menu |
| F1 | Help |

## What's in the apartment

Three rooms in a row, at real tenement dimensions (3.4 m wide, 10.2 m deep, 2.75 m ceilings):

- **Front room.** Two east-facing windows onto Sullivan Street and the fire escape. A slipcovered sofa, a dead TV, the transistor radio, yesterday's paper ("FORD TO CITY: DROP DEAD"), a paper skeleton in the window, and the jack-o'-lantern out on the fire escape.
- **Bedroom.** Bed, dresser (cash, cigarettes, the prescription card), a photo of you and Terry, and an airshaft window.
- **Kitchen.** You enter from the hall here. Tub with a board lid, dead fridge and freezer, a working gas range, sink, cupboard, kitchen table with a drawer, the wall phone, the calendar, your coat on its hook, and the medicine cooler.

The street outside is dressed with dark tenements, Halloween paper in windows, a water tower, and cars left idling with their headlights on.

![Sullivan Street from the fire escape](docs/04_fire_escape_street.png)

## Systems

| System | In this slice | Data |
| --- | --- | --- |
| Time | 1 game minute per real second; sleep skips time and wakes you for knocks | `tuning.json` → `time` |
| Climate | Design curve for days 1 to 7: 8 to 14 C on day 1, near freezing by day 7, with daylight dimming as soot spreads | `climate.json` |
| Needs | Warmth, food, water, rest, condition, morale | `tuning.json` → `needs` |
| Heat and air | One-zone room temperature and carbon monoxide. Burners and candles add heat and CO; each open window vents both. Headache, then dizziness, then drowsiness. Sleeping in bad air kills. | `tuning.json` → `air` |
| The cooler | Dial thermometer, ice that melts, 60 vials. Potency drops above 8 C and is ruined below 0 C. One dose a day; missed doses bring fever. Put it on the fire escape on cold nights. | `tuning.json` → `cooler` |
| Fridge and freezer | The fridge warms from 1 a.m. onward. The freezer stays frozen for about 22 hours, less each time you open it, then its ice trays melt one by one. Food spoils by temperature. | `tuning.json` → `fridge`, `items.json` |
| Inventory | Weight limit; every item ages on its own; tools gate actions (can opener, matches, a pot) | `items.json` |
| Carrying | Pick up props and set them on any flat surface, including the fire escape through an open window. The cooler takes both hands: no flashlight and slower walking. | |
| Radio | Six AM stations on day 1, fewer each day. EBS on 640, Civil Defense on 1240, all-news on 1130, an overnight call-in on 770, a DJ on 1550, a Spanish-language station on 1600. Batteries run down. | `radio.json` |
| Events | Captions on a schedule, with sound built by subtraction: horns and sirens on day 1, a car dying on day 2, bells and then silence on day 3. Walter knocks at 9:10 a.m., Concetta calls up the airshaft, and the Rivera kids trick-or-treat at 5:40 p.m. | `events.json` |
| Documents | Newspaper, notepad, calendar, photo, the Fear City pamphlet, a civil defense booklet, the prescription card, Concetta's note | `docs.json` |
| Save / load | All state, plus every prop's position, saved to `user://` | |

Things worth trying: fill the tub before the water goes, ration the freezer's ice into the cooler, make coffee on the range (then open a window), answer Walter, keep candy for the trick-or-treaters, and sleep with the gas on to see what happens.

![The cooler's thermometer](docs/07_cooler_close.png)

## Hero prop: the television

A test of how far procedural modelling and texturing can go. `tools/build_tv.py` builds a mid-1970s 19-inch table TV entirely in a Blender script. It has a walnut-grain cabinet on a tapered-leg stand with brass caps, a curved CRT, a brushed-aluminium control panel with a numbered channel dial and knurled knobs, a speaker grille, chrome "Westbury" script (an invented brand), a vented back with a maker's plate, rabbit ears with a UHF loop, and a doily. It is about 30k triangles.

The script then bakes 2048 px textures: colour with dirt in the crevices, worn edges and dust on top; a normal map; and roughness/metal. In Godot, `shaders/baked_prop.gdshader` keeps the prop on the same toon lighting as the rest of the apartment.

![The TV, rendered in Blender](docs/props/tv_blender_closeup.png)

| In the front room, morning | By candlelight |
| --- | --- |
| ![](docs/props/tv_in_game_morning.png) | ![](docs/props/tv_in_game_night.png) |

To rebuild it (Blender 4.0 or later; about 4 minutes on 4 CPU cores):

```bash
blender --background --factory-startup --python long-lines/tools/build_tv.py
blender --background --factory-startup --python long-lines/tools/preview_prop.py -- long-lines/assets/props/tv tv /tmp/tv.png
```

`PropFactory.baked_prop("name")` loads any prop built this way from `assets/props/<name>/`.

## Layout of the project

```
long-lines/
  data/            every tunable number, the layout, items, radio, events, documents
  scripts/core/    Data and Game autoloads
  scripts/sim/     pure simulation classes (clock, climate, needs, air, cooler, fridge, radio, inventory)
  scripts/world/   apartment builder, prop factory, player, interactables
  scripts/ui/      HUD and panels
  shaders/         paint.gdshader: toon ramp, painted grain, procedural patterns
  tests/           unit tests, an in-scene smoke test, a screenshot renderer
```

The apartment is built at runtime from `data/apartment.json`: walls with openings, rooms with their own floors and wallpaper, and props placed by position and rotation. To move the sofa, edit one line.

## Tests

```bash
# Unit tests for the simulation layer (39 checks)
godot --headless --path long-lines --script res://tests/run_tests.gd

# Scripted playthrough in the real scene: raycast interactions, carrying the
# cooler out to the fire escape, cooking with the windows shut, sleeping,
# saving and loading (44 checks)
godot --headless --path long-lines -- --smoke

# Render screenshots from fixed viewpoints and times (needs a display and
# Vulkan; on a headless Linux box, xvfb-run plus mesa-vulkan-drivers works).
# --only=k renders just the kitchen set.
godot --path long-lines -- --shots=/tmp/shots --only=k
```

The first run of a fresh checkout needs `godot --headless --path long-lines --import` so Godot can register the script classes.

## Differences from the design doc, for now

- **Built from scratch, not on Cogito.** The doc plans to start from the Cogito template. This slice needed only a small interaction and carry system, so it uses its own. Moving to Cogito when the building and street are added is still an option.
- **No audio yet.** Sound is shown as captions. The subtraction schedule is already in `events.json`, ready for an audio layer.
- **One air zone.** The doc imagines picking a warm room and sealing it off. Here the whole apartment shares one temperature and one CO level. Per-room zones are the next step for the shelter puzzle.
- **No glass breaking, nailing or taping, or fires spreading.** Windows open and close.
- **Renderer.** The project uses Forward+, which needs a Vulkan-capable GPU. For older hardware, switch `rendering/renderer/rendering_method` to `gl_compatibility`. It still runs, without ambient occlusion, volumetric fog or bounced light.
- **Toilets on the landing** (true to old-law tenements) are outside the slice.
- **Placeholder names.** The newspaper (*New York Daily Record*), food brands and radio station names are invented, as the doc requires. Real officials are never quoted.

## Next

The vertical-slice milestone in the design doc adds the rest of the building and Sullivan Street, days 1 to 7, Concetta and Walter as characters, keys and locked doors.
