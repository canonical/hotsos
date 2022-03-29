import os

from hotsos.core import checks
from hotsos.core.config import HotSOSConfig
from hotsos.core.plugintools import PluginPartBase
from hotsos.core.searchtools import (
    SearchDef,
    FileSearcher,
)

CORE_APT = ['sosreport']


class SOSReportChecksBase(PluginPartBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apt_check = checks.APTPackageChecksBase(core_pkgs=CORE_APT)

    @property
    def data_root_is_sosreport(self):
        path = os.path.join(HotSOSConfig.DATA_ROOT, 'sos_commands')
        if os.path.isdir(path):
            return True

        return False

    @property
    def version(self):
        if not self.data_root_is_sosreport:
            return

        path = os.path.join(HotSOSConfig.DATA_ROOT, 'version.txt')
        if not os.path.exists(path):
            return

        with open(path) as fd:
            for line in fd:
                if line.startswith('sosreport:'):
                    return line.partition(' ')[2].strip()

    @property
    def timed_out_plugins(self):
        timeouts = []
        if not os.path.exists(os.path.join(HotSOSConfig.DATA_ROOT,
                                           'sos_logs')):
            return timeouts

        searcher = FileSearcher()
        path = os.path.join(HotSOSConfig.DATA_ROOT, 'sos_logs/ui.log')
        searcher.add_search_term(SearchDef(r".* Plugin (\S+) timed out.*",
                                           tag="timeouts"), path=path)
        results = searcher.search()
        for r in results.find_by_tag("timeouts"):
            plugin = r.get(1)
            timeouts.append(plugin)

        return timeouts

    @property
    def plugin_runnable(self):
        return self.data_root_is_sosreport
