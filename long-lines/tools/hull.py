"""Hull V2: blender -b --factory-startup -P tools/hull.py -- build MANIFEST --output DIR."""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Hull V2 companion-view component pipeline")
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("validate", help="validate assembly schema without building")
    check.add_argument("manifest")
    build = commands.add_parser("build", help="reconstruct, bake and export a complete assembly")
    build.add_argument("manifest")
    build.add_argument("--output", required=True)
    build.add_argument("--work-dir")
    build.add_argument("--no-blend", action="store_true")
    render = commands.add_parser("render", help="inspect an exported GLB with textures, clay or wireframe")
    render.add_argument("model")
    render.add_argument("--output", required=True)
    render.add_argument("--mode", choices=["textured", "clay", "wireframe"], default="textured")
    render.add_argument("--resolution", type=int, default=640)
    args = parser.parse_args(argv)
    if args.command == "validate":
        from propkit.components import load_manifest
        cfg, _ = load_manifest(args.manifest)
        print(json.dumps({"name": cfg["name"], "parts": len(cfg["parts"]), "triangle_limit": cfg["triangle_limit"]}))
    elif args.command == "render":
        from propkit.components.render import render as render_asset
        print(render_asset(args.model, args.output, args.mode, args.resolution))
    else:
        from propkit.components.pipeline import build as build_components
        print(json.dumps(build_components(args.manifest, args.output, args.work_dir, not args.no_blend)))


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])
