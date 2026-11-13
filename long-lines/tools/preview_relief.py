"""Blender CLI: preview recorded relief as an uncapped diagnostic skin, not an asset."""
import argparse
import json
from pathlib import Path
import sys
import bpy
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from propkit.relief_preview import mesh_grid  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--result', type=Path, required=True)
    parser.add_argument('--diagnostics', type=Path, required=True)
    parser.add_argument('--view', default='front')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    result = json.loads(args.result.read_text())
    field = result['measured']['relief']['field']
    dimensions = np.asarray(field['grid_shape']) * field['spacing_m']
    with np.load(args.diagnostics / (args.view + '.npz'), allow_pickle=False) as source:
        arrays = {key: source[key].copy() for key in (
            'mask', 'coarse_height_px', 'hypothesis_height_px', 'accepted_height_px', 'metres_per_pixel')}
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    artifacts = []
    for label, height in [('base', np.zeros(arrays['mask'].shape)), ('proposal', arrays['hypothesis_height_px']), ('applied', arrays['accepted_height_px'])]:
        vertices, faces = mesh_grid(arrays['coarse_height_px'], height, arrays['mask'],
                                    args.view, dimensions, float(arrays['metres_per_pixel']))
        mesh = bpy.data.meshes.new(label)
        mesh.from_pydata(vertices.tolist(), [], faces.tolist())
        mesh.update()
        for polygon in mesh.polygons:
            polygon.use_smooth = True
        obj = bpy.data.objects.new(label + '-diagnostic-open-surface', mesh)
        path = args.output / (args.view + '-' + label + '.blend')
        bpy.data.libraries.write(str(path), {obj}, compress=True)
        artifacts.append(
            {'variant': label, 'path': str(path), 'triangles': len(faces)})
        bpy.data.objects.remove(obj)
        bpy.data.meshes.remove(mesh)
    report = {'production_model': False, 'open_surface': True, 'view': args.view, 'artifacts': artifacts,
              'limits': 'A recorded single-view surface. No assembly, thickness, cross-view fusion or geometry acceptance is implied.'}
    (args.output / 'preview-manifest.json').write_text(json.dumps(report, indent=2))
    print('RELIEF_PREVIEW', json.dumps(report))


if __name__ == '__main__':
    main()
