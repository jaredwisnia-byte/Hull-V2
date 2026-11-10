"""External, map-guided assembly using unchanged Hull APIs. No repository writes."""
import sys,json,math,time,shutil,os
from pathlib import Path
BASE=Path(os.environ['HULL_WORKDIR'])
sys.path.insert(0,os.environ['HULL_PYTHON_DEPS'])
sys.path.insert(0,os.environ['HULL_TOOLS'])
import bpy, numpy as np
from PIL import Image
from scipy import ndimage as ndi
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from propkit import core,mats,sheetset,texturing,bake,sizing
from propkit.hull import polygon_hull

started=time.time()
OUT=BASE/'outputs'/'stove_1974_companion_build'; RUN=BASE/'work'/'stove-companion-run'
OUT.mkdir(exist_ok=True); RUN.mkdir(parents=True,exist_ok=True)
paint=Image.open(os.environ['HULL_REFERENCE']).convert('RGB')
shutil.copy2(os.environ['HULL_REFERENCE'],OUT/'painted-sheet.png')
boxes={'front':(45,8,365,458),'back':(415,8,748,458),'left':(788,8,1110,458),
       'right':(1175,8,1525,458),'top':(30,540,375,945)}
manifest={'object_type':'appliance','dimensions_cm':{'height':116.6,'width':77,'depth':72.8},
          'painted_sheet':{'filename':'painted-sheet.png','view_bboxes_px':boxes},
          'part_map':{'filename':'part-map.png'},'depth_map':{'filename':'depth-map.png'}}
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2))
images={'painted_sheet':paint,'part_map':Image.open(OUT/'part-map.png').convert('RGB'),
        'depth_map':Image.open(OUT/'depth-map.png').convert('RGB')}
V={k:sheetset.view(manifest,images,k) for k in boxes}
W,D,H=.77,.728,1.166
for k,v in V.items():
    p=RUN/('paint_'+k+'.png');v['paint'].save(p);v['path']=str(p)
core.reset();mats.reset()
body=polygon_hull({k:v['carve'] for k,v in V.items()},W,D,H,name='stove_body',bevel_frac=.003,tolerance=1.2)
bpy.context.view_layer.update()

def comps(mask,min_area=10):
    lab,n=ndi.label(mask)
    return sorted([lab==i for i in range(1,n+1) if (lab==i).sum()>=min_area],key=lambda m: -m.sum())
def bounds(mask):
    yy,xx=np.nonzero(mask); return int(xx.min()),int(yy.min()),int(xx.max()+1),int(yy.max()+1)
def normalized(mask,view):
    a,b,c,d=bounds(mask);hh,ww=V[view]['cls'].shape
    return a/ww,b/hh,c/ww,d/hh
def tree(obj):
    return BVHTree.FromPolygons([obj.matrix_world@v.co for v in obj.data.vertices],[p.vertices for p in obj.data.polygons])
def front_surface(x,z):
    hit=tree(body).ray_cast(Vector((x,-2,z)),Vector((0,1,0)),4)
    if hit[0] is None:raise RuntimeError('No front surface at '+str((x,z)))
    return hit[0].y
def top_surface(x,y):
    hit=tree(body).ray_cast(Vector((x,y,3)),Vector((0,0,-1)),5)
    if hit[0] is None:raise RuntimeError('No cooktop surface')
    return hit[0].z
def boolean_cut(obj,cut):
    md=obj.modifiers.new('Map defined component clearance','BOOLEAN');md.operation='DIFFERENCE';md.solver='EXACT';md.object=cut
    core.apply_mods(obj);core.PARTS.remove(cut);bpy.data.objects.remove(cut,do_unlink=True)
def move_mesh(obj,offset):
    off=Vector(offset)
    for vert in obj.data.vertices:vert.co+=off
    obj.data.update()

