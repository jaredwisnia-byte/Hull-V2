# Extruded trim quality checks (November 2026)

The existing factory gate checks loadability, texture availability, triangle limits,
texel density, floor contact and (where v_*.png exists) silhouettes. Those are
necessary but **not sufficient** to certify the visual quality of trim or frames.

## Additional checks for extrude-line work orders

- **Profile fidelity:** if the work order names a drawn section, the factory
  crops `p_section.png` and compares it with the **exported GLB's actual end cap**.
  A section IoU below 0.68 or a depth/height ratio error above 0.30 fails.
  An unusable drawing is an error, not a silent fallback to a generic shape.
  Work orders without a drawn section continue to use the declared standard
  profile and report that fact.
- **Frame opening:** door casings, window casings, window trim, and closet trim
  need a genuine hole in the front-facing mesh. We check the intended opening
  from `p_front.png` and ray-cast its central region against the exported GLB.
  More than 10% occlusion fails.
- **Painted colour:** compare a coarse median foreground colour in
  `p_strip.png`/`p_front.png` with occupied pixels of the exported albedo.
  A normalized RGB distance above 0.40 fails. This catches drastic colour
  errors but **does not establish pixel-accurate texture fidelity**.
- **Reproducibility:** the gauge hash now includes a millimetre-quantized
  fingerprint of the exported mesh vertices **and face connectivity**, plus
  coarse baked colour statistics. It still is not bit-for-bit deterministic.
- **One automatic correction:** profile contour simplification is tightened
  from 1.0 to 0.3 if the profile comparison fails; frames retry with an
  interior-gap detector for open-bottom casing shapes. Failed retries are
  flagged for review instead of shipped.
- **Visual review:** every successfully built extrusion asset produces
  `assets/props/NAME/_preview.png` containing three views of the **exported
  GLB with its baked maps**: front, end profile and three-quarter. If the
  preview cannot be generated, the work order is flagged.

## Commands

From the repository root, with the Blender/Python dependencies specified by
the factory installed:

```bash
python -m unittest discover -s long-lines/tests -p 'test_trim_checks.py'
blender -b --factory-startup -P long-lines/tools/factory.py -- build crown_ornate
blender -b --factory-startup -P long-lines/tools/factory.py -- qa crown_ornate
blender -b --factory-startup -P long-lines/tools/factory.py -- preview crown_ornate
```

The first command tests the pure-image geometry and colour utilities without
Blender. The remaining commands must be run in a Blender environment capable
of importing GLB, baking maps and rendering with Cycles.

## Limitations and acceptance

**A quality-gate pass is not an artistic acceptance test.** Cross-section IoU
and median colour tests cannot see all contour/weathering errors, wrong
ornament detail, or bad UV placement. Inspect the saved PNG turnaround before
marking a hero-quality asset approved. The threshold values are intentionally
initial values; validate them against a known-good/known-bad set of real
mouldings before rebuilding the entire library. Existing 41/41 pass counts
refer to the **previous** gate and should not be reused as claims about this
stricter gate.

The review branch contains code changes and unit tests, not regenerated GLBs
or previews; those require executing Blender. No existing exported assets
were overwritten by this patch.
