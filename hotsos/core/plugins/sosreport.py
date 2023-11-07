import os
from functools import cached_property

from hotsos.core.config import HotSOSConfig
from hotsos.core.host_helpers import APTPackageHelper
from hotsos.core.plugintools import PluginPartBase
from hotsos.core.search import (
    SearchDef,
    FileSearcher,
)

CORE_APT = ['sosreport']


class SOSReportChecksBase(PluginPartBase):
    plugin_name = 'sosreport'
    plugin_root_index = 2

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apt = APTPackageHelper(core_pkgs=CORE_APT)

    @cached_property
    def data_root_is_sosreport(self):
        path = os.path.join(HotSOSConfig.data_root, 'sos_commands')
        if os.path.isdir(path):
            return True

        return False

    @cached_property
    def version(self):
        if not self.data_root_is_sosreport:
            return

        path = os.path.join(HotSOSConfig.data_root, 'version.txt')
        if not os.path.exists(path):
            return

        with open(path) as fd:
            for line in fd:
                if line.startswith('sosreport:'):
                    return line.partition(' ')[2].strip()

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

    @property
    def plugin_runnable(self):
        return self.data_root_is_sosreport
