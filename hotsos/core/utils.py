import fasteners
import os
import pickle
import tempfile

from hotsos.core.log import log
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


def mktemp_dump(data):
    """Create a temporary file under the current plugin tmp directory and write
    data to the file.
    """
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


class MPCache(object):
    """
    A multiprocessing safe cache.
    """
    def __init__(self, id, root_dir):
        self.id = id
        self.root_dir = root_dir

    @property
    def _global_lock(self):
        """ Inter-process lock for all caches. """
        path = os.path.join(HotSOSConfig.global_tmp_dir, 'locks',
                            'cache_all.lock')
        return fasteners.InterProcessLock(path)

    @property
    def _cache_lock(self):
        """ Inter-process lock for this cache. """
        path = os.path.join(HotSOSConfig.global_tmp_dir, 'locks',
                            'cache_{}.lock'.format(self.id))
        return fasteners.InterProcessLock(path)

    @cached_property
    def cache_path(self):
        """
        Get cache path. Takes global cache lock to check root is created.
        """
        globaltmp = HotSOSConfig.global_tmp_dir
        if globaltmp is None:
            log.warning("global tmp dir '%s' not setup")
            return

        dir = os.path.join(globaltmp, 'cache/{}'.format(self.root_dir))
        with self._global_lock:
            if not os.path.isdir(dir):
                os.makedirs(dir)

        return os.path.join(dir, self.id)

    def _get_unsafe(self, path):
        """
        Unlocked get not to be used without having first acquired the lock.
        """
        if not path or not os.path.exists(path):
            log.debug("no cache found at '%s'", path)
            return

        with open(path, 'rb') as fd:
            contents = pickle.load(fd)
            if not contents:
                return

            return contents

    def get(self, key):
        """ Get value for key. If not found returns None. """
        path = self.cache_path
        with self._cache_lock:
            log.debug("load from cache '%s' (key='%s')", path, key)
            contents = self._get_unsafe(path)
            if contents:
                return contents.get(key)

    def set(self, key, data):
        """ Set value for key. """
        path = self.cache_path
        with self._cache_lock:
            if not path:
                log.warning("invalid path '%s' - cannot save to cache", path)

            contents = self._get_unsafe(path)
            if contents:
                contents[key] = data
            else:
                contents = {key: data}

            log.debug("saving to cache '%s' (key=%s, items=%s)", path, key,
                      len(contents))
            with open(path, 'wb') as fd:
                pickle.dump(contents, fd)

            log.debug("cache id=%s size=%s", self.id, os.path.getsize(path))
