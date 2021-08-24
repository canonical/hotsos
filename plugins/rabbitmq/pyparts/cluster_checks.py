from common import (
    issue_types,
    issues_utils,
)
from common.plugins.rabbitmq import RabbitMQEventChecksBase

YAML_PRIORITY = 1


class RabbitMQClusterChecks(RabbitMQEventChecksBase):

    def __init__(self):
        super().__init__(yaml_defs_group='cluster-checks')

    def process_results(self, results):
        """ See defs/events.yaml for definitions. """
        for events in self.event_definitions.values():
            for event in events:
                _results = results.find_by_tag(event)
                if event == "cluster-partitions" and _results:
                    msg = ("cluster either has or has had partitions - check "
                           "cluster_status")
                    issues_utils.add_issue(issue_types.RabbitMQWarning(msg))
