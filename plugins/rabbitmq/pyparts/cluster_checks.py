from core.checks import CallbackHelper
from core.issues import (
    issue_types,
    issue_utils,
)
from core.plugins.rabbitmq import RabbitMQEventChecksBase

YAML_PRIORITY = 1
EVENTCALLBACKS = CallbackHelper()


class RabbitMQClusterChecks(RabbitMQEventChecksBase):

    def __init__(self):
        super().__init__(yaml_defs_group='cluster-checks',
                         callback_helper=EVENTCALLBACKS)

    @EVENTCALLBACKS.callback
    def cluster_partitions(self, event):  # pylint: disable=W0613
        msg = ("cluster either has or has had partitions - check "
               "cluster_status")
        issue_utils.add_issue(issue_types.RabbitMQWarning(msg))
