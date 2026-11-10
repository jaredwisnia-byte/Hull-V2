"""Bounded local relief baked into normals, without adding export triangles."""
from pathlib import Path
import numpy as np
import bpy
from PIL import Image


def apply(obj, options, paintings, work, source_root):
    view = options['view']
    path = Path(work)/'surface-height.png'
    if options.get('height_map'):
        source = Path(options['height_map'])
        source = source if source.is_absolute() else source_root/source
        with Image.open(source) as image:
            image.convert('L').save(path)
        report = {'source':'supplied cropped height map'}
    else:
        from ..relief import view_relief
        try:
            height, report = view_relief(paintings[view], view)
        except ValueError as exc:
            if 'no object found' not in str(exc):
                raise
            return {'applied':False, 'reason':'no separable silhouette for shading inference', 'view':view}
        maximum = float(np.max(np.abs(height)))
        normalized = height / maximum if maximum > 0 else height
        Image.fromarray(np.uint8(np.clip(.5+.5*normalized,0,1)*255)).save(path)
        report['source'] = 'estimated from shading; not measured depth'
        match = report.get('shading_match', 0)
        if not np.isfinite(match) or match < options.get('minimum_match', .2):
            report.update({'applied':False, 'reason':'insufficient shading agreement', 'height_map':str(path)})
            return report
    material = obj.data.materials[-1]
    nodes = material.node_tree
    shader = nodes.nodes['Principled BSDF']
    attribute = nodes.nodes.new('ShaderNodeAttribute')
    attribute.attribute_name = 'uvp_'+view
    texture = nodes.nodes.new('ShaderNodeTexImage')
    texture.image = bpy.data.images.load(str(path))
    texture.image.colorspace_settings.name = 'Non-Color'
    bump = nodes.nodes.new('ShaderNodeBump')
    bump.inputs['Distance'].default_value = 2*options['depth_m']
    directions = {'front':(0,-1,0),'back':(0,1,0),'right':(1,0,0),'left':(-1,0,0),'top':(0,0,1)}
    direction = np.asarray(directions[view])
    weight = obj.data.color_attributes.new('surface_detail_weight', 'FLOAT_COLOR', 'CORNER')
    for face in obj.data.polygons:
        facing = max(0, float(np.asarray(face.normal) @ direction)) ** 8
        for index in face.loop_indices:
            weight.data[index].color = (facing,facing,facing,1)
    strength = nodes.nodes.new('ShaderNodeAttribute')
    strength.attribute_name = 'surface_detail_weight'
    nodes.links.new(strength.outputs['Fac'], bump.inputs['Strength'])
    nodes.links.new(attribute.outputs['Color'], texture.inputs['Vector'])
    nodes.links.new(texture.outputs['Color'], bump.inputs['Height'])
    nodes.links.new(bump.outputs['Normal'], shader.inputs['Normal'])
    report.update({'applied':True, 'view':view, 'depth_cap_m':options['depth_m'], 'height_map':str(path), 'output':'baked normal detail'})
    return report
