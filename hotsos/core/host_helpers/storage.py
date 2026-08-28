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
    def path_to_kernel_path(self):
        """Return device and persistent paths mapped to kernel device paths."""
        paths = {}
        for line in CLIHelper().lsblk_O_P():
            fields = self._parse_pairs(line)
            path = fields.get('PATH')
            kname = fields.get('KNAME')
            if not path or not kname:
                continue

            kernel_path = f'/dev/{kname}'
            paths[path] = kernel_path
            if fields.get('ID-LINK'):
                paths[f"/dev/disk/by-id/{fields['ID-LINK']}"] = kernel_path

        return paths
