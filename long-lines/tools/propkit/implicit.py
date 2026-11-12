"""Metric boundary conditions for cell-centred signed fields (negative inside)."""
import numpy as np


def preserve_components(base, target, maximum_fragment_cells=8):
    """Remove only unresolved detached specks before reducing relief strength.

    Every original physical component keeps its dominant overlapping component,
    including originally tiny parts. Large splits, destroyed parts and merges
    still require conservative backoff. An unrelated one-cell remnant must not
    halve the detail of an entire object.
    """
    from scipy import ndimage
    from .correction_review import assess, Rejected
    original, expected = ndimage.label(base < 0)
    original_cavities = ndimage.binary_fill_holes(base < 0) & (base >= 0)
    removed_total = 0
    reviews = []
    initial_errors = None
    for attempt, scale in enumerate((1., .95, .9, .8, .5, .25)):
        candidate = (target.copy() if attempt == 0 else
                     base + (target - base) * scale)
        lost_cavity_cells = int(np.count_nonzero(original_cavities & (candidate < 0)))
        if lost_cavity_cells:
            raise Rejected(assess('original enclosed cavity was filled', 'alter unobserved interior',
                                 {'cavity_loss_cells': lost_cavity_cells},
                                 {'cavity_loss_cells': lost_cavity_cells},
                                 improve=['cavity_loss_cells'], limits={'cavity_loss_cells': (0, 0)}))
        labels, count = ndimage.label(candidate < 0)
        if initial_errors is None:
            initial_errors = abs(count - expected)
        sizes = np.bincount(labels.ravel(), minlength=count + 1)
        owners = []
        for part in range(1, expected + 1):
            overlap = np.bincount(
                labels[original == part], minlength=count + 1)
            overlap[0] = 0
            owners.append(int(overlap.argmax()) if overlap.any() else 0)
        keep = set(owners) - {0}
        fragments = [i for i in range(1, count + 1)
                     if i not in keep and sizes[i] <= maximum_fragment_cells]
        removed = int(sizes[fragments].sum()) if fragments else 0
        if fragments:
            discard = np.zeros(count + 1, bool)
            discard[fragments] = True
            selected = discard[labels]
            candidate[selected] = np.maximum(
                abs(candidate[selected]), np.finfo(np.float32).eps)
        # A disconnected positive cell creates an inner mesh shell even when
        # the solid itself is connected. Preserve original cavities and open
        # grooves; repair only newly enclosed grid-scale air pockets.
        enclosed = ndimage.binary_fill_holes(candidate < 0) & (candidate >= 0)
        pockets, pocket_count = ndimage.label(enclosed)
        pocket_sizes = np.bincount(pockets.ravel(), minlength=pocket_count + 1)
        existing = set(np.unique(pockets[original_cavities])) - {0}
        new_pockets = [i for i in range(
            1, pocket_count + 1) if i not in existing]
        fill_ids = [i for i in new_pockets if pocket_sizes[i]
                    <= maximum_fragment_cells]
        filled = int(pocket_sizes[fill_ids].sum()) if fill_ids else 0
        if fill_ids:
            lookup = np.zeros(pocket_count + 1, bool)
            lookup[fill_ids] = True
            fill = lookup[pockets]
            candidate[fill] = - \
                np.maximum(abs(candidate[fill]), np.finfo(np.float32).eps)
        # Distinct original parts must not silently merge. Nontrivial splits
        # also remain a failure even when their component count coincides.
        valid = (0 not in owners and len(keep) == expected
                 and count - len(fragments) == expected
                 and len(fill_ids) == len(new_pockets))
        if filled and expected > 1:
            valid = valid and ndimage.label(candidate < 0)[1] == expected
        if valid:
            if count != expected or scale != 1. or filled:
                review = assess('solid component mismatch', 'repair detached grid fragments and enclosed grid pockets',
                                {'component_errors': initial_errors +
                                    len(new_pockets)},
                                {'component_errors': 0, 'detail_retention': scale,
                                 'discarded_solid_fraction': removed / max(1, int(np.count_nonzero(original))),
                                 'filled_solid_fraction': filled / max(1, int(np.count_nonzero(original)))},
                                improve=['component_errors'],
                                limits={'component_errors': (0, 0), 'detail_retention': (.8, 1.),
                                        'discarded_solid_fraction': (0, .001), 'filled_solid_fraction': (0, .001)})
                reviews.append(review)
                if not review['accepted']:
                    raise Rejected(review)
            return candidate, {'baseline_solid_components': int(expected),
                               'detail_scale': scale,
                               'removed_fragment_components': len(fragments),
                               'removed_fragment_cells': removed,
                               'filled_new_cavity_components': len(fill_ids),
                               'filled_new_cavity_cells': filled,
                               'maximum_fragment_cells': maximum_fragment_cells,
                               'correction_reviews': reviews,
                               'method': 'preserve original components; remove detached grid-scale fragments before backoff'}
        removed_total += removed
    raise Rejected(assess('unresolved solid component conflict', 'discard all inferred relief',
                          {'component_errors': max(1, abs(count - expected))},
                          {'component_errors': 0, 'detail_retention': 0.},
                          improve=['component_errors'], limits={'detail_retention': (.8, 1.)}))


def bounded_field(field, dimensions):
    """Intersect with the physical sampling box before adding interior detail.

    Silhouette extrusions can be unbounded along a camera axis. Explicit box
    distances give the boundary cells the same metric meaning as interior cells.
    """
    result = np.asarray(field, dtype=np.float32).copy()
    for axis, (count, span) in enumerate(zip(field.shape, dimensions)):
        distance = (np.abs((np.arange(count) + .5) / count - .5) - .5) * span
        shape = [1, 1, 1]
        shape[axis] = count
        np.maximum(result, distance.reshape(shape), out=result)
    return result


def pad_field(field, dimensions):
    """One exterior cell layer at metric half-voxel distances.

    A constant unrelated to voxel size shifts a zero crossing towards the first
    interior cell, shrinking the shape and flattening shallow crowns.
    """
    result = np.pad(np.asarray(field, dtype=np.float32), 1, mode='edge')
    for axis, (count, span) in enumerate(zip(field.shape, dimensions)):
        for index in (0, -1):
            section = [slice(None)] * 3
            section[axis] = index
            face = result[tuple(section)]
            np.maximum(face, span / count / 2, out=face)
    return result
