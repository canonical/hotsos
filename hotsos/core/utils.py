import tempfile

from hotsos.core.config import HotSOSConfig


def cached_property(f):
    """
    This is used to cache properties and can be replaced once we no longer need
    to support versions of Python (< 3.8) that don't support
    functools.cached_property.
    """

    @property
    def _cached_property(self):
        key = "__cached_property_{}".format(f.__name__)
        try:
            if hasattr(self, key):
                return getattr(self, key)
        except AttributeError:
            pass

        val = f(self)
        setattr(self, key, val)
        return val

    return _cached_property


def sorted_dict(d, key=None, reverse=False):
    """
    Return dictionary sorted using key. If no key provided sorted by dict keys.
    """
    if key is None:
        return dict(sorted(d.items(), key=lambda e: e[0], reverse=reverse))

    return dict(sorted(d.items(), key=key, reverse=reverse))


def mktemp_dump(data, prefix=None):
    """Create a temporary file under the current plugin tmp directory and write
    data to the file.
    """
    if prefix is not None:
        ftmp = tempfile.mktemp(prefix=prefix, dir=HotSOSConfig.plugin_tmp_dir)
    else:
        ftmp = tempfile.mktemp(dir=HotSOSConfig.plugin_tmp_dir)

    with open(ftmp, 'w') as fd:
        fd.write(data)

    return ftmp


def seconds_to_date(secs):
    days = secs / 86400
    hours = secs / 3600 % 24
    mins = secs / 60 % 60
    secs = secs % 60
    return '{}d:{}h:{}m:{}s'.format(int(days), int(hours),
                                    int(mins), int(secs))


def sample_set_regressions(samples, ascending=True):
    """
    Takes a sample set and determines the number of times the sequence
    regresses i.e. values go the opposite direction than is expected.

    The default is to expect values to be increasing but this can be reversed
    by setting ascending=False.
    """
    if ascending:
        prev_reset = min(samples)
    else:
        prev_reset = max(samples)

    prev = prev_reset
    repetitions = 0
    for s in samples:
        if ascending and s >= prev:
            prev = s
        elif not ascending and s <= prev:
            prev = s
        else:
            repetitions += 1
            prev = prev_reset

    return repetitions
