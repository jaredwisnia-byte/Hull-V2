# Hull V2 working guide

Read `CONTRIBUTING.md` and `KNOWLEDGE_FILE.md` before changing the factory. The
reconstruction engine is in `long-lines/tools/propkit/`; orchestration is in
`long-lines/tools/factory.py`. The factory manual is
`long-lines/factory/README.md` and the current trace-driven drawing milestone is
recorded in `docs/TRACE_DRIVEN_DRAWING_STATUS.md`.

For reconstruction changes, reproduce the defect, record the source evidence,
and compare the same inputs before and after. Never select geometry from an
object name or tune a rule to one example. Test a planar manufactured object,
a curved manufactured object, a carved or organic object, and a negative
control, including a family outside the development examples.

Technical drawings must start from traced source pixels. Preserve each path's
source view, coordinates, method, and uncertainty. Label inferred geometry as
inferred and measure its deviation from the traced evidence. Do not claim a
physical part, bore, recess, or protrusion from a painted mark alone. The
builder must report which drawing constraints it used and which remain
unresolved.

For changed code, run `python hull.py check --changed-files PATH ...` and the
relevant checks it recommends. Geometry changes also require the mixed-asset
regression described in `CONTRIBUTING.md`; optional skipped tests do not
qualify a feature. Review the final diff and retain failed cases. Stage only
the intended files because this checkout contains generated assets and imports.
