import subprocess
import tempfile

from hotsos.core.config import HotSOSConfig
from hotsos.core.cli_helpers import CLIHelper


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
    ftmp = tempfile.mktemp(dir=HotSOSConfig.PLUGIN_TMP_DIR)
    with open(ftmp, 'w') as fd:
        fd.write(data)

    return ftmp


def get_date_secs(datestring=None):
    if datestring:
        cmd = ["date", "--utc", "--date={}".format(datestring), "+%s"]
        date_in_secs = subprocess.check_output(cmd)
    else:
        date_in_secs = CLIHelper().date() or 0
        if date_in_secs:
            date_in_secs = date_in_secs.strip()

    return int(date_in_secs)


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