parts=[('stove_body',body,list(V))]; evidence=[]
front=V['front'];fh,fw=front['cls'].shape
panels=comps(front['cls']==sheetset.CLASSES['panel'],300)
panels=sorted(panels,key=lambda m:bounds(m)[1])
panel_objects={}
for index,mask in enumerate(panels[:2]):
    mask=ndi.binary_fill_holes(mask)
    x0,y0,x1,y1=bounds(mask);u0,v0,u1,v1=normalized(mask,'front')
    pw,ph=(u1-u0)*W,(v1-v0)*H
    z0,z1=(1-v1)*H,(1-v0)*H
    cx=((u0+u1)/2-.5)*W
    # Door thickness is read from the matching green side-view component.
    sm=[m for m in comps(V['right']['cls']==sheetset.CLASSES['panel'],50)
        if abs((normalized(m,'right')[1]+normalized(m,'right')[3])/2-(v0+v1)/2)<.15]
    thickness=(normalized(sm[0],'right')[2]-normalized(sm[0],'right')[0])*D if sm else .035
    thickness=float(np.clip(thickness,.018,.06))
    fy=front_surface(cx,(z0+z1)/2)
    local=mask[y0:y1,x0:x1]
    key='oven_door' if index==0 else 'storage_drawer'
    obj=polygon_hull({'front':local,'right':np.ones((64,64),bool)},pw,thickness,ph,name=key,bevel_frac=.015,tolerance=.7)
    move_mesh(obj,(cx,fy+thickness/2-.001,z0))
    # Remove the occupied door layer from the shell, rather than stacking a second painted door over it.
    cut=core.box((pw+.002,thickness+.012,ph+.002),(cx,fy+thickness/2-.006,(z0+z1)/2),bevel=.002,name='component_cut')
    boolean_cut(body,cut)
    panel_objects[key]=(obj,(cx,fy+thickness-.001,z0),fy,z0,z1,pw,thickness)
    parts.append((key,obj,['front']))
    evidence.append({'part':key,'width_m':pw,'height_m':ph,'thickness_m':thickness,'source':'green panel boundary + side profile'})

# A plain inner face prevents the exterior door painting from appearing behind the separate door.
# This is a shallow placeholder backing, not a reconstructed oven chamber.
door,pivot,door_y,z0,z1,pw,thick=panel_objects['oven_door']
backing=core.box((pw-.006,.003,z1-z0-.006),(pivot[0],door_y+thick-.018,(z0+z1)/2),
                 mat=mats.plain((.035,.035,.032),rough=.9,edge=0,grime=0,dust=0,name='unobserved_inner_backing'),bevel=.001,name='unobserved_inner_backing')
parts.append(('unobserved_inner_backing',backing,[]))

reds=comps(front['cls']==sheetset.CLASSES['out'],15)
for mask in reds:
    x0,y0,x1,y1=bounds(mask);u0,v0,u1,v1=normalized(mask,'front')
    cx=((u0+u1)/2-.5)*W;cz=(1-(v0+v1)/2)*H
    if v1>.93:continue
    if .14<v0<.27:continue # burners seen edge-on; generated separately from top masks below
    if v0<.145:
        kind='knob' if (x1-x0)>14 else 'clock_button'
        # The front map identifies each item; existing sizing rules bound plausible relief.
        cat=sizing.catalogue()['out'].get('knob')
        depth=cat['default']/1000 if kind=='knob' else .005
        depth=float(np.clip(depth,.008,.03)) if kind=='knob' else depth
        fy=front_surface(cx,cz)
        local=mask[y0:y1,x0:x1]
        obj=polygon_hull({'front':local,'right':np.ones((64,64),bool)},(u1-u0)*W,depth,(v1-v0)*H,
                         name=kind,bevel_frac=.03,tolerance=.45)
        move_mesh(obj,(cx,fy-depth/2+.001,(1-v1)*H))
        key=kind+'_'+str(sum(1 for k,_,_ in parts if k.startswith(kind)))
        parts.append((key,obj,['front']))
        evidence.append({'part':key,'depth_m':depth,'source':'part-map footprint; existing sizing catalogue for depth'})
    elif (x1-x0)>fw*.45 and v0<.5:
        fy=panel_objects['oven_door'][2]-.002
        sidecomps=comps(V['right']['cls']==sheetset.CLASSES['out'],8)
        candidates=[m for m in sidecomps if abs((normalized(m,'right')[1]+normalized(m,'right')[3])/2-(v0+v1)/2)<.035]
        depth=(normalized(candidates[0],'right')[2]-normalized(candidates[0],'right')[0])*D if candidates else .035
        depth=float(np.clip(depth,.025,.055))
        local=mask[y0:y1,x0:x1]
        obj=polygon_hull({'front':local,'right':np.ones((64,64),bool)},(u1-u0)*W,depth,(v1-v0)*H,
                         name='oven_handle',bevel_frac=.1,tolerance=.6)
        move_mesh(obj,(cx,fy-depth/2,(1-v1)*H))
        parts.append(('oven_handle',obj,['front']))
        evidence.append({'part':'oven_handle','depth_m':depth,'source':'front component mask + side protrusion profile'})

