import tempfile
from collections import namedtuple
from operator import attrgetter

from hotsos.core.config import HotSOSConfig


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

    with open(ftmp, 'w', encoding='utf-8') as fd:
        fd.write(data)

    return ftmp


def seconds_to_date(secs):
    days = int(secs / 86400)
    hours = int(secs / 3600 % 24)
    mins = int(secs / 60 % 60)
    secs = int(secs % 60)
    return f'{days}d:{hours}h:{mins}m:{secs}s'


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


def string_to_int_or_float(value):
    try:
        return int(value)
    except ValueError:
        return float(value)


def sort_suffixed_integers(values, reverse=False):
    """
    Given a list of values that contain numbers suffixed with a
    k/K/m/M/g/G/t/T/p/P, sort them taking into account their suffix.

    @param values: list of integer or string values
    @param reverse: sort order
    @return: sorted list of values (original type is maintained)
    """
    reals = []
    suffix_exps = {'p': 5, 't': 4, 'g': 3, 'm': 2, 'k': 1}
    if reverse:
        valid_suffixes = ('p', 't', 'g', 'm', 'k')
    else:
        valid_suffixes = ('k', 'm', 'g', 't', 'p')

    Entry = namedtuple('entry', ('raw', 'actual'))
    for item in values:
        if isinstance(item, str):
            if len(item) > 1:
                value = item[:-1]
                suffix = item[-1].lower()
                if suffix in valid_suffixes:
                    value = string_to_int_or_float(value)
                    value = value * 1024 ** suffix_exps[suffix]
                    reals.append(Entry(item, value))
                    continue

        value = string_to_int_or_float(item)
        reals.append(Entry(item, value))

    reals.sort(key=attrgetter('actual'), reverse=reverse)
    return [t.raw for t in reals]
