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

    VIRTUAL_DEV_PREFIXES = (
        'loop', 'ram', 'zram', 'dm-', 'md', 'sr', 'fd', 'nbd', 'rbd', 'bcache'
    )
    RESERVED_PART_TYPES = frozenset({
        '21686148-6449-6e6f-744e-656564454649',  # BIOS boot
        'c12a7328-f81f-11d2-ba4b-00a0c93ec93b',  # EFI System Partition
        'e3c9e316-0b5c-4db8-817d-f92df00215ae',  # Microsoft Reserved (MSR)
        '9e1a2d38-c612-4316-aa26-8b49521e5a8b',  # PowerPC PReP boot
        '4fbd7e29-9d25-41b8-afd0-062c0ceff05d',  # Ceph OSD
        '45b0969e-9b03-4f30-b4c6-b4b80ceff106',  # Ceph journal
        'cafecafe-9b03-4f30-b4c6-b4b80ceff106',  # Ceph block
        '30cd0809-c2b2-499c-8879-2d6b78529876',  # Ceph block.db
        '5ce17fce-4087-4169-b7ff-056cc58473f9',  # Ceph block.wal
        '0x5', '0xf', '0x85', '0xef', '0x41',
    })

    @staticmethod
    def parse_size_bytes(size_str):
        """Convert human-readable disk size string to bytes."""
        if not size_str:
            return 0

        normalized = size_str.strip().upper().replace(',', '.')
        match = re.match(r'^([\d.]+)\s*([BKMGTPE]?)(?:IB)?$', normalized)
        if not match:
            return 0

        val, unit = match.groups()
        multipliers = {'B': 1, 'K': 1024, 'M': 1024**2, 'G': 1024**3,
                       'T': 1024**4, 'P': 1024**5, 'E': 1024**6}
        try:
            return int(float(val) * multipliers.get(unit, 1))
        except ValueError:
            return 0

    def is_partition_unused(self, dev):
        """
        Determine if a block device is an empty, un-used partition.

        A partition is considered un-used if:
        - TYPE == 'part' and not read-only (RO != '1')
        - Size > 10MB (ignores tiny BIOS boot / reserved partitions)
        - Not a known boot, extended, reserved, or Ceph partition type/label
        - Parent device is not virtual
        - No filesystem or signature (FSTYPE, UUID, FSUSED, FSSIZE are empty)
        - No mountpoints (MOUNTPOINT and MOUNTPOINTS are empty)
        - No child devices
        """
        if dev.get('TYPE') != 'part' or dev.get('RO') == '1':
            return False

        if self.parse_size_bytes(dev.get('SIZE')) <= 10 * 1024 * 1024:
            return False

        parttype = dev.get('PARTTYPE', '').lower()
        parttypename = dev.get('PARTTYPENAME', '').lower()
        partlabel = dev.get('PARTLABEL', '').lower()
        reserved_keywords = ('bios', 'efi', 'extended', 'reserved', 'prep',
                             'ceph', 'osd', 'journal')
        is_reserved = (
            parttype in self.RESERVED_PART_TYPES
            or any(kw in parttypename for kw in reserved_keywords)
            or any(kw in partlabel for kw in reserved_keywords)
        )
        if is_reserved:
            return False

        kname = dev.get('KNAME') or dev.get('NAME')
        if not kname:
            return False

        pkname = dev.get('PKNAME')
        is_virtual = (
            (pkname not in self.non_virtual_devices)
            if (self.non_virtual_devices is not None and pkname)
            else (pkname or kname).startswith(self.VIRTUAL_DEV_PREFIXES)
        )
        if is_virtual:
            return False

        name = dev.get('NAME')
        has_children = (kname in self.children_by_parent or
                        (name and name in self.children_by_parent))
        has_fs = bool(dev.get('FSTYPE') or dev.get('UUID') or
                      dev.get('FSUSED') or dev.get('FSSIZE'))
        has_mounts = bool(dev.get('MOUNTPOINT') or dev.get('MOUNTPOINTS'))

        return not (has_children or has_fs or has_mounts)
