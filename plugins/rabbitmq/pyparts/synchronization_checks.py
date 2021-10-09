from core.checks import CallbackHelper
from core.issues import (
    issue_types,
    issue_utils,
)
from core.plugins.rabbitmq import RabbitMQEventChecksBase

YAML_PRIORITY = 1
EVENTCALLBACKS = CallbackHelper()


class RabbitMQSynchronizationChecks(RabbitMQEventChecksBase):

    def __init__(self):
        super().__init__(yaml_defs_group='synced-queues',
                         callback_helper=EVENTCALLBACKS)

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
