import os

from common import (
    constants,
    issue_types,
    issues_utils,
)
from common.searchtools import (
    SearchDef,
    FileSearcher,
)
from common.plugins.rabbitmq import RabbitMQChecksBase

YAML_PRIORITY = 1


class RabbitMQClusterChecks(RabbitMQChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.searcher = FileSearcher()

    def check_log_errors(self):
        path = os.path.join(constants.DATA_ROOT,
                            'var/log/rabbitmq/rabbit@*.log')
        if constants.USE_ALL_LOGS:
            path = f"{path}*"

        self.searcher.add_search_term(SearchDef(
                                        r".+ \S+_partitioned_network",
                                        tag="partitions"),
                                      path=path)
        results = self.searcher.search()
        if results.find_by_tag("partitions"):
            msg = ("cluster either has or has had partitions - check "
                   "cluster_status")
            issues_utils.add_issue(issue_types.RabbitMQWarning(msg))

    def __call__(self):
        self.check_log_errors()
