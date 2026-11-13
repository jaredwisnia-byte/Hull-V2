"""Filesystem paths accepted by Blender's embedded Python on Windows."""

import os


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
