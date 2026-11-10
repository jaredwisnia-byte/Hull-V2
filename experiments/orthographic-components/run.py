"""Bootstrap an external Blender experiment without writing into Hull's source tree."""
import argparse,json,os,shutil,subprocess
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument('object',choices=['stove','camera'])
p.add_argument('--blender',required=True)
p.add_argument('--deps',required=True,help='Python 3.13-compatible pillow, scipy, scikit-image and numpy installation directory')
p.add_argument('--workdir',required=True,help='Writable working directory outside the checkout')
a=p.parse_args();here=Path(__file__).resolve().parent;repo=here.parents[1]
work=Path(a.workdir).resolve();work.mkdir(parents=True,exist_ok=True)
env=os.environ.copy();env['HULL_TOOLS']=str(repo/'long-lines'/'tools');env['HULL_PYTHON_DEPS']=str(Path(a.deps).resolve());env['HULL_WORKDIR']=str(work)
if a.object=='camera':
    for name in ['build.py','manifest.json']:shutil.copy2(here/'camera'/name,work/name)
    shutil.copy2(here/'camera'/'assets'/'reference-sheet.png',work/'reference-sheet.png')
    env['HULL_OUTPUT']=str(work/'outputs');script=work/'build.py'
else:
    out=work/'outputs'/'stove_1974_companion_build';out.mkdir(parents=True,exist_ok=True)
    for asset in (here/'stove'/'assets').glob('*.png'):shutil.copy2(asset,out/asset.name)
    env['HULL_REFERENCE']=str(out/'painted-sheet.png')
    # Reference and destination must differ because the stove runner archives its input.
    shutil.copy2(out/'painted-sheet.png',work/'stove-reference.png');env['HULL_REFERENCE']=str(work/'stove-reference.png')
    script=here/'stove'/'build.py'
subprocess.run([a.blender,'-b','--factory-startup','--python-exit-code','1','-P',str(script)],env=env,check=True)