# The stock sheetset build skips top-facing parts. Existing polygon_hull can reconstruct their masks independently.
top=V['top'];th,tw=top['cls'].shape
burners=[]
for mask in comps(top['cls']==sheetset.CLASSES['out'],100):
    a,b,c,d=bounds(mask)
    if not (.20*th<b<.83*th and c-a>.15*tw and d-b>.10*th):continue
    burners.append(mask)
burners=sorted(burners,key=lambda m:(bounds(m)[1],bounds(m)[0]))
if len(burners)!=4:raise RuntimeError('Expected four separate top-view burners, found '+str(len(burners)))
for i,mask in enumerate(burners):
    a,b,c,d=bounds(mask)
    cx=((a+c)/2/tw-.5)*W;cy=(.5-(b+d)/2/th)*D
    height=.012
    local=mask[b:d,a:c]
    obj=polygon_hull({'front':np.ones((64,64),bool),'top':local},(c-a)/tw*W,(d-b)/th*D,height,name='burner_'+str(i+1),bevel_frac=.12,tolerance=.55)
    surface=top_surface(cx,cy)
    move_mesh(obj,(cx,cy,surface-.001))
    parts.append(('burner_'+str(i+1),obj,['top']))
    evidence.append({'part':'burner_'+str(i+1),'height_m':height,'source':'top part-map footprint; assumed 12 mm raised assembly, not individual coil wire'})

# Four foot locations measured from front and right part maps, reconstructed with existing geometry primitives.
frontfeet=[m for m in reds if normalized(m,'front')[1]>.93]
sidefeet=[m for m in comps(V['right']['cls']==sheetset.CLASSES['out'],10) if normalized(m,'right')[1]>.93]
for i,f in enumerate(frontfeet[:2]):
    u0,v0,u1,v1=normalized(f,'front');cx=((u0+u1)/2-.5)*W
    for j,s in enumerate(sidefeet[:2]):
        a,b,c,d=normalized(s,'right');cy=((a+c)/2-.5)*D
        h=max(.015,(v1-v0)*H)
        obj=core.cyl((u1-u0)*W/2,h,(cx,cy,h/2),mat=None,verts=24,bevel=.001,name='foot')
        parts.append(('foot_'+str(i*2+j+1),obj,['front']))

# Inserted into the external fresh-build runner before baking. No Hull files are edited.
from propkit.hull import hull_prop, silhouette, HULL_REPORT
companion=Image.open(OUT/'companion-sheet.png').convert('RGB')
component_boxes={
 'knob':{'front':(145,365,375,585),'right':(390,365,570,585),'back':(602,365,834,585),'left':(850,365,1030,585),'top':(1060,395,1277,570)},
 'burner':{'front':(128,145,374,290),'right':(378,145,597,290),'back':(605,145,840,300),'left':(846,145,1050,300),'top':(1052,80,1285,340)},
 'handle':{'front':(125,645,415,730),'right':(437,631,550,739),'back':(565,645,850,735),'left':(868,631,985,739),'top':(1009,635,1278,738)}
}
prototype_reports={}
def tri_count(obj):return sum(len(p.vertices)-2 for p in obj.data.polygons)
def cap_mesh(obj,limit):
    n=tri_count(obj)
    if n>limit:
        dec=obj.modifiers.new('External assembly triangle allocation','DECIMATE');dec.ratio=limit/n*.97
        core.apply_mods(obj)
    assert tri_count(obj)<=limit,(obj.name,tri_count(obj),limit)

