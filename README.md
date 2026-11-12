# Hull V2

Image references → geometric reconstruction → textured models → measured inspection.

Hull is the asset-production software in `long-lines/tools`; the Long Lines Godot
project supplies its original asset library and a consumer for exported props.
The reconstruction pipeline runs in software, without a runtime LLM. It supports
orthographic views, parts sheets, inferred sections, local relief hypotheses,
texture ownership, inspection drawings and optional CAD surface exchange.
**A passing image fit does not establish physical depth or universal recognition.**

## Start here

1. Use Python **3.13** and Blender **5.2.3** for the qualified profile.
2. Install the core dependencies in an isolated environment:
   `python -m pip install -r requirements-core.txt`.
3. Run `python hull.py doctor`, then `python hull.py check`.
4. Follow the [image intake guide](long-lines/factory/AUTOMATIC_INTAKE.md) to build.

On Windows, `Hull.cmd doctor` also finds Blender 5.2's bundled Python if Python
is not installed separately. It does not install packages or change machine policy.
For a local dependency folder use `python -m pip install --target .hull-runtime -r requirements-core.txt`.

```text
python hull.py audit
python hull.py check --profiles core
python hull.py qualify --blender "PATH/TO/blender.exe" --godot "PATH/TO/godot.exe"
python hull.py package --output "PATH/TO/Hull-V2-source.zip"
```

`qualify` requires core, Blender and Godot checks; `--profiles core,blender,godot,cad`
also requires a working optional Open CASCADE backend. Missing capabilities and
skipped required checks fail qualification. OCR, neural models and CAD dependencies
are separate capabilities; installing core does not install them.

## Build safety

Each factory build keeps its order, diagnostics, QA and candidate exports under
`.hull-runs/<run-id>/`. Failed or uncertain candidates remain inspectable.
Passing candidates receive an artifact audit before publication into immutable
`long-lines/assets/props/releases/<name>/<run-id>/` versions. `library.json` selects
the active version; legacy asset paths still load. Set `HULL_RELEASE_POLICY=hold`
for experiments, then use `python hull.py promote RECEIPT.json` when qualified.
Promotion cannot override failed QA or unresolved inference warnings.

## Project guide

- [Operations, repairs and recovery](long-lines/factory/OPERATIONS.md)
- [Contribution and validation](CONTRIBUTING.md)
- [Repository maintenance audit](docs/REPOSITORY_MAINTENANCE.md)
- [Validation and retained benchmark failures](docs/MAINTENANCE_VALIDATION.md)
- [Current machinery and limitations](KNOWLEDGE_FILE.md)
- [Factory manual and sizing](long-lines/factory/README.md)
- [Security reporting](SECURITY.md)
- [Long Lines game](long-lines/README.md)
- [Preserved Midnight Watch project](docs/legacy/MIDNIGHT_WATCH.md)

The root web files belong to the older Midnight Watch project. Its collector is
manual and explicitly opt-in in this repository. No historical branches were removed.
A code-only ZIP is a reproducible source handoff, not a standalone installer: model
assets, trained weights, dependencies, generated outputs and private run records are excluded.
No project-wide license grant is inferred; dependency and image rights remain separate.
