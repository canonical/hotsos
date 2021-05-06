import contextlib
import tempfile


from common import constants


def sorted_dict(d, key=None, reverse=False):
    """
    Return dictionary sorted using key. If no key provided sorted by dict keys.
    """
    if key is None:
        return dict(sorted(d.items(), key=lambda e: e[0], reverse=reverse))

    return dict(sorted(d.items(), key=key, reverse=reverse))


def mktemp_dump(data):
    """Create a temporary file under the current plugin tmp directory and write
    data to the file.
    """
    ftmp = tempfile.mktemp(dir=constants.PLUGIN_TMP_DIR)
    with open(ftmp, 'w') as fd:
        fd.write(data)

    return ftmp


class suppress(contextlib.suppress, contextlib.ContextDecorator):
    """Decorator to suppress the exceptions passed.

    @suppress(ValueError)
    def foo(value):
        if type(value) == int:
            # this will be effectively equivalent to 'return None' due to the
            # suppress decorator.
            raise ValueError("error")
        else:
            # callers will receive this exception, suppress will do nothing.
            raise IndexError("index error")
    """
