import math
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
            id_link = fields.get('ID-LINK')
            if id_link:
                for link in id_link.replace('\\x0a', '\n').splitlines():
                    if link:
                        paths[f'/dev/disk/by-id/{link}'] = kernel_path

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
        matches = (re.search(r'\s(\S+)\s->\s*(\S+)', line) for line in out)
        return {
            m.group(1) for m in matches
            if m and virtual not in m.group(2)
        }

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
        elif kname.startswith(self.VIRTUAL_DEV_PREFIXES):
            return False

        name = dev.get('NAME')
        has_children = (kname in self.children_by_parent or
                        (name and name in self.children_by_parent))
        has_pt = bool(dev.get('PTTYPE') or dev.get('PTUUID'))
        has_fs = self._has_fs(dev)
        has_mounts = bool(dev.get('MOUNTPOINT') or dev.get('MOUNTPOINTS'))

        return not (has_children or has_pt or has_fs or has_mounts)

    @staticmethod
    def _has_fs(dev):
        """Return True if device has a filesystem signature or usage info."""
        return bool(dev.get('FSTYPE') or dev.get('UUID') or
                    dev.get('FSUSED') or dev.get('FSSIZE'))

    VIRTUAL_DEV_PREFIXES = (
        'loop', 'ram', 'zram', 'dm-', 'md', 'sr', 'fd', 'nbd', 'rbd', 'bcache'
    )
    UNALLOCATED_MIN_BYTES = 10 * 1024 * 1024
    UNALLOCATED_MIN_PERCENT = 5
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

    @cached_property
    def blockdev_sizes(self):
        """Return exact byte sizes keyed by blockdev device path."""
        sizes = {}
        for line in CLIHelper().blockdev_report():
            parts = line.rsplit(None, 2)
            if len(parts) < 3 or not parts[-1].startswith('/dev/'):
                continue

            if parts[-2].isdigit() and int(parts[-2]) > 0:
                sizes[parts[-1]] = int(parts[-2])

        return sizes

    @staticmethod
    def parse_size_bytes(size_str):
        """Convert human-readable disk size string to bytes."""
        if not size_str:
            return 0

        normalized = size_str.strip().lstrip('<>').upper().replace(',', '.')
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

    @staticmethod
    def parse_size_uncertainty_bytes(size_str):
        """
        Return half-ULP rounding uncertainty in bytes for a human-readable
        size string (e.g. '1.8T' -> 0.05 TiB). Exact byte sizes return 0.
        """
        if not size_str:
            return 0

        normalized = size_str.strip().lstrip('<>').upper().replace(',', '.')
        match = re.match(r'^([\d.]+)\s*([BKMGTPE]?)(?:IB)?$', normalized)
        if not match:
            return 0

        val, unit = match.groups()
        if unit in ('', 'B'):
            return 0

        multipliers = {'K': 1024, 'M': 1024**2, 'G': 1024**3,
                       'T': 1024**4, 'P': 1024**5, 'E': 1024**6}
        try:
            float(val)
        except ValueError:
            return 0

        decimals = len(val.partition('.')[2]) if '.' in val else 0
        ulp = 10 ** (-max(1, decimals))
        return math.ceil(0.5 * ulp * multipliers[unit])

    @staticmethod
    def format_size_bytes(size_bytes):
        """Convert byte count to a human-readable size string (e.g. '50G')."""
        if not size_bytes or size_bytes <= 0:
            return '0B'

        units = (('E', 1024**6), ('P', 1024**5), ('T', 1024**4),
                 ('G', 1024**3), ('M', 1024**2), ('K', 1024))
        for unit, factor in units:
            if size_bytes >= factor:
                val = size_bytes / factor
                formatted = f"{val:.1f}".rstrip('0').rstrip('.')
                return f"{formatted}{unit}"

        return f"{int(size_bytes)}B"

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
        has_fs = self._has_fs(dev)
        has_mounts = bool(dev.get('MOUNTPOINT') or dev.get('MOUNTPOINTS'))

        return not (has_children or has_fs or has_mounts)

    @staticmethod
    def _is_extended_container(part):
        """Return True if partition is an MBR extended container partition."""
        parttype = part.get('PARTTYPE', '').lower()
        parttypename = part.get('PARTTYPENAME', '').lower()
        return (parttype in ('0x5', '0xf', '0x85') or
                'extended' in parttypename)

    def _get_device_size_bytes(self, dev):
        """
        Return (size_bytes, uncertainty_bytes) for a block device, preferring
        exact byte sizes from blockdev --report when available.
        """
        path = dev.get('PATH') or f"/dev/{dev.get('KNAME') or dev.get('NAME')}"
        if path in self.blockdev_sizes:
            return self.blockdev_sizes[path], 0

        size_str = dev.get('SIZE')
        return (
            self.parse_size_bytes(size_str),
            self.parse_size_uncertainty_bytes(size_str),
        )

    def get_disk_unallocated_bytes(self, dev):
        """
        Return unallocated bytes on a partitioned disk, or 0 if not applicable
        or below threshold (>= 5% of disk size and >= 10MB).
        """
        kname = dev.get('KNAME') or dev.get('NAME')
        if dev.get('TYPE') != 'disk' or dev.get('RO') == '1' or not kname:
            return 0

        is_virtual = (
            (kname not in self.non_virtual_devices)
            if self.non_virtual_devices is not None
            else kname.startswith(self.VIRTUAL_DEV_PREFIXES)
        )
        if is_virtual:
            return 0

        name = dev.get('NAME')
        children = (self.children_by_parent.get(kname) or
                    (self.children_by_parent.get(name) if name else None) or
                    [])
        part_children = [
            c for c in children
            if c.get('TYPE') == 'part' and not self._is_extended_container(c)
        ]
        has_pt = bool(dev.get('PTTYPE') or dev.get('PTUUID'))
        has_fs_or_mounts = bool(
            self._has_fs(dev) or dev.get('MOUNTPOINT') or
            dev.get('MOUNTPOINTS')
        )
        has_non_part_children = any(
            c.get('TYPE') != 'part' for c in children
        )
        if (has_fs_or_mounts or has_non_part_children or
                (not part_children and not has_pt)):
            return 0

        size_info = [
            self._get_device_size_bytes(d) for d in [dev] + part_children
        ]
        disk_bytes, disk_uncertainty = size_info[0]
        if disk_bytes <= 0:
            return 0

        unallocated = disk_bytes - sum(s for s, _ in size_info[1:])
        min_unallocated = (
            unallocated - disk_uncertainty - sum(u for _, u in size_info[1:])
        )
        if (min_unallocated >= self.UNALLOCATED_MIN_BYTES and
                min_unallocated * 100 >=
                (disk_bytes + disk_uncertainty) *
                self.UNALLOCATED_MIN_PERCENT):
            return unallocated

        return 0

    @cached_property
    def unallocated_volume_groups(self):
        """
        Return list of LVM volume groups that have significant free space
        (>= 5% of VSize and >= 10MB) formatted as '<vg_name> (<free_size>)'.
        """
        vgs = []
        vsize_idx = None
        vfree_idx = None
        vg_idx = 0
        for line in CLIHelper().vgs():
            fields = line.split()
            if not fields:
                continue

            if fields[0] == 'VG' and 'VSize' in fields and 'VFree' in fields:
                vg_idx = 0
                vsize_idx = fields.index('VSize')
                vfree_idx = fields.index('VFree')
                continue

            if vsize_idx is None or len(fields) <= max(vsize_idx, vfree_idx):
                continue

            vg_name = fields[vg_idx]
            vsize = self.parse_size_bytes(fields[vsize_idx])
            vfree = self.parse_size_bytes(fields[vfree_idx])
            if vsize <= 0 or vfree < self.UNALLOCATED_MIN_BYTES:
                continue

            if vfree * 100 >= vsize * self.UNALLOCATED_MIN_PERCENT:
                free_str = self.format_size_bytes(vfree)
                vgs.append(f"{vg_name} ({free_str})")

        return sorted(vgs)
