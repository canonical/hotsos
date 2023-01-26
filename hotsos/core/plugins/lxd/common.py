from hotsos.core.host_helpers import (
    APTPackageHelper,
    CLIHelper,
    SnapPackageHelper,
    SystemdHelper,
)
from hotsos.core.plugintools import PluginPartBase
from hotsos.core.utils import cached_property, mktemp_dump
from hotsos.core.search import (
    FileSearcher, SearchDef,
    SequenceSearchDef
)


CORE_APT = ['lxd', 'lxc']
CORE_SNAPS = [r"(?:snap\.)?{}".format(p) for p in CORE_APT]
SERVICE_EXPRS = [r"{}\S*".format(s) for s in CORE_SNAPS]


class LXD(object):

    @cached_property
    def buginfo_tmpfile(self):
        out = CLIHelper().lxd_buginfo()
        return mktemp_dump(''.join(out))

    @cached_property
    def instances(self):
        """ Return a list of instance names. """
        _instances = []
        s = FileSearcher()
        seq = SequenceSearchDef(start=SearchDef(r'^## Instances$'),
                                body=SearchDef(r'^\|\s+(\S+)\s+\|'),
                                end=SearchDef(r'##.*'),
                                tag='instances')
        s.add(seq, path=self.buginfo_tmpfile)
        results = s.run()
        for section in results.find_sequence_sections(seq).values():
            for r in section:
                if 'body' in r.tag:
                    if r.get(1) != 'NAME' and r.get(1) != '|':
                        _instances.append(r.get(1))

        return _instances


class LXDChecksBase(PluginPartBase):

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
