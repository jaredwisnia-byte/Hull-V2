"""Shared dimension/attachment evidence and technical projections of real meshes.

Sections are intersections with the reconstructed mesh, never invented interiors.
"""
import json
from pathlib import Path
import numpy as np


def construction_graph(order):
    nodes=[]
    plan=order.get('parts')
    if plan is None:
        plan=[{'name':order['name'],'root':True}]
    parts={p['name']:p for p in plan}
    measured=order.get('measured',{}).get('parts',{})
    for name,part in parts.items():
        parent=part.get('attach',{}).get('to')
        ancestors={name}
        while parent:
            if parent not in parts or parent in ancestors:
                raise ValueError('invalid attachment graph at '+name)
            ancestors.add(parent)
            parent=parts[parent].get('attach',{}).get('to')
        box=part.get('vision_box',measured.get(name,{}).get('box_m'))
        if box is not None:
            box=np.asarray(box,dtype=float)
            if box.shape!=(6,) or not np.isfinite(box).all() or np.any(box[1::2]<=box[::2]):
                raise ValueError('invalid dimension constraints at '+name)
        depth=part.get('depth_inference')
        nodes.append({'id':name,'attachment':part.get('attach'),
                      'inferred_box_before_seating_m':None if box is None else box.tolist(),
                      'depth_evidence':depth,
                      'construction_used':'revolved_profile' if measured.get(name,{}).get('lathe') else 'multiview_sections_or_hull',
                      'uncertain':bool(depth and depth['needs_review'])})
    return {'scale_status':'estimated_from_physical_prior','units':'metres',
            'nodes':nodes,'constraints':['shared_height_axis','positive_dimensions','acyclic_attachments'],
            'seating':order.get('measured',{}).get('gaps_mm',[]),
            'unknown':['wall_thickness','unseen_internals','manufacturing_tolerances'],
            'production_ready':False}


def section_segments(vertices, triangles, height):
    result=[]
    for tri in np.asarray(vertices)[triangles]:
        points=[]
        for a,b in ((tri[0],tri[1]),(tri[1],tri[2]),(tri[2],tri[0])):
            if (a[2]<=height<b[2]) or (b[2]<=height<a[2]):
                t=(height-a[2])/(b[2]-a[2])
                points.append((a+t*(b-a))[:2])
        if len(points)==2:
            result.append(points)
    return np.asarray(result,dtype=float).reshape(-1,2,2)


def export(order,destination):
    """Use the loaded finished export, not the source paintings, for every line."""
    import bpy
    from PIL import Image,ImageDraw
    destination=Path(destination)
    vertices=[]; faces=[]
    for obj in bpy.context.scene.objects:
        if obj.type!='MESH':
            continue
        offset=len(vertices)
        vertices.extend(tuple(obj.matrix_world@v.co) for v in obj.data.vertices)
        obj.data.calc_loop_triangles()
        faces.extend(tuple(offset+i for i in t.vertices) for t in obj.data.loop_triangles)
    vertices=np.asarray(vertices); faces=np.asarray(faces)
    if not len(faces):
        raise ValueError('no finished mesh for technical drawings')
    lo,hi=vertices.min(0),vertices.max(0)
    center=(lo+hi)/2
    tile=420; scale=(tile-60)/max(hi-lo)
    sheet=Image.new('RGB',(tile*3,tile*2+60),'white'); draw=ImageDraw.Draw(sheet)
    draw.text((15,10),'Derived from reconstructed mesh; estimated dimensions; sections do not reveal actual internals',fill='black')
    def pixel(points,axes,column,row):
        return np.c_[column*tile+tile/2+(points[:,axes[0]]-center[axes[0]])*scale,
                     60+row*tile+tile/2-(points[:,axes[1]]-center[axes[1]])*scale]
    for column,(name,axes) in enumerate((('Front',(0,2)),('Right',(1,2)),('Top',(0,1)))):
        pts=pixel(vertices,axes,column,0)
        for tri in faces:
            draw.polygon([tuple(p) for p in pts[tri]],fill=(80,95,105))
        draw.text((column*tile+12,65),name,fill='black')
    for column,fraction in enumerate((.25,.5,.75)):
        height=lo[2]+fraction*(hi[2]-lo[2])
        segments=section_segments(vertices,faces,height)
        for segment in segments:
            points=np.c_[segment,np.full(2,height)]
            draw.line([tuple(p) for p in pixel(points,(0,1),column,1)],fill='black',width=2)
        draw.text((column*tile+12,65+tile),f'Section Z = {height*1000:.1f} mm (inferred)',fill='black')
    graph=construction_graph(order)
    graph['finished_envelope_m']=(hi-lo).tolist()
    graph['drawing_convention']='Common scale, orthographic silhouettes; horizontal mesh intersections, not inferred cavities'
    (destination/'engineering.json').write_text(json.dumps(graph,indent=2))
    sheet.save(destination/'technical-views.png')
    return {'engineering':str(destination/'engineering.json'),'technical_views':str(destination/'technical-views.png')}
