"""Filesystem paths accepted by Blender's embedded Python on Windows."""

import os


# Blender's image save and export operators do not consistently accept the
# extended Windows prefix used by ordinary Python file I/O. Leave room below
# the legacy 260-character limit for those operators and their internal paths.
BLENDER_WINDOWS_PATH_LIMIT = 247


def check_blender_export_paths(out_root, name, windows=None):
    """Reject an unsupported output path before creating a costly asset.

    The public asset name and its standard manifest filenames remain unchanged.
    This checks every filename passed to Blender's image-save or glTF exporter.
    """
    if windows is None:
        windows = os.name == 'nt'
    if not windows:
        return
    folder = os.path.abspath(os.path.join(os.fspath(out_root), name))
    filenames = (name + suffix for suffix in
                 ('_albedo.png', '_normal.png', '_orm.png', '.glb'))
    longest = max((os.path.join(folder, filename) for filename in filenames),
                  key=len)
    excess = len(longest) - BLENDER_WINDOWS_PATH_LIMIT
    if excess > 0:
        raise ValueError(
            'Blender export path is %d characters; Windows-safe budget is %d. '
            'Shorten the run root or asset name by at least %d characters before '
            'building. Target: %s' %
            (len(longest), BLENDER_WINDOWS_PATH_LIMIT, excess, longest))


def io_path(path):
    """Return an extended path when Blender's Windows process hits MAX_PATH.

    Keep ordinary paths in reports and manifests. This form is for Python
    file I/O only; Blender operators may not accept the extended prefix.
    """
    value = os.fspath(path)
    if os.name != 'nt' or value.startswith('\\\\?\\') or len(value) < 248:
        return value
    absolute = os.path.abspath(value)
    if absolute.startswith('\\\\'):
        return '\\\\?\\UNC\\' + absolute[2:]
    return '\\\\?\\' + absolute
