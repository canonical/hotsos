import os

from core import constants
from core.plugins.sosreport import SOSReportChecksBase
from core.issues import (
    issue_types,
    issue_utils,
)
from core.searchtools import (
    SearchDef,
    FileSearcher,
)

YAML_PRIORITY = 1


class SOSReportPluginChecks(SOSReportChecksBase):

    def check_plugin_timeouts(self):
        if not os.path.exists(os.path.join(constants.DATA_ROOT, 'sos_logs')):
            return

        searcher = FileSearcher()
        path = os.path.join(constants.DATA_ROOT, 'sos_logs/ui.log')
        searcher.add_search_term(SearchDef(r".* Plugin (\S+) timed out.*",
                                           tag="timeouts"), path=path)
        results = searcher.search()
        timeouts = []
        for r in results.find_by_tag("timeouts"):
            plugin = r.get(1)
            timeouts.append(plugin)
            msg = ("sosreport plugin '{}' has timed out and may have "
                   "incomplete data.".format(plugin))
            issue_utils.add_issue(issue_types.SOSReportWarning(msg))

        if timeouts:
            self._output["plugin-timeouts"] = timeouts

    def __call__(self):
        self.check_plugin_timeouts()
