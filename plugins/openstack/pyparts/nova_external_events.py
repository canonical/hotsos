from core.checks import CallbackHelper
from core.searchtools import (
    SearchDef,
    FileSearcher,
)
from core.plugins.openstack import OpenstackEventChecksBase

EXT_EVENT_META = {'network-vif-plugged': {'stages_keys':
                                          ['Preparing', 'Received',
                                           'Processing']},
                  'network-changed': {'stages_keys': ['Received',
                                                      'Refreshing']}}
YAML_PRIORITY = 2
EVENTCALLBACKS = CallbackHelper()


class NovaExternalEventChecks(OpenstackEventChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, callback_helper=EVENTCALLBACKS,
                         yaml_defs_group='nova-external-events',
                         event_results_output_key='os-server-external-events',
                         **kwargs,)

    def get_state_dict(self, event_name):
        state = {}
        for key in EXT_EVENT_META[event_name]['stages_keys']:
            state[key] = False

        return state

    def _get_events(self, event_name, master_results):
        ext_output = {}
        events = {}
        events_found = {}

        s = FileSearcher()
        for result in master_results:
            instance_id = result.get(1)
            event_id = result.get(3)
            events[event_id] = {'instance_id': instance_id,
                                'data_source': result.source}

            for stage in EXT_EVENT_META[event_name]['stages_keys']:
                expr = (r".+\[instance: {}\]\s+{}\s.*\s?event\s+{}-{}.? "
                        ".+".
                        format(instance_id, stage, event_name, event_id))
                tag = "{}_{}_{}".format(instance_id, event_id, stage)
                sd = SearchDef(expr, tag, hint=event_name)
                s.add_search_term(sd, result.source)

        results = s.search()
        for event_id in events:
            instance_id = events[event_id]['instance_id']
            data_source = events[event_id]['data_source']
            stages = self.get_state_dict(event_name)
            for stage in stages:
                tag = "{}_{}_{}".format(instance_id, event_id, stage)
                r = results.find_by_tag(tag, path=data_source)
                if r:
                    stages[stage] = True

            if all([stages[stage] for stage in stages]):
                result = 'succeeded'
            else:
                result = 'failed'

            if result not in ext_output:
                ext_output[result] = []

            info = {'port': event_id, 'instance': instance_id}
            ext_output[result].append(info)

        if ext_output:
            for result in ext_output:
                events_found[result] = list(ext_output[result])

        return events_found

    @EVENTCALLBACKS.callback
    def network_changed(self, event):
        return self._get_events('network-changed', event['results'])

    @EVENTCALLBACKS.callback
    def network_vif_plugged(self, event):
        return self._get_events('network-vif-plugged', event['results'])
