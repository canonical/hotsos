from hotsos.core.plugins.rabbitmq.common import (
    RabbitMQEventHandlerBase,
    RabbitMQEventCallbackBase,
)


class RabbitMQEventsCallback(RabbitMQEventCallbackBase):
    """ Callback for rabbitmq error events. """
    event_group = 'errors'
    event_names = ['connection-exception', 'delivery-ack-timeout',
                   'mnesia-error-event']

    def __call__(self, event):
        ret = self.categorise_events(event)
        return ret


class RabbitMQEventChecks(RabbitMQEventHandlerBase):
    """ Event handler for rabbitmq error events. """
    event_group = 'errors'
    summary_part_index = 1

    @property
    def summary_subkey(self):
        return 'rabbitmq-checks'
