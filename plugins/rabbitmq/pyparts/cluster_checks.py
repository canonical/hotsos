from common import (
    checks,
    issue_types,
    issues_utils,
)
from common.plugins.rabbitmq import RabbitMQChecksBase
from common.searchtools import FileSearcher

YAML_PRIORITY = 1


class RabbitMQClusterChecks(RabbitMQChecksBase, checks.EventChecksBase):

    def __init__(self, *args, **kwargs):
        s = FileSearcher()
        super().__init__(*args, searchobj=s, yaml_defs_label='cluster-checks',
                         **kwargs)

    def process_results(self, results):
        """ See defs/events.yaml for definitions. """
        for defs in self.event_definitions.values():
            for label in defs:
                _results = results.find_by_tag(label)
                if label == "cluster-partitions" and _results:
                    msg = ("cluster either has or has had partitions - check "
                           "cluster_status")
                    issues_utils.add_issue(issue_types.RabbitMQWarning(msg))

    def __call__(self):
        self.register_search_terms()
        self.process_results(self.searchobj.search())
