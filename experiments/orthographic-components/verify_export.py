"""Count actual triangles in an uncompressed GLB and enforce an assembly budget."""
import argparse,json,struct
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('glb');p.add_argument('--limit',type=int,required=True);a=p.parse_args()
data=Path(a.glb).read_bytes();length,kind=struct.unpack_from('<II',data,12);assert kind==0x4E4F534A
doc=json.loads(data[20:20+length]);count=0
for mesh in doc.get('meshes',[]):
    for primitive in mesh['primitives']:
        assert primitive.get('mode',4)==4,'Expected triangles'
        count+=doc['accessors'][primitive['indices']]['count']//3
assert count<=a.limit,(count,a.limit)
print(json.dumps({'file':Path(a.glb).name,'triangles':count,'limit':a.limit,'pass':True}))
