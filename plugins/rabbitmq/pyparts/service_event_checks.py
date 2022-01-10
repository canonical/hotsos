from core.ycheck import CallbackHelper
from core.issues import (
    issue_types,
    issue_utils,
)
from core.searchtools import FileSearcher
from core.plugins.rabbitmq import RabbitMQEventChecksBase

YAML_PRIORITY = 1
EVENTCALLBACKS = CallbackHelper()


class RabbitMQEventChecks(RabbitMQEventChecksBase):

    def __init__(self):
        super().__init__(yaml_defs_group='cluster-checks',
                         searchobj=FileSearcher(),
                         callback_helper=EVENTCALLBACKS)

    @EVENTCALLBACKS.callback
    def cluster_partitions(self, event):  # pylint: disable=W0613
        msg = ("cluster either has or has had partitions - check "
               "cluster_status.")
        issue_utils.add_issue(issue_types.RabbitMQWarning(msg))

    @EVENTCALLBACKS.callback
    def no_sync(self, event):  # pylint: disable=W0613
        msg = ("Transient mirrored classic queues are not deleted when there "
               "are no replicas available for promotion. Please stop all "
               "rabbitmq-server units and restart the cluster. Note that "
               "a rolling restart will not work.")
        issue_utils.add_issue(issue_types.RabbitMQWarning(msg))

    @EVENTCALLBACKS.callback
    def discard(self, event):  # pylint: disable=W0613
        msg = ("Messages were discarded because transient mirrored classic "
               "queues are not syncronized. Please stop all rabbitmq-server "
               "units and restart the cluster. Note that a rolling restart "
               "will not work.")
        issue_utils.add_issue(issue_types.RabbitMQWarning(msg))
