#!/usr/bin/python3
import os

from common import (
    constants,
    issue_types,
    issues_utils,
    plugin_yaml,
)
from common.searchtools import (
    SearchDef,
    FileSearcher,
)

from rabbitmq_common import RabbitMQChecksBase

CLUSTER_INFO = {}


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
        super().__call__()
        self.check_log_errors()


def get_rabbitmq_cluster_checker():
    # Do this way to make it easier to write unit tests.
    return RabbitMQClusterChecks()


if __name__ == "__main__":
    get_rabbitmq_cluster_checker()()
    if CLUSTER_INFO:
        plugin_yaml.save_part(CLUSTER_INFO, priority=1)
