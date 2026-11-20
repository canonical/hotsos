import re
from functools import cached_property

from hotsos.core.host_helpers import CLIHelper

# Map header e.g. 'mpatha (3600508b4000156d700012000000b0000) dm-0 HP,HSV200'
# or, without user friendly names, '3600508b4000156d7 dm-0 HP,HSV200'.
MAP_EXPR = re.compile(r'^(\S+)(?: \(\S+\))? dm-\d+ ')
# Path line e.g. '| `- 1:0:1:1 sdc 8:32  failed faulty running' with the
# device-mapper state, path checker state and online state. Columns are padded,
# the SCSI address is '#:#:#:#' when unknown and the checker state can be more
# than one word e.g. 'i/o pending'.
PATH_EXPR = re.compile(r'^[\s|`]*[|`]- (\S+)\s+(\S+)\s+(\d+:\d+)\s+'
                       r'(\S+)\s+(.+?)\s+(\S+)\s*$')


class MultipathMaps():
    """ Device Mapper Multipath maps reported by 'multipath -ll'. """

    @cached_property
    def _maps(self):
        """
        Return a dict of map name to list of path dicts parsed from
        'multipath -ll'. Output that is not a map listing, such as a failure
        to talk to device-mapper, yields an empty dict.
        """
        maps = {}
        name = None
        for line in CLIHelper().multipath_ll():
            ret = MAP_EXPR.match(line)
            if ret:
                name = ret.group(1)
                maps[name] = []
                continue

            ret = PATH_EXPR.match(line)
            if ret and name is not None:
                maps[name].append({'dev': ret.group(2),
                                   'major-minor': ret.group(3),
                                   'dm-state': ret.group(4),
                                   'checker-state': ret.group(5),
                                   'online-state': ret.group(6)})

        return maps

    @property
    def num_maps(self):
        """ Number of multipath maps reported. """
        return len(self._maps)

    @cached_property
    def failed_paths(self):
        """
        Return a dict of map name to list of paths that device-mapper marks
        failed or the path checker reports faulty, as
        '<major:minor> <dev> <dm-state> <checker-state> <online-state>'.
        """
        failed = {}
        for name, paths in self._maps.items():
            for path in paths:
                if (path['dm-state'] != 'failed' and
                        path['checker-state'] != 'faulty'):
                    continue

                failed.setdefault(name, []).append(
                    f"{path['major-minor']} {path['dev']} "
                    f"{path['dm-state']} {path['checker-state']} "
                    f"{path['online-state']}")

        return failed
