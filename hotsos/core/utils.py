import tempfile

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


def sort_suffixed_integers(values, reverse=False):
    """
    Given a list of values that contain numbers suffixed with a
    k/K/m/M/g/G/t/T/p/P, sort them taking into account their suffix.

    @param values: list of integer or string values
    @param reverse: sort order
    @return: sorted list of values (original type is maintained)
    """
    bysuffix = {}
    if reverse:
        valid_suffixes = ('p', 't', 'g', 'm', 'k', '_')
    else:
        valid_suffixes = ('_', 'k', 'm', 'g', 't', 'p')

    for item in values:
        if isinstance(item, str):
            if len(item) > 1:
                suffix = item[-1].lower()
                if suffix in valid_suffixes:
                    if suffix not in bysuffix:
                        bysuffix[suffix] = []

                    bysuffix[suffix].append(item)
                    continue

        if '_' not in bysuffix:
            bysuffix['_'] = []

        bysuffix['_'].append(item)

    if len(bysuffix.keys()) == 1 and '_' in bysuffix:
        return sorted(bysuffix['_'], key=lambda e: int(e), reverse=reverse)

    _sorted = []
    for suffix in valid_suffixes:
        if suffix not in bysuffix:
            continue

        if suffix == '_':
            _sorted += sorted(bysuffix[suffix], reverse=reverse,
                              key=lambda e: int(e))
        else:
            _sorted += sorted(bysuffix[suffix], reverse=reverse,
                              key=lambda e: int(e[:-1]))

    return _sorted
