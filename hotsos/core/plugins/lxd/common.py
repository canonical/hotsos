from dataclasses import dataclass, field
from functools import cached_property

from hotsos.core.host_helpers import (
    APTPackageHelper,
    CLIHelperFile,
    InstallInfoBase,
    SnapPackageHelper,
    SystemdHelper,
)
from hotsos.core.plugintools import PluginPartBase
from hotsos.core.search import (
    FileSearcher, SearchDef,
    SequenceSearchDef
)


CORE_APT = ['lxd', 'lxc']
CORE_SNAPS = [rf"(?:snap\.)?{p}" for p in CORE_APT]
SERVICE_EXPRS = [rf"{s}\S*" for s in CORE_SNAPS]


class LXD():
    """ LXD interface. """
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


@dataclass
class LXDInstallInfo(InstallInfoBase):
    """ LXD installation information. """
    apt: APTPackageHelper = field(default_factory=lambda:
                                  APTPackageHelper(core_pkgs=CORE_APT))
    snaps: SnapPackageHelper = field(default_factory=lambda:
                                     SnapPackageHelper(core_snaps=CORE_SNAPS))
    systemd: SystemdHelper = field(default_factory=lambda:
                                   SystemdHelper(service_exprs=SERVICE_EXPRS))


class LXDChecks(PluginPartBase):
    """ LXD Checks. """
    plugin_name = 'lxd'
    plugin_root_index = 11

    def __init__(self, *args, **kwargs):
        super().__init__()
        LXDInstallInfo().mixin(self)

    @classmethod
    def is_runnable(cls):
        """
        Determine whether or not this plugin can and should be run.

        @return: True or False
        """
        lxd_pkgs = LXDInstallInfo()
        if lxd_pkgs.apt.core or lxd_pkgs.snaps.core:
            return True

        return False
