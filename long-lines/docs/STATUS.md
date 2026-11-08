# Status

## Done
- Apartment slice systems: needs, heat and CO, cooler and vials, fridge, radio, events,
  inventory, carry and place, save/load. Unit tests (39) and an in-scene smoke test (45).
- Rendering: Forward+ with SSAO/SSIL, volumetric fog, glow, a colour grade, window fill
  lights and reflection probes. Painted wall wear (cracks, peeling, stains, scuffs).
- Prop kit and library: 108 baked props (see README "The prop library").
- Floor plan: front room, office, bedroom, closet, kitchen, water closet, entrance,
  landing outside 4A. Street outside built from library facade parts and three cars.

## Known weak spots
- Statue (statue_madonna) and the stair flight's stringer are crude.
- Entry door model: the inside face reads plain; the police lock is small.
- Many props carry no gameplay yet beyond "look at" (fixtures) or static collision.
- assets/ is ~120 MB of PNGs in plain git; consider Git LFS before it grows much more.

## Next
- Rest of the building (stairwell, other landings, neighbours' flats) reusing the builder.
- Sullivan Street at ground level, reusing facade bays, shopfronts, street furniture, cars.
- Characters (Walter, Concetta) need an artist or bought assets.
