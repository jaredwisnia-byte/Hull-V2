"""Blender regressions for landmark orientation and surface simplification."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import bpy
import bmesh
import numpy as np
from mathutils import Matrix, Vector
from propkit import core
from propkit.components.alignment import solve
from propkit.components.placement import place
from propkit.components.optimization import optimize
from propkit.components.reconstruction import triangle_count

source = [[0,0,0],[0,0,.1],[.05,0,.05]]
rotation = Matrix.Rotation(.4,4,'Y')
target = [list(rotation @ Vector(p)+Vector((.1,.2,.3))) for p in source]
matrix,error = solve(source,target,1e-6)
assert error < 1e-7 and np.linalg.det(matrix[:3,:3]) > .9999
for a,b in zip(source,target):
    assert np.linalg.norm(matrix[:3,:3]@a+matrix[:3,3]-b) < 1e-7
for invalid in ([[0,0,0],[0,0,.1],[0,0,.2]], [[0,0,0],[0,0,.1],[.5,0,.05]]):
    try: solve(invalid,target,1e-5)
    except ValueError: pass
    else: raise AssertionError('ambiguous or incompatible anchors accepted')
core.reset()
bpy.ops.mesh.primitive_cube_add(size=.1)
parent=bpy.context.object
parent['component_transform']=[list(r) for r in Matrix.Translation((.4,0,0))]
bpy.ops.mesh.primitive_cube_add(size=.01)
child=bpy.context.object
spec={'position':[0,0,0],'attachment':{'parent':'parent','landmarks':[{'source':a,'target':b} for a,b in zip(source,target)],'tolerance_m':1e-6}}
report=place(child,spec,{'parent':parent},{},{})
assert np.linalg.norm(np.asarray(report['transform'])[:3,3]-[.5,.2,.3]) < 1e-6
core.reset()
bpy.ops.mesh.primitive_cube_add(size=.1)
obj=bpy.context.object
bm=bmesh.new(); bm.from_mesh(obj.data)
bmesh.ops.subdivide_edges(bm,edges=list(bm.edges),cuts=5,use_grid_fill=True)
bm.to_mesh(obj.data); bm.free()
before=triangle_count(obj)
result=optimize(obj,.00005)
assert result['after'] <= 12 < before, result
assert max(abs(v.co[i]) for v in obj.data.vertices for i in range(3)) <= .050001
print('COMPONENT QUALITY PASS',result)

import tempfile
from PIL import Image
from propkit.components.surface_detail import apply as surface_detail
with tempfile.TemporaryDirectory() as d:
    directory=Path(d)
    Image.new('RGB',(64,64),(100,100,100)).save(directory/'flat.png')
    report=surface_detail(obj,{'view':'front','depth_m':.0005},{'front':str(directory/'flat.png')},directory,directory)
    assert report['applied'] is False, report
    material=bpy.data.materials.new('quality detail')
    material.use_nodes=True
    obj.data.materials.append(material)
    Image.fromarray(np.tile(np.arange(64,dtype=np.uint8)*4,(64,1))).save(directory/'height.png')
    count=triangle_count(obj)
    report=surface_detail(obj,{'view':'front','depth_m':.0005,'height_map':'height.png'},{'front':str(directory/'flat.png')},directory,directory)
    assert report['applied'] and triangle_count(obj)==count
    assert material.node_tree.nodes['Principled BSDF'].inputs['Normal'].is_linked
print('SURFACE DETAIL PASS')
