import abc
import os
import re
import sys
from datetime import datetime
from functools import cached_property

from hotsos.core.config import HotSOSConfig
from hotsos.core.factory import FactoryBase
from hotsos.core.host_helpers import (
    APTPackageHelper,
    CLIHelper,
    CLIHelperFile,
    DPKGVersion,
    HostNetworkingHelper,
    PebbleHelper,
    SnapPackageHelper,
    SystemdHelper,
    IniConfigBase,
)
from hotsos.core.log import log
from hotsos.core.plugins.kernel.net import Lsof
from hotsos.core.plugins.storage import StorageBase
from hotsos.core.plugins.storage.bcache import BcacheBase
from hotsos.core.plugins.storage.ceph.daemon import CephOSD
from hotsos.core.plugins.storage.ceph.cluster import CephCluster
from hotsos.core.search import (
    FileSearcher,
    SequenceSearchDef,
    SearchDef
)
from hotsos.core.ycheck.events import EventCallbackBase

CEPH_SERVICES_EXPRS = [r"ceph-[a-z0-9-]+",
                       r"rados[a-z0-9-:]+",
                       r"microceph.(mon|mgr|mds|osd|rgw)"]
CEPH_PKGS_CORE = [r"ceph",
                  r"rados",
                  r"rbd",
                  ]
CEPH_PKGS_OTHER = []
# Add in clients/deps
for ceph_pkg in CEPH_PKGS_CORE:
    CEPH_PKGS_OTHER.append(rf"python3?-{ceph_pkg}\S*")

CEPH_SNAPS_CORE = [r'microceph']

# NOTE(tpsilva): when updating this list, refer to the supported Ceph
# versions for Ubuntu page:
# https://ubuntu.com/ceph/docs/supported-ceph-versions
CEPH_EOL_INFO = {
    'reef': datetime(2034, 4, 30),
    'quincy': datetime(2032, 4, 30),
    'pacific': datetime(2024, 4, 30),
    'octopus': datetime(2030, 4, 30),
    'nautilus': datetime(2021, 2, 28),
    'mimic': datetime(2022, 4, 30),
    'luminous': datetime(2028, 4, 30),
    'jewel': datetime(2024, 4, 30)
}

CEPH_REL_INFO = {
    'ceph-common': {
        'reef': '18.0',
        'quincy': '17.0',
        'pacific': '16.0',
        'octopus': '15.0',
        'nautilus': '14.0',
        'mimic': '13.0',
        'luminous': '12.0',
        'kraken': '11.0',
        'jewel': '10.0'},
}


def csv_to_set(f):
    """
    Decorator used to convert a csv string to a set().
    """
    def csv_to_set_inner(*args, **kwargs):
        val = f(*args, **kwargs)
        if val is not None:
            return set(v.strip(',') for v in val.split())

        return set([])

    return csv_to_set_inner


class CephConfig(IniConfigBase):
    """
    Ceph config.

    Adds support for specific format used in Ceph config files.
    """
    def __init__(self, *args, **kwargs):
        path = os.path.join(HotSOSConfig.data_root, 'etc/ceph/ceph.conf')
        super().__init__(*args, path=path, **kwargs)

    def get(self, key, *args, **kwargs):
        """
        First to get value for key and if not found, try alternative key format
        i.e. ceph config like 'ceph osd debug' and 'ceph_osd_debug' are both
        valid and equivalent so we try both by converting the key name. If that
        still does not match we look for key in this object instance since it
        may have been provided as a property.
        """
        val = super().get(key, *args, **kwargs)
        if val is not None:
            return val

        orig_key = key
        if ' ' in key:
            key = key.replace(' ', '_')
        else:
            key = key.replace('_', ' ')

        val = super().get(key, *args, **kwargs)
        if val is not None:
            return val

        if hasattr(self, orig_key):
            return getattr(self, orig_key)

        return None

    @property
    @csv_to_set
    def cluster_network_set(self):
        return self.get('cluster network')

    @property
    @csv_to_set
    def public_network_set(self):
        return self.get('public network')


