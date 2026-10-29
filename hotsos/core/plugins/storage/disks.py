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
        helper = LsblkHelper()
        return bool(helper.parsed_devices or
                    helper.unallocated_volume_groups)

    @cached_property
    def lsblk(self):
        """Return cached LsblkHelper instance."""
        return LsblkHelper()

    @cached_property
    def ceph_osd_devices(self):
        """
        Return set of kernel paths for local Ceph OSD devices, or None if
        Ceph is runnable on this host but OSD device discovery fails.
        """
        if not CephChecks.is_runnable():
            return set()
        try:
            ceph = CephChecks()
            osd_devices = set()
            lsblk_paths = self.lsblk.path_to_kernel_path
            for osd in ceph.local_osds:
                if not (osd.device or osd.block_device):
                    return None
                for dev in (osd.device, osd.block_device):
                    if not dev:
                        continue
                    osd_devices.add(dev)
                    kernel_path = lsblk_paths.get(dev)
                    if kernel_path:
                        osd_devices.add(kernel_path)
                    elif dev.startswith('/dev/disk/'):
                        return None
            return osd_devices
        except Exception:  # pylint: disable=broad-except
            return None

    @staticmethod
    def _add_device_names(target_set, dev):
        """Add KNAME, NAME, PATH and /dev/<name> for dev into target_set."""
        for key in ('KNAME', 'NAME', 'PATH'):
            val = dev.get(key)
            if val:
                target_set.add(val)
                if not val.startswith('/dev/'):
                    target_set.add(f"/dev/{val}")

    @cached_property
    def multipath_devices(self):
        """
        Return set of device names and paths that belong to multipath maps,
        including any descendant block devices (e.g. multipath partitions).
        """
        out = CLIHelper().multipath_ll()
        devs = set()
        for line in out or []:
            ret = re.search(r'\s(\S+)\s+\d+:\d+(?:\s|$)', line)
            if ret:
                dev_name = ret.group(1)
                devs.add(dev_name)
                if not dev_name.startswith('/dev/'):
                    devs.add(f"/dev/{dev_name}")

        for dev in self.lsblk.parsed_devices:
            if (dev.get('TYPE') == 'mpath' or
                    dev.get('FSTYPE') == 'mpath_member'):
                self._add_device_names(devs, dev)

        queue = list(devs)
        while queue:
            parent = queue.pop()
            for child in self.lsblk.children_by_parent.get(parent, []):
                before = len(devs)
                self._add_device_names(devs, child)
                if len(devs) > before:
                    kname = child.get('KNAME') or child.get('NAME')
                    if kname:
                        queue.append(kname)

        return devs

    def _get_matching_devices(self, predicate, size_fn=None):
        """Return sorted list of '<dev_path> (<size>)' matching predicate."""
        if not self.lsblk.parsed_devices or self.ceph_osd_devices is None:
            return []

        matched = []
        for dev in self.lsblk.parsed_devices:
            if not predicate(dev):
                continue

            kname = dev.get('KNAME') or dev.get('NAME')
            dev_path = dev.get('PATH') or f'/dev/{kname}'

            if dev_path in self.ceph_osd_devices:
                continue

            pkname = dev.get('PKNAME')
            if (kname in self.multipath_devices or
                    dev_path in self.multipath_devices or
                    (pkname and pkname in self.multipath_devices)):
                continue

            size = size_fn(dev) if size_fn else dev.get('SIZE')
            if size:
                desc = f"{dev_path} ({size})"
            else:
                desc = dev_path

            matched.append(desc)

        return sorted(matched)

    @cached_property
    def unused_disks(self):
        """
        Return list of entirely un-used disk paths and sizes formatted as
        strings, e.g. ['/dev/sdb (100G)'].
        """
        return self._get_matching_devices(self.lsblk.is_disk_entirely_unused)

    @cached_property
    def empty_partitions(self):
        """
        Return list of empty partition paths and sizes formatted as
        strings, e.g. ['/dev/sdb1 (50G)'].
        """
        return self._get_matching_devices(self.lsblk.is_partition_unused)

    @cached_property
    def unallocated_disks(self):
        """
        Return list of partitioned disks that have unallocated space formatted
        as strings, e.g. ['/dev/sdb (50G)'].
        """
        return self._get_matching_devices(
            lambda dev: self.lsblk.get_disk_unallocated_bytes(dev) > 0,
            size_fn=lambda dev: self.lsblk.format_size_bytes(
                self.lsblk.get_disk_unallocated_bytes(dev)
            ),
        )

    @cached_property
    def unallocated_volume_groups(self):
        """
        Return list of LVM volume groups that have significant free space
        formatted as strings, e.g. ['vg0 (50G)'].
        """
        return self.lsblk.unallocated_volume_groups
