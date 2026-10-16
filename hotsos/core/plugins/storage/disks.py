import re
from functools import cached_property

from hotsos.core.host_helpers.cli import CLIHelper
from hotsos.core.host_helpers.storage import LsblkHelper
from hotsos.core.plugins.storage import StorageBase
from hotsos.core.plugins.storage.ceph.common import CephChecks


class DiskChecks(StorageBase):
    """Storage checks for un-used disks and unallocated space."""

    @classmethod
    def is_runnable(cls):
        """Determine whether disk checks should run."""
        return bool(LsblkHelper().parsed_devices)

    @cached_property
    def ceph_osd_devices(self):
        """Return set of kernel paths for local Ceph OSD devices."""
        try:
            if not CephChecks.is_runnable():
                return set()
            ceph = CephChecks()
            osd_devices = set()
            for osd in ceph.local_osds:
                if osd.dev:
                    osd_devices.add(osd.dev)
            return osd_devices
        except Exception:  # pylint: disable=broad-except
            return set()

    @cached_property
    def multipath_devices(self):
        """Return set of device names that are members of multipath maps."""
        out = CLIHelper().multipath_ll()
        if not out:
            return set()

        devs = set()
        for line in out:
            ret = re.search(r'\b(sd[a-z]+|nvme\d+n\d+|vd[a-z]+)\b', line)
            if ret:
                devs.add(ret.group(1))
                devs.add(f"/dev/{ret.group(1)}")
        return devs

    @cached_property
    def unused_disks(self):
        """
        Return list of entirely un-used disk paths and sizes formatted as
        strings, e.g. ['/dev/sdb (100G)'].
        """
        helper = LsblkHelper()
        unused = []
        for dev in helper.parsed_devices:
            if not helper.is_disk_entirely_unused(dev):
                continue

            kname = dev.get('KNAME') or dev.get('NAME')
            dev_path = dev.get('PATH') or f'/dev/{kname}'

            if dev_path in self.ceph_osd_devices:
                continue

            if (kname in self.multipath_devices or
                    dev_path in self.multipath_devices):
                continue

            size = dev.get('SIZE')
            if size:
                desc = f"{dev_path} ({size})"
            else:
                desc = dev_path

            unused.append(desc)

        return sorted(unused)