class CephChecks(StorageBase):
    """ Ceph Checks. """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ceph_config = CephConfig()
        self.bcache = BcacheBase()
        self.apt = APTPackageHelper(core_pkgs=CEPH_PKGS_CORE,
                                    other_pkgs=CEPH_PKGS_OTHER)
        self.snaps = SnapPackageHelper(core_snaps=CEPH_SNAPS_CORE)
        self.pebble = PebbleHelper(service_exprs=CEPH_SERVICES_EXPRS)
        self.systemd = SystemdHelper(service_exprs=CEPH_SERVICES_EXPRS)
        self.cluster = CephCluster()

    @property
    def summary_subkey_include_default_entries(self):
        return True

    @property
    def summary_subkey(self):
        return 'ceph'

    @property
    def plugin_runnable(self):
        if self.apt.core or self.snaps.core:
            return True

        return False

    @cached_property
    def release_name(self):
        relname = 'unknown'

        pkg = 'ceph-common'
        pkg_version = None
        if self.apt.core and pkg in self.apt.core:
            pkg_version = self.apt.core[pkg]
        elif self.snaps.core and 'microceph' in self.snaps.core:
            pkg_version = self.snaps.core['microceph']['version']
            pkg_version = pkg_version.partition("+snap")[0]

        if pkg_version is not None:
            for rel, ver in sorted(CEPH_REL_INFO[pkg].items(),
                                   key=lambda i: i[1], reverse=True):
                if pkg_version > DPKGVersion(ver):
                    relname = rel
                    break

        return relname

    @cached_property
    def days_to_eol(self):
        if self.release_name == 'unknown':
            return None

        eol = CEPH_EOL_INFO[self.release_name]
        today = datetime.utcfromtimestamp(int(CLIHelper().date()))
        delta = (eol - today).days
        return delta

    def _get_bind_interfaces(self, iface_type):
        """
        For the given config network type determine what interface ceph is
        binding to.

        @param iface_type: cluster or public
        """
        net = self.ceph_config.get(f'{iface_type} network')
        addr = self.ceph_config.get(f'{iface_type} addr')
        if not any([net, addr]):
            return {}

        nethelp = HostNetworkingHelper()
        port = None
        if net:
            port = nethelp.get_interface_with_addr(net)
        elif addr:
            port = nethelp.get_interface_with_addr(addr)

        if port:
            return {iface_type: port}

        return None

    @cached_property
    def _ceph_bind_interfaces(self):
        """
        Returns a dict of network interfaces used by Ceph daemons on this host.
        The dict has the form {<type>: [<port>, ...]}
        """
        interfaces = {}
        for iface_type in ['cluster', 'public']:
            ret = self._get_bind_interfaces(iface_type)
            if ret:
                interfaces.update(ret)

        return interfaces

    @property
    def bind_interfaces(self):
        return self._ceph_bind_interfaces

    @cached_property
    def bind_interface_names(self):
        """
        Returns a list of names for network interfaces used by Ceph daemons on
        this host.
        """
        names = [iface.name for iface in self.bind_interfaces.values()]
        return ', '.join(list(set(names)))

    @cached_property
    def local_osds(self):
        """
        Returns a list of CephOSD objects for osds found on the local host.
        """
        osds = []

        s = FileSearcher()
        sd = SequenceSearchDef(start=SearchDef(r"^=+\s+osd\.(\d+)\s+=+.*"),
                               body=SearchDef([r"\s+osd\s+(fsid)\s+(\S+)\s*",
                                               r"\s+(devices)\s+([\S]+)\s*"]),
                               tag="ceph-lvm")
        with CLIHelperFile() as cli:
            fout = cli.ceph_volume_lvm_list()
            s.add(sd, path=fout)
            for results in s.run().find_sequence_sections(sd).values():
                osdid = None
                fsid = None
                dev = None
                for result in results:
                    if result.tag == sd.start_tag:
                        osdid = int(result.get(1))
                    elif result.tag == sd.body_tag:
                        if result.get(1) == "fsid":
                            fsid = result.get(2)
                        elif result.get(1) == "devices":
                            dev = result.get(2)

                osds.append(CephOSD(osdid, fsid, dev))

        return osds

    @cached_property
    def local_osds_use_bcache(self):
        """
        Returns True if any local osds are using bcache devices.
        """
        for osd in self.local_osds:
            if self.bcache.is_bcache_device(osd.device):
                return True

        return False

    @cached_property
    def local_osds_devtypes(self):
        return [osd.devtype for osd in self.local_osds]

    @cached_property
    def bluestore_enabled(self):
        """
        If any of the following are enabled in ceph.conf (by the charm) it
        indicates that bluestore=True.
        """
        bs_key_vals = {('enable experimental unrecoverable data corrupting '
                        'features'): 'bluestore',
                       'osd objectstore': 'bluestore'}
        bs_keys = ['bluestore block wal size', 'bluestore block db size',
                   r'bluestore compression .+']

        for keys in self.ceph_config.all_keys:
            for conf_key in keys:
                if conf_key in bs_keys:
                    return True

                for key in bs_keys:
                    if re.compile(key).match(conf_key):
                        return True

        for key, val in bs_key_vals.items():
            conf_val = self.ceph_config.get(key)
            if conf_val and val in conf_val:
                return True

        return False

    @cached_property
    def has_interface_errors(self):
        """
        Checks if any network interfaces used by Ceph are showing packet
        errors.

        Returns True if errors found otherwise False.
        """
        for port in self.bind_interfaces.values():
            for stats in port.stats.values():
                if stats.get('errors'):
                    return True

        return False

    @cached_property
    def linked_with_tcmalloc(self):
        """
        Checks that each ceph-osd process has libtcmalloc linked.

        Returns True if every OSD has it linked, otherwise False.
        """
        osds = {}
        tcmalloc_osds = 0
        for row in Lsof():
            if row.COMMAND == 'ceph-osd':
                osds[row.PID] = 1
                if re.search("libtcmalloc", row.NAME):
                    tcmalloc_osds += 1

        return len(osds) == tcmalloc_osds


