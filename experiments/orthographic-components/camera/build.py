"""Manifest-driven experiment runner. Hull source is imported without editing it."""
import sys,json,os,time
from pathlib import Path
BASE=Path(__file__).resolve().parent
cfg=json.loads((BASE/'manifest.json').read_text())
sys.path.insert(0,os.environ['HULL_PYTHON_DEPS']);sys.path.insert(0,os.environ['HULL_TOOLS'])
import bpy
from PIL import Image
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from propkit import core,mats,texturing,bake
from propkit.hull import hull_prop,polygon_hull,silhouette,HULL_REPORT
OUT=Path(os.environ.get('HULL_OUTPUT',str(BASE/'output')));OUT.mkdir(parents=True,exist_ok=True)
sheet=Image.open(BASE/cfg['reference']).convert('RGB');parts=[];report=[];start=time.time()
core.reset();mats.reset()
for spec in cfg['parts']:
    name=spec['name'];w,d,h=spec['dimensions'];sil={};paint={}
    for view,bb in spec['views'].items():
        p=OUT/(name+'_'+view+'_input.png');sheet.crop(bb).save(p)
        mask,img=silhouette(str(p));sil[view]=(mask,img)
        p=OUT/(name+'_'+view+'_paint.png');img.save(p);paint[view]=str(p)
    HULL_REPORT.clear()
    if spec['method']=='round':
        obj=hull_prop({},h,width_m=w,depth_m=d,sil_override=sil,name=name,res=64,paint=False,features=False,
                      sections=False,smooth_iters=2,decimate=.1,revolve=True)
    else:obj=polygon_hull({k:v[0] for k,v in sil.items()},w,d,h,name=name,tolerance=1.1,bevel_frac=.01)
    before=sum(len(p.vertices)-2 for p in obj.data.polygons)
    if before>spec['budget']:
        md=obj.modifiers.new('Manifest budget','DECIMATE');md.ratio=spec['budget']/before*.97;core.apply_mods(obj)
    count=sum(len(p.vertices)-2 for p in obj.data.polygons);assert count<=spec['budget']
    texturing.project(obj,paint,w,d,h,others=[],name=name,rough=.65)
    x,y,z=spec['position']
    if spec.get('mount')=='top':
        body=parts[0][1]
        tree=BVHTree.FromPolygons([v.co for v in body.data.vertices],[p.vertices for p in body.data.polygons])
        hit=tree.ray_cast(Vector((x,y,1)),Vector((0,0,-1)),2)
        assert hit[0] is not None,name
        z=hit[0].z-.001
    for v in obj.data.vertices:v.co+=Vector((x,y,z))
    obj.data.update();parts.append((name,obj))
    group=obj.vertex_groups.new(name='component_'+name);group.add(list(range(len(obj.data.vertices))),1,'REPLACE')
    report.append({'name':name,'triangles':count,'budget':spec['budget'],'position':[x,y,z],'hull_report':json.loads(json.dumps(HULL_REPORT,default=str))})
    print('COMPONENT',name,count,flush=True)
assert sum(r['triangles'] for r in report)<=cfg['triangle_limit']
core.PARTS[:]=[o for _,o in parts]
info=bake.finish(cfg['name'],str(OUT/'baked'),cfg['texture'],12)
joined=bpy.context.view_layer.objects.active
mat=bpy.data.materials.new('Camera baked material');mat.use_nodes=True;nt=mat.node_tree;bs=nt.nodes['Principled BSDF']
def tex(s,cs):
    n=nt.nodes.new('ShaderNodeTexImage');n.image=bpy.data.images.load(str(OUT/'baked'/cfg['name']/(cfg['name']+'_'+s+'.png')));n.image.colorspace_settings.name=cs;return n
nt.links.new(tex('albedo','sRGB').outputs['Color'],bs.inputs['Base Color'])
nm=nt.nodes.new('ShaderNodeNormalMap');nt.links.new(tex('normal','Non-Color').outputs['Color'],nm.inputs['Color']);nt.links.new(nm.outputs['Normal'],bs.inputs['Normal'])
sep=nt.nodes.new('ShaderNodeSeparateColor');nt.links.new(tex('orm','Non-Color').outputs['Color'],sep.inputs['Color']);nt.links.new(sep.outputs['Green'],bs.inputs['Roughness']);nt.links.new(sep.outputs['Blue'],bs.inputs['Metallic'])
joined.data.materials.clear();joined.data.materials.append(mat)
for name,_ in parts[1:]:
    core.select_only(joined);joined.vertex_groups.active_index=joined.vertex_groups['component_'+name].index;before=set(bpy.data.objects)
    bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='DESELECT');bpy.ops.object.vertex_group_select();bpy.ops.mesh.separate(type='SELECTED');bpy.ops.object.mode_set(mode='OBJECT')
    new=set(bpy.data.objects)-before;assert len(new)==1;next(iter(new)).name=name
joined.name='body'
bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(OUT/(cfg['name']+'.blend')))
bpy.ops.object.select_all(action='SELECT');bpy.ops.export_scene.gltf(filepath=str(OUT/(cfg['name']+'.glb')),export_format='GLB',use_selection=True)
(OUT/'build-report.json').write_text(json.dumps({'parts':report,'bake':info,'total_triangles':info['tris'],'seconds':time.time()-start,'hull_source_edited':False},indent=2))
print('CAMERA_DONE',info['tris'],flush=True)
