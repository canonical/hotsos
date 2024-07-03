import glob
import os
import re
from functools import cached_property

from hotsos.core.config import HotSOSConfig
from hotsos.core.host_helpers import CLIHelper, CLIHelperFile
from hotsos.core.host_helpers.config import ConfigBase
from hotsos.core.plugins.storage import StorageBase
from hotsos.core.search import (
    FileSearcher,
    SequenceSearchDef,
    SearchDef
)
from hotsos.core.utils import sort_suffixed_integers


class BcacheConfig(ConfigBase):

    def get(self, key, section=None, expand_to_list=False):
        cfg = os.path.join(self.path, key)
        if os.path.exists(cfg):
            with open(cfg) as fd:
                return fd.read().strip()


class BDev():

    def __init__(self, path, cache):
        self.cache = cache
        self.path = path

    @property
    def cfg(self):
        return BcacheConfig(self.path)

    @property
    def dev_to_dname(self):
        for line in CLIHelper().udevadm_info_dev(device=self.dev):
            expr = r'.+\s+disk/by-dname/(.+)'
            ret = re.compile(expr).match(line)
            if ret:
                return ret[1]

    @property
    def dev(self):
        return os.path.basename(os.path.realpath(os.path.join(self.path,
                                                              'dev')))

    @cached_property
    def name(self):
        return os.path.basename(self.path)

    def __getattr__(self, key):
        cfg = os.path.join(self.path, key)
        if os.path.exists(cfg):
            with open(cfg) as fd:
                return fd.read().strip()

        raise AttributeError("{} not found in bdev config".format(key))


class Cacheset():

    def __init__(self, path):
        self.path = path
        self.bdevs = []

        self.uuid = os.path.basename(self.path)
        for bdev in glob.glob(os.path.join(self.path, 'bdev*')):
            self.bdevs.append(BDev(bdev, self))

    @cached_property
    def cfg(self):
        return BcacheConfig(self.path)

    def __getattr__(self, key):
        cfg = os.path.join(self.path, key)
        if os.path.exists(cfg):
            with open(cfg) as fd:
                return fd.read().strip()

        raise AttributeError("{} not found in cacheset config".format(key))


class BcacheBase(StorageBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cachesets = []

        for entry in glob.glob(os.path.join(HotSOSConfig.data_root,
                               'sys/fs/bcache/*')):
            if not os.path.isdir(entry):
                continue

            if not os.path.exists(os.path.join(entry,
                                               'cache_available_percent')):
                continue

            self.cachesets.append(Cacheset(entry))

    @cached_property
    def bcache_enabled(self):
        """ Return True if there are any backing devices configured. """
        if self.cachesets:
            for cset in self.cachesets:
                if cset.bdevs:
                    return True

        return False

    @property
    def plugin_runnable(self):
        return self.bcache_enabled

    @cached_property
    def udev_bcache_devs(self):
        """ If bcache devices exist fetch information and return as a list. """
        devs = []
        with CLIHelperFile() as cli:
            s = FileSearcher()
            sdef = SequenceSearchDef(start=SearchDef(r"^P: .+/(bcache\S+)"),
                                     body=SearchDef(r"^S: disk/by-uuid/(\S+)"),
                                     tag="bcacheinfo")
            s.add(sdef, cli.udevadm_info_exportdb())
            results = s.run()
            for section in results.find_sequence_sections(sdef).values():
                dev = {}
                for r in section:
                    if r.tag == sdef.start_tag:
                        dev["name"] = r.get(1)
                    else:
                        dev["by-uuid"] = r.get(1)

                devs.append(dev)

        return devs

    def resolve_bdev_from_dev(self, devpath):
        """
        Given a device path, resolve it to a corresponding bcache BDev object.
        """
        bcache_name = None
        if 'bcache' in devpath:
            bcache_name = os.path.basename(devpath)
        else:
            ret = re.compile(r"/dev/mapper/crypt-(\S+)").search(devpath)
            if ret:
                for udev_dev in self.udev_bcache_devs:
                    if 'name' not in udev_dev:
                        continue

                    _uuid = udev_dev.get("by-uuid")
                    if not _uuid or _uuid != ret.group(1):
                        continue

                    bcache_name = udev_dev['name']

        if bcache_name:
            for cset in self.cachesets:
                for bdev in cset.bdevs:
                    if bdev.dev == bcache_name:
                        return bdev

    def is_bcache_device(self, dev):
        """
        Returns True if the device either is or is backed by a bcache device
        e.g. dmcrypt device using bcache dev.
        """
        if dev.startswith("bcache"):
            return True

        if dev.startswith("/dev/bcache"):
            return True

        if self.resolve_bdev_from_dev(dev):
            return True

        return False


class BDevsInfo(BcacheBase):

    def _get_parameter(self, key):
        all_values = []
        for cset in self.cachesets:
            for bdev in cset.bdevs:
                all_values.append(bdev.cfg.get(key))

        return all_values

    @property
    def sequential_cutoff(self):
        """
        @return: list of <str> sequential_cutoff from each bdev sorted in
                 descending order. values can be int or float with our without
                 a suffix e.g. '2' or '0.0k'.
        """
        ret = self._get_parameter("sequential_cutoff")
        return sort_suffixed_integers(ret, reverse=True)

    @property
    def cache_mode(self):
        """
        @return: list of <str> cache_mode from each bdev sorted so that the
                 settings with writeback mode selected are at the end of the
                 list.
        """
        ret = self._get_parameter("cache_mode")
        # send [writeback] to the end of the list
        return sorted(ret,
                      key='writethrough [writeback] writearound none'.__eq__)

    @property
    def writeback_percent(self):
        """
        @return: list of <int> writeback_percent from each bdev sorted in
                 ascending order.
        """
        ret = self._get_parameter("writeback_percent")
        # convert str to int
        return sorted(list(map(int, ret)))


class CachesetsInfo(BcacheBase):

    def _get_parameter(self, key):
        return [cset.cfg.get(key) for cset in self.cachesets]

    @property
    def congested_read_threshold_us(self):
        """
        @return: list of <int> congested_read_threshold_us from each cacheset
                 sorted in descending order.
        """
        ret = self._get_parameter("congested_read_threshold_us")
        # convert str to int
        return sorted(list(map(int, ret)), reverse=True)

    @property
    def congested_write_threshold_us(self):
        """
        @return: list of <int> congested_write_threshold_us from each cacheset
                 sorted in descending order.
        """
        ret = self._get_parameter("congested_write_threshold_us")
        # convert str to int
        return sorted(list(map(int, ret)), reverse=True)

    @property
    def cache_available_percent(self):
        """
        @return: list of <int> cache_available_percent from each cacheset
                 sorted in ascending order.
        """
        ret = self._get_parameter("cache_available_percent")
        # convert str to int
        return sorted(list(map(int, ret)))


class BcacheChecksBase(BcacheBase):

    @property
    def summary_subkey(self):
        return 'bcache'
