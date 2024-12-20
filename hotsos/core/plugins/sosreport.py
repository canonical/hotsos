import os
from dataclasses import dataclass, field
from functools import cached_property

from hotsos.core.config import HotSOSConfig
from hotsos.core.host_helpers import APTPackageHelper, InstallInfoBase
from hotsos.core.plugintools import PluginPartBase
from hotsos.core.search import (
    SearchDef,
    FileSearcher,
)

CORE_APT = ['sosreport']


@dataclass
class SOSInstallInfo(InstallInfoBase):
    """ SOSReport installation information. """
    apt: APTPackageHelper = field(default_factory=lambda:
                                  APTPackageHelper(core_pkgs=CORE_APT))


class SOSReportBase():
    """ SOSReport check helpers. """
    @property
    def data_root_is_sosreport(self):
        path = os.path.join(HotSOSConfig.data_root, 'sos_commands')
        if os.path.isdir(path):
            return True

        return False

    @cached_property
    def version(self):
        if not self.data_root_is_sosreport:
            return None

        path = os.path.join(HotSOSConfig.data_root, 'version.txt')
        if not os.path.exists(path):
            return None

        with open(path, encoding='utf-8') as fd:
            for line in fd:
                if not line.startswith('sosreport:'):
                    continue

                return line.partition(' ')[2].strip()

        return None

    @cached_property
    def timed_out_plugins(self):
        timeouts = []
        if not os.path.exists(os.path.join(HotSOSConfig.data_root,
                                           'sos_logs')):
            return timeouts

        searcher = FileSearcher()
        path = os.path.join(HotSOSConfig.data_root, 'sos_logs/ui.log')
        searcher.add(SearchDef(r".* Plugin (\S+) timed out.*", tag="timeouts"),
                     path=path)
        results = searcher.run()
        for r in results.find_by_tag("timeouts"):
            plugin = r.get(1)
            timeouts.append(plugin)

        return timeouts


class SOSReportChecks(SOSReportBase, PluginPartBase):
    """ Sosreport checks. """
    plugin_name = 'sosreport'
    plugin_root_index = 2

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        SOSInstallInfo().mixin(self)

    @classmethod
    def is_runnable(cls):
        """
        Determine whether or not this plugin can and should be run.

        @return: True or False
        """
        return SOSReportBase().data_root_is_sosreport