class CephDaemonCommand():
    """
    This class is used to run a ceph daemon command that must be supported by
    CLIHelper. Attributes of the output can then be retrieved by calling them
    on the returned object.
    """
    def __init__(self, command, *args, **kwargs):
        self.command = command
        self.output = getattr(CLIHelper(), command)(*args, **kwargs)

    def __getattr__(self, name):
        if name in self.output:
            return self.output[name]

        raise AttributeError(f"{name} not found in output of {self.command}")


class CephDaemonConfigShow():
    """ Interface to ceph daemon config show command. """
    def __init__(self, osd_id):
        self.cmd = CephDaemonCommand('ceph_daemon_osd_config_show',
                                     osd_id=osd_id)

    def __getattr__(self, name):
        return getattr(self.cmd, name)


class CephDaemonDumpMemPools():
    """ Interface to ceph daemon osd dump mempools. """
    def __init__(self, osd_id):
        self.cmd = CephDaemonCommand('ceph_daemon_osd_dump_mempools',
                                     osd_id=osd_id)

    def __getattr__(self, name):
        val = getattr(self.cmd, 'mempool')
        if val:
            return val.get('by_pool', {}).get(name, {}).get('items')

        return None


class CephDaemonAllOSDsCommand():
    """
    This class is used to run CephDaemonCommand for all local OSDs.
    """
    def __init__(self, command):
        self.checks_base = CephChecks()
        self.command = command

    def __getattr__(self, name=None):
        """
        First instantiates the requested ceph daemon command handler then
        retrieves the requested attribute/operand and returns as a list of
        unique values.
        """
        vals = set()
        for osd in self.checks_base.local_osds:
            try:
                config = getattr(sys.modules[__name__],
                                 self.command)(osd_id=osd.id)
            except ImportError:
                log.warning("no ceph daemon command handler found for '%s'")
                break

            if hasattr(config, name):
                vals.add(getattr(config, name))

        return list(vals)


class CephDaemonAllOSDsFactory(FactoryBase):
    """
    A factory interface to allow dynamic access to ceph daemon commands and
    attributes of the output.
    """

    def __getattr__(self, command):
        return CephDaemonAllOSDsCommand(command)


class CephEventCallbackBase(EventCallbackBase):
    """ Base class for ceph event callbacks. """

    @abc.abstractmethod
    def __call__(self):
        """ Callback method. """
