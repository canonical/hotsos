from functools import cached_property

from hotsos.core.host_helpers import (
    APTPackageHelper,
    CLIHelperFile,
    SnapPackageHelper,
    SystemdHelper,
)
from hotsos.core.plugintools import PluginPartBase
from hotsos.core.search import (
    FileSearcher, SearchDef,
    SequenceSearchDef
)


CORE_APT = ['lxd', 'lxc']
CORE_SNAPS = [r"(?:snap\.)?{}".format(p) for p in CORE_APT]
SERVICE_EXPRS = [r"{}\S*".format(s) for s in CORE_SNAPS]


class LXD():

    @cached_property
    def instances(self):
        """ Return a list of instance names. """
        _instances = []
        s = FileSearcher()
        seq = SequenceSearchDef(start=SearchDef(r'^## Instances$'),
                                body=SearchDef(r'^\|\s+(\S+)\s+\|'),
                                end=SearchDef(r'##.*'),
                                tag='instances')
        with CLIHelperFile() as cli:
            s.add(seq, path=cli.lxd_buginfo())
            results = s.run()
            for section in results.find_sequence_sections(seq).values():
                for r in section:
                    if 'body' in r.tag:
                        if r.get(1) != 'NAME' and r.get(1) != '|':
                            _instances.append(r.get(1))

        return _instances


class LXDChecksBase(PluginPartBase):
    plugin_name = 'lxd'
    plugin_root_index = 11

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.snaps = SnapPackageHelper(core_snaps=CORE_SNAPS)
        self.apt = APTPackageHelper(core_pkgs=CORE_APT)
        self.systemd = SystemdHelper(service_exprs=SERVICE_EXPRS)

    @property
    def plugin_runnable(self):
        if self.apt.core or self.snaps.core:
            return True

        return False
