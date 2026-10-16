import re
import shlex
from functools import cached_property

from hotsos.core.host_helpers.cli import CLIHelper


class LsblkHelper():
    """Helper for parsing lsblk output."""

    @staticmethod
    def _parse_pairs(line):
        try:
            fields = shlex.split(line)
        except ValueError:
            return {}

        pairs = {}
        for field in fields:
            key, separator, value = field.partition('=')
            if separator:
                pairs[key] = value

        return pairs

    @cached_property
    def parsed_devices(self):
        """
        Return list of parsed device dicts from lsblk -O -P.
        Each entry contains the key-value pairs for one block device.
        """
        devices = []
        for line in CLIHelper().lsblk_O_P():
            fields = self._parse_pairs(line)
            if fields:
                devices.append(fields)

        return devices

    @cached_property
    def path_to_kernel_path(self):
        """Return device and persistent paths mapped to kernel device paths."""
        paths = {}
        for fields in self.parsed_devices:
            path = fields.get('PATH')
            kname = fields.get('KNAME')
            if not path or not kname:
                continue

            kernel_path = f'/dev/{kname}'
            paths[path] = kernel_path
            if fields.get('ID-LINK'):
                paths[f"/dev/disk/by-id/{fields['ID-LINK']}"] = kernel_path

        return paths

    @cached_property
    def children_by_parent(self):
        """Map parent kname or name to list of child device dicts."""
        children = {}
        for dev in self.parsed_devices:
            pkname = dev.get('PKNAME')
            if pkname:
                children.setdefault(pkname, []).append(dev)

        return children

    @cached_property
    def non_virtual_devices(self):
        """
        Return set of block device names from /sys/block that do not point
        to ../devices/virtual. Returns None if sysfs block listing is not
        available.
        """
        out = CLIHelper().ls_lanR_sys_block()
        if not out:
            return None

        virtual = '../devices/virtual'
        matches = (re.search(r'\s(\S+)\s->', line) for line in out
                   if virtual not in line)
        return {m.group(1) for m in matches if m}

    def is_disk_entirely_unused(self, dev):
        """
        Determine if a block device is an entirely un-used disk.

        A disk is considered entirely unused if:
        - TYPE == 'disk'
        - Not read-only (RO != '1')
        - Size is not empty and not '0' / '0B'
        - Not a virtual device (e.g. loop, dm-, ram, zram, bcache)
        - No partition table (PTTYPE and PTUUID are empty)
        - No partitions or child devices (not referenced as PKNAME by any dev)
        - No filesystem or signature (FSTYPE is empty)
        - No mountpoints (MOUNTPOINT and MOUNTPOINTS are empty)
        """
        if dev.get('TYPE') != 'disk' or dev.get('RO') == '1':
            return False

        size = dev.get('SIZE')
        if not size or size in ('0', '0B'):
            return False

        kname = dev.get('KNAME') or dev.get('NAME')
        if not kname:
            return False

        # Virtual device check
        if self.non_virtual_devices is not None:
            if kname not in self.non_virtual_devices:
                return False
        elif kname.startswith(('loop', 'ram', 'zram', 'dm-', 'md', 'sr',
                               'fd', 'nbd', 'rbd', 'bcache')):
            return False

        name = dev.get('NAME')
        has_children = (kname in self.children_by_parent or
                        (name and name in self.children_by_parent))
        has_pt = bool(dev.get('PTTYPE') or dev.get('PTUUID'))
        has_fs = bool(dev.get('FSTYPE'))
        has_mounts = bool(dev.get('MOUNTPOINT') or dev.get('MOUNTPOINTS'))

        return not (has_children or has_pt or has_fs or has_mounts)
