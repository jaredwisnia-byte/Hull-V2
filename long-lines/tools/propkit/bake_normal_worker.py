"""Single-threaded tangent-space normal bake, run as `blender -b -t 1 FILE.blend --python THIS -- JSON`.

Why a separate process: Blender 5.2 computes MikkTSpace tangents with a parallel sum whose order
varies, so twenty calls on the same mesh gave twenty slightly different tangent sets, and a
normal-map value lying on a rounding boundary flipped by one level between identical builds
(rule R9). Only the command-line thread count (-t 1) makes the tangents repeatable; the scene's
render-thread setting does not. propkit/bake.py saves a copy of the scene, runs this worker and
reads the PNG back, so every entry point gets a repeatable normal map without slowing the rest of
the build.
"""
import json
import sys

import bpy

args = json.loads(sys.argv[sys.argv.index('--') + 1])
scene = bpy.context.scene
obj = bpy.data.objects[args['object']]
image = bpy.data.images[args['image']]
for o in bpy.context.view_layer.objects:
    o.select_set(False)
obj.select_set(True)
bpy.context.view_layer.objects.active = obj
for slot in obj.material_slots:
    if slot.material and slot.material.node_tree:
        node = slot.material.node_tree.nodes.get('bake_target')
        if node is not None:
            node.image = image
            slot.material.node_tree.nodes.active = node
if args.get('high'):
    bpy.data.objects[args['high']].select_set(True)
    bpy.ops.object.bake(type='NORMAL', normal_space='TANGENT', use_selected_to_active=True,
                        cage_extrusion=args['cage_extrusion'], max_ray_distance=args['max_ray_distance'])
else:
    bpy.ops.object.bake(type='NORMAL', normal_space='TANGENT')
image.filepath_raw = args['output']
image.file_format = 'PNG'
image.save()
print('NORMAL_BAKE_WORKER_DONE', args['output'], flush=True)
