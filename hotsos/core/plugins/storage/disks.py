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
    def lsblk(self):
        """Return cached LsblkHelper instance."""
        return LsblkHelper()

    @cached_property
    def ceph_osd_devices(self):
        """Return set of kernel paths for local Ceph OSD devices."""
        try:
            if not CephChecks.is_runnable():
                return set()
            ceph = CephChecks()
            osd_devices = set()
            lsblk_paths = self.lsblk.path_to_kernel_path
            for osd in ceph.local_osds:
                for dev in (osd.device, osd.block_device):
                    if not dev:
                        continue
                    osd_devices.add(dev)
                    kernel_path = lsblk_paths.get(dev)
                    if kernel_path:
                        osd_devices.add(kernel_path)
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
            ret = re.search(r'\s(\S+)\s+\d+:\d+(?:\s|$)', line)
            if ret:
                dev_name = ret.group(1)
                devs.add(dev_name)
                if not dev_name.startswith('/dev/'):
                    devs.add(f"/dev/{dev_name}")
        return devs

    @cached_property
    def unused_disks(self):
        """
        Return list of entirely un-used disk paths and sizes formatted as
        strings, e.g. ['/dev/sdb (100G)'].
        """
        helper = self.lsblk
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
