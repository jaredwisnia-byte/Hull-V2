"""Local CPU worker for the registered published MatchED-BIPED checkpoint."""
import argparse
import contextlib
import importlib.metadata
import json
from pathlib import Path
import sys
import time


def versions():
    import numpy
    import scipy
    import torch
    import skimage
    return {'numpy': numpy.__version__, 'scipy': scipy.__version__, 'torch': torch.__version__,
            'phasepack': importlib.metadata.version('phasepack'), 'scikit_image': skimage.__version__,
            'python': sys.version.split()[0]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--describe', action='store_true')
    parser.add_argument('--config', type=Path)
    parser.add_argument('--input', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.describe:
        metadata = {}
        for name in ('numpy', 'scipy', 'torch', 'phasepack', 'scikit-image'):
            distribution = importlib.metadata.distribution(name)
            for item in distribution.files or ():
                if str(item).endswith('.dist-info/METADATA'):
                    metadata[name] = str(
                        distribution.locate_file(item).resolve())
                    break
        print(json.dumps({'versions': versions(), 'metadata': metadata}))
        return
    from types import SimpleNamespace
    from unittest.mock import patch
    import numpy as np
    import torch
    from scipy import ndimage
    from skimage.filters import apply_hysteresis_threshold
    from skimage.morphology import skeletonize
    from phasepack import phasecong
    config = json.loads(args.config.read_text(encoding='utf-8'))
    sys.path.insert(0, config['source'])
    started = time.perf_counter()
    with np.load(args.input, allow_pickle=False) as data:
        pixels, mask = data['pixels'], data['mask']
    torch.set_num_threads(4)
    with contextlib.redirect_stdout(sys.stderr):
        import models
        # The published constructor hard-codes .cuda() on its thinning module.
        # This scoped device-only adaptation leaves architecture/math unchanged.
        with patch.object(torch.nn.Module, 'cuda', lambda self, *a, **k: self):
            model = models.pidinet(SimpleNamespace(
                config='carv4', sa=True, dil=True)).cpu().eval()
        saved = torch.load(config['checkpoint'],
                           map_location='cpu', weights_only=True)
        state = saved.get('state_dict', saved)
        model.load_state_dict({key.removeprefix(
            'module.'): value for key, value in state.items()}, strict=True)
        rgb = pixels.astype(np.float32) / 255
        value = (rgb - np.array([.485, .456, .406], np.float32)
                 ) / np.array([.229, .224, .225], np.float32)
        tensor = torch.from_numpy(value.transpose(2, 0, 1).copy())[None]
        with torch.inference_mode():
            _, thin, _ = model(tensor, 11)
        structural_score = thin[0, 0].numpy()
        phase = np.nan_to_num(
            phasecong(rgb @ [.2126, .7152, .0722], nscale=4, norient=6)[0])
    interior = ndimage.binary_erosion(mask, iterations=2)
    structural = (structural_score > .5) & interior
    fine = skeletonize(apply_hysteresis_threshold(
        phase, .04, .10)) & interior & ~structural
    np.savez_compressed(args.output, structural=structural, fine_candidates=fine,
                        structural_score=np.where(
                            interior, structural_score, 0).astype(np.float32),
                        phase_score=np.where(interior, phase, 0).astype(np.float32))
    print(json.dumps({'versions': versions(),
          'seconds': time.perf_counter() - started}))


if __name__ == '__main__':
    main()
