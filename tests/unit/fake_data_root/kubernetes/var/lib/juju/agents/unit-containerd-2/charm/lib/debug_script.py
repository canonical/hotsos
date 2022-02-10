import os

dir = os.environ["DEBUG_SCRIPT_DIR"]


def open_file(path, *args, **kwargs):
    """ Open a file within the debug script dir """
    return open(os.path.join(dir, path), *args, **kwargs)