for kind,crops in component_boxes.items():
    paths={};sil={};tight={}
    for view,bb in crops.items():
        path=RUN/(kind+'_'+view+'.png');companion.crop(bb).save(path)
        mask,image=silhouette(str(path))
        sil[view]=(mask,image)
        tightpath=RUN/(kind+'_'+view+'_tight.png');image.save(tightpath);tight[view]=str(tightpath)
        paths[view]=str(path)
    old_items=[(key,obj,views) for key,obj,views in parts if (key.startswith(kind+'_') if kind!='handle' else key=='oven_handle')]
    assert len(old_items)==(1 if kind=='handle' else 4)
    example=old_items[0][1]
    bpy.context.view_layer.update()
    p=[example.matrix_world@Vector(c) for c in example.bound_box]
    elo=Vector([min(q[j] for q in p) for j in range(3)]);ehi=Vector([max(q[j] for q in p) for j in range(3)])
    w,d,h=ehi-elo
    if kind=='knob':d=.036
    elif kind=='burner':h=.065
    else:d=.065
    HULL_REPORT.clear()
    if kind=='handle':
        proto=polygon_hull({k:v[0] for k,v in sil.items()},float(w),float(d),float(h),name='companion_handle',bevel_frac=.02,tolerance=.8)
    else:
        proto=hull_prop({},float(h),width_m=float(w),depth_m=float(d),sil_override=sil,name='companion_'+kind,
                        res=72,paint=False,features=False,sections=False,revolve=True,smooth_iters=2,decimate=.12)
    # One explicit budget for every copy; no repeated independent 6000-triangle allocations.
    allowance={'knob':400,'burner':800,'handle':650}[kind]
    cap_mesh(proto,allowance)
    report=json.loads(json.dumps(HULL_REPORT,default=str))
    texturing.project(proto,tight,float(w),float(d),float(h),others=[],name='companion_'+kind,rough=.65)
    for key,old,_ in old_items:
        pp=[old.matrix_world@Vector(c) for c in old.bound_box]
        lo=Vector([min(q[j] for q in pp) for j in range(3)]);hi=Vector([max(q[j] for q in pp) for j in range(3)])
        center=(lo+hi)/2
        obj=bpy.data.objects.new(key+'_fresh',proto.data.copy());bpy.context.collection.objects.link(obj)
        if kind=='knob':
            offset=(center.x,front_surface(center.x,center.z)+d/2-.024,center.z-h/2)
        elif kind=='burner':
            offset=(center.x,center.y,top_surface(center.x,center.y)-.040)
        else:
            offset=(center.x,panel_objects['oven_door'][2]+d/2-.055,center.z-h/2)
        move_mesh(obj,offset)
        parts[:]=[(k,(obj if k==key else o),([] if k==key else vv)) for k,o,vv in parts]
        if old in core.PARTS:core.PARTS.remove(old)
        bpy.data.objects.remove(old,do_unlink=True);obj.name=key
    if proto in core.PARTS:core.PARTS.remove(proto)
    bpy.data.objects.remove(proto,do_unlink=True)
    prototype_reports[kind]={'source':crops,'per_copy_budget':allowance,'reconstruction':report}

for key,obj,views in parts:
    if key=='stove_body':limit=2400
    elif key in ('oven_door','storage_drawer'):limit=450
    elif key.startswith('foot_'):limit=100
    elif key.startswith('clock_button'):limit=60
    elif key=='unobserved_inner_backing':limit=40
    else:continue
    cap_mesh(obj,limit)
allocation={key:tri_count(obj) for key,obj,_ in parts}
assert sum(allocation.values())<=10000,allocation
(OUT/'triangle-plan.json').write_text(json.dumps({'target':10000,'hard_limit':12000,'before_bake':allocation,
    'before_bake_total':sum(allocation.values()),'companion_prototypes':prototype_reports},indent=2))
print('ASSEMBLY_TRIANGLES_BEFORE_BAKE',sum(allocation.values()),allocation,flush=True)

