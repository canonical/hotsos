from hotsos.core.plugins.openstack.common import (
    OpenstackEventCallbackBase,
    OpenstackEventHandlerBase,
)
from hotsos.core.plugintools import (
    summary_entry,
    get_min_available_entry_index,
)

EXT_EVENT_META = {'network-vif-plugged': {'stages_keys':
                                          ['Preparing', 'Received',
                                           'Processing']},
                  'network-changed': {'stages_keys': ['Received',
                                                      'Refreshing']}}


class ExternalEventsCallback(OpenstackEventCallbackBase):
    """ Implements Openstack Nova external events callback.

    @return: dictionary with count of succeeded and list of failed (incomplete)
             external events grouped by event type.
    """
    event_group = 'nova.external-events'
    event_names = ['network-changed', 'network-vif-plugged']

    def __call__(self, event):
        data = {}
        for result in event.results:
            instance_id = result.get(1)
            stage = result.get(2)
            event_id = result.get(3)
            # If the same event/port is used for a new instance we reset.
            if (event_id in data and
                    data[event_id]['instance_id'] == instance_id):
                stages = data[event_id]['stages']
                stages.add(stage)
                if (not
                        stages.difference(EXT_EVENT_META[event.name]
                                          ['stages_keys'])):
                    data[event_id]['complete'] = True
            else:
                data[event_id] = {'complete': False,
                                  'stages': {stage},
                                  'instance_id': instance_id}

        out = {'succeeded': 0,
               'failed': []}
        for e, info in data.items():
            if info['complete']:
                out['succeeded'] += 1
            else:
                x = {'port': e, 'instance': info['instance_id']}
                out['failed'].append(x)

        if not out['succeeded']:
            del out['succeeded']

        if not out['failed']:
            del out['failed']

        return out


class NovaExternalEventChecks(OpenstackEventHandlerBase):
    """ Implements Openstack Nova external events handler. """
    event_group = 'nova.external-events'
    summary_part_index = 1

    @summary_entry('os-server-external-events',
                   get_min_available_entry_index() + 4)
    def summary_os_server_external_events(self):
        return self.run()
