import glob
import os
import re

from core import (
    checks,
    constants,
    host_helpers,
    plugintools,
    utils,
)
from core.cli_helpers import get_ps_axo_flags_available
from core.cli_helpers import CLIHelper
from core.searchtools import (
    FileSearcher,
    SequenceSearchDef,
    SearchDef
)
from core.utils import mktemp_dump


CEPH_SERVICES_EXPRS = [r"ceph-[a-z0-9-]+",
                       r"rados[a-z0-9-:]+"]
CEPH_PKGS_CORE = [r"ceph-[a-z-]+",
                  r"rados[a-z-]+",
                  r"rbd",
                  ]
CEPH_LOGS = "var/log/ceph/"


class StorageBase(plugintools.PluginPartBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class CephConfig(checks.SectionalConfigBase):
    def __init__(self, *args, **kwargs):
        path = os.path.join(constants.DATA_ROOT, 'etc/ceph/ceph.conf')
        super().__init__(path=path, *args, **kwargs)


class CephOSD(object):

    def __init__(self, id, fsid, device):
        self.cli = CLIHelper()
        self.date_in_secs = utils.get_date_secs()
        self.id = id
        self.fsid = fsid
        self.device = device
        self._devtype = None
        self._etime = None
        self._rss = None

    def to_dict(self):
        d = {self.id: {
             'fsid': self.fsid,
             'dev': self.device}}

        if self.devtype:
            d[self.id]['devtype'] = self.devtype

        if self.etime:
            d[self.id]['etime'] = self.etime

        if self.rss:
            d[self.id]['rss'] = self.rss

        return d

    @property
    def rss(self):
        """Return memory RSS for a given OSD.

        NOTE: this assumes we have ps auxwwwm format.
        """
        if self._rss:
            return self._rss

        f_osd_ps_cmds = mktemp_dump(''.join(self.cli.ps()))

        s = FileSearcher()
        # columns: USER PID %CPU %MEM VSZ RSS TTY STAT START TIME COMMAND
        sd = SearchDef(r"\S+\s+\d+\s+\S+\s+\S+\s+\d+\s+(\d+)\s+.+/ceph-osd\s+"
                       r".+--id\s+{}\s+.+".format(self.id))
        s.add_search_term(sd, path=f_osd_ps_cmds)
        rss = 0
        # we only expect one result
        for result in s.search().find_by_path(f_osd_ps_cmds):
            rss = int(int(result.get(1)) / 1024)
            break

        os.unlink(f_osd_ps_cmds)
        self._rss = "{}M".format(rss)
        return self._rss

    @property
    def etime(self):
        """Return process etime for a given OSD.

        To get etime we have to use ps_axo_flags rather than the default
        ps_auxww.
        """
        if self._etime:
            return self._etime

        if not get_ps_axo_flags_available():
            return

        ps_osds = []
        for line in self.cli.ps_axo_flags():
            ret = re.compile("ceph-osd").search(line)
            if not ret:
                continue

            expt_tmplt = checks.SVC_EXPR_TEMPLATES["absolute"]
            ret = re.compile(expt_tmplt.format("ceph-osd")).search(line)
            if ret:
                ps_osds.append(ret.group(0))

        if not ps_osds:
            return

        for cmd in ps_osds:
            ret = re.compile(r".+\s+.+--id {}\s+.+".format(
                             self.id)).match(cmd)
            if ret:
                osd_start = ' '.join(cmd.split()[13:17])
                if self.date_in_secs and osd_start:
                    osd_start_secs = utils.get_date_secs(datestring=osd_start)
                    osd_uptime_secs = (self.date_in_secs - osd_start_secs)
                    osd_uptime_str = utils.seconds_to_date(osd_uptime_secs)
                    self._etime = osd_uptime_str

        return self._etime

    @property
    def devtype(self):
        if self._devtype:
            return self._devtype

        for line in self.cli.ceph_osd_tree():
            if line.split()[3] == "osd.{}".format(self.id):
                self._devtype = line.split()[1]

        return self._devtype


class CephBase(StorageBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ceph_config = CephConfig()
        self._bcache_info = []
        self._osds = {}
        self.cli = CLIHelper()
        udevadm_db = self.cli.udevadm_info_exportdb()
        self.udevadm_db = None
        if udevadm_db:
            self.udevadm_db = utils.mktemp_dump('\n'.join(udevadm_db))

        ceph_volume_lvm_list = self.cli.ceph_volume_lvm_list()
        self.f_ceph_volume_lvm_list = None
        if ceph_volume_lvm_list:
            self.f_ceph_volume_lvm_list = mktemp_dump('\n'.
                                                      join(
                                                        ceph_volume_lvm_list))

    def __del__(self):
        if self.udevadm_db:
            os.unlink(self.udevadm_db)

        if self.f_ceph_volume_lvm_list:
            os.unlink(self.f_ceph_volume_lvm_list)

    @property
    def bind_interfaces(self):
        """
        If ceph is using specific network interfaces, return them as a dict.
        """
        pub_net = self.ceph_config.get('public network')
        pub_addr = self.ceph_config.get('public addr')
        clus_net = self.ceph_config.get('cluster network')
        clus_addr = self.ceph_config.get('cluster addr')

        interfaces = {}
        if not any([pub_net, pub_addr, clus_net, clus_addr]):
            return interfaces

        nethelp = host_helpers.HostNetworkingHelper()

        if pub_net:
            iface = nethelp.get_interface_with_addr(pub_net).to_dict()
            interfaces.update(iface)
        elif pub_addr:
            iface = nethelp.get_interface_with_addr(pub_addr).to_dict()
            interfaces.update(iface)

        if clus_net:
            iface = nethelp.get_interface_with_addr(clus_net).to_dict()
            interfaces.update(iface)
        elif clus_addr:
            iface = nethelp.get_interface_with_addr(clus_addr).to_dict()
            interfaces.update(iface)

        return interfaces

    def _get_osds(self):
        if not self.f_ceph_volume_lvm_list:
            return

        s = FileSearcher()
        sd = SequenceSearchDef(start=SearchDef(r"^=+\s+osd\.(\d+)\s+=+.*"),
                               body=SearchDef([r"\s+osd\s+(fsid)\s+(\S+)\s*",
                                               r"\s+(devices)\s+([\S]+)\s*"]),
                               tag="ceph-lvm")
        s.add_search_term(sd, path=self.f_ceph_volume_lvm_list)
        osds = []
        for results in s.search().find_sequence_sections(sd).values():
            id = None
            fsid = None
            dev = None
            for result in results:
                if result.tag == sd.start_tag:
                    id = int(result.get(1))
                elif result.tag == sd.body_tag:
                    if result.get(1) == "fsid":
                        fsid = result.get(2)
                    elif result.get(1) == "devices":
                        dev = result.get(2)

            osds.append(CephOSD(id, fsid, dev))

        return osds

    @property
    def osds(self):
        """ Get key information about OSDs. """
        if self._osds:
            return self._osds

        self._osds = self._get_osds()
        return self._osds

    @property
    def bcache_info(self):
        """ If bcache devices exist fetch information and return as a dict. """
        if self._bcache_info:
            return self._bcache_info

        devs = []
        if not self.udevadm_db:
            return devs

        s = FileSearcher()
        sdef = SequenceSearchDef(start=SearchDef(r"^P: .+/(bcache\S+)"),
                                 body=SearchDef(r"^S: disk/by-uuid/(\S+)"),
                                 tag="bcacheinfo")
        s.add_search_term(sdef, self.udevadm_db)
        results = s.search()
        for section in results.find_sequence_sections(sdef).values():
            dev = {}
            for r in section:
                if r.tag == sdef.start_tag:
                    dev["name"] = r.get(1)
                else:
                    dev["by-uuid"] = r.get(1)

            devs.append(dev)

        self._bcache_info = devs
        return self._bcache_info

    def is_bcache_device(self, dev):
        """
        Returns True if the device either is or is based on a bcache device
        e.g. dmcrypt device using bcache dev.
        """
        if dev.startswith("bcache"):
            return True

        if dev.startswith("/dev/bcache"):
            return True

        ret = re.compile(r"/dev/mapper/crypt-(\S+)").search(dev)
        if ret:
            for dev in self.bcache_info:
                if dev.get("by-uuid") == ret.group(1):
                    return True

    def daemon_pkg_version(self, daemon):
        """Get version of local daemon based on package installed.

        This is prone to inaccuracy since the deamom many not have been
        restarted after package update.
        """
        pkginfo = checks.APTPackageChecksBase(CEPH_PKGS_CORE)
        return pkginfo.get_version(daemon)


class CephChecksBase(CephBase, plugintools.PluginPartBase,
                     checks.ServiceChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(service_exprs=CEPH_SERVICES_EXPRS, *args, **kwargs)

    @property
    def output(self):
        if self._output:
            return {"ceph": self._output}


class CephEventChecksBase(CephBase, checks.EventChecksBase):

    @property
    def output(self):
        if self._output:
            return {"ceph": self._output}


class BcacheBase(StorageBase):

    def get_sysfs_cachesets(self):
        cachesets = []
        path = os.path.join(constants.DATA_ROOT, "sys/fs/bcache/*")
        for entry in glob.glob(path):
            if os.path.exists(os.path.join(entry, "cache_available_percent")):
                cachesets.append({"path": entry,
                                  "uuid": os.path.basename(entry)})

        for cset in cachesets:
            path = os.path.join(cset['path'], "cache_available_percent")
            with open(path) as fd:
                value = fd.read().strip()
                cset["cache_available_percent"] = int(value)

            # dont include in final output
            del cset["path"]

        return cachesets


class BcacheChecksBase(BcacheBase, plugintools.PluginPartBase):

    @property
    def output(self):
        if self._output:
            return {"bcache": self._output}