all_objs=[o for _,o,_ in parts]
bpy.context.view_layer.update()
for key,obj,views in parts:
    if views:texturing.project(obj,{k:V[k]['path'] for k in views},W,D,H,others=[],name=key,rough=.65)
    group=obj.vertex_groups.new(name='part__'+key)
    group.add(list(range(len(obj.data.vertices))),1.0,'REPLACE')
    obj.name=key
print('PARTS_READY',[(k,len(o.data.polygons)) for k,o,_ in parts],flush=True)
core.PARTS[:]=all_objs
info=bake.finish('stove_1974_companion_build',str(RUN/'baked'),2048,16,tags=['appliance'])
(OUT/'build-report.json').write_text(json.dumps({'pipeline':'existing sheetset.view + polygon_hull + texturing.project + bake.finish; external per-part assembly',
    'source_code_modified':False,'part_evidence':evidence,'mesh':info,'seconds_to_bake':round(time.time()-started,2),
    'limitations':['Hidden oven interior is not in reference; only a shallow neutral backing is supplied.',
                  'Burner height assumed 12 mm; rings are painted, not separate coil-wire geometry.',
                  'External assembly explicitly identifies door and top burner components; this is not an unassisted stock sheetset build.']},indent=2))
for p in (RUN/'baked'/'stove_1974_companion_build').glob('*.png'):shutil.copy2(p,OUT/p.name)

# Restore standard baked material before splitting so every component shares the same atlas.
mat=bpy.data.materials.new('Baked stove parts');mat.use_nodes=True;nt=mat.node_tree;bs=nt.nodes['Principled BSDF']
def texture(suffix,space):
    n=nt.nodes.new('ShaderNodeTexImage');n.image=bpy.data.images.load(str(OUT/('stove_1974_companion_build_'+suffix+'.png')))
    n.image.colorspace_settings.name=space;return n
nt.links.new(texture('albedo','sRGB').outputs['Color'],bs.inputs['Base Color'])
n=nt.nodes.new('ShaderNodeNormalMap');nt.links.new(texture('normal','Non-Color').outputs['Color'],n.inputs['Color']);nt.links.new(n.outputs['Normal'],bs.inputs['Normal'])
s=nt.nodes.new('ShaderNodeSeparateColor');nt.links.new(texture('orm','Non-Color').outputs['Color'],s.inputs['Color']);nt.links.new(s.outputs['Green'],bs.inputs['Roughness']);nt.links.new(s.outputs['Blue'],bs.inputs['Metallic'])
joined=bpy.context.view_layer.objects.active;joined.data.materials.clear();joined.data.materials.append(mat)
for key,_,_ in parts[1:]:
    core.select_only(joined)
    group=joined.vertex_groups.get('part__'+key)
    if group is None:raise RuntimeError('Lost part group '+key)
    before=set(bpy.data.objects)
    joined.vertex_groups.active_index=group.index
    bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='DESELECT');bpy.ops.object.vertex_group_select();bpy.ops.mesh.separate(type='SELECTED');bpy.ops.object.mode_set(mode='OBJECT')
    new=set(bpy.data.objects)-before
    if len(new)!=1:raise RuntimeError('Failed to separate '+key)
    next(iter(new)).name=key
joined.name='stove_body'
hinge=bpy.data.objects.new('oven_door_hinge',None);bpy.context.collection.objects.link(hinge);hinge.location=pivot
bpy.context.view_layer.update()
for key in ['oven_door','oven_handle']:
    obj=bpy.data.objects.get(key)
    if obj:
        world=obj.matrix_world.copy();obj.parent=hinge;obj.matrix_parent_inverse=hinge.matrix_world.inverted();obj.matrix_world=world
hinge['note']='Bottom-edge door pivot; hidden interior has not been reconstructed.'
for obj in bpy.data.objects:
    if obj.type=='MESH':obj['generated_by']='Hull existing functions; external map-guided assembly'
bpy.ops.file.pack_all()
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'stove_1974_companion_build.blend'))
bpy.ops.object.select_all(action='SELECT')
bpy.ops.export_scene.gltf(filepath=str(OUT/'stove_1974_companion_build.glb'),export_format='GLB',use_selection=True)
print('PART_MODEL_DONE',round(time.time()-started,1),flush=True)




