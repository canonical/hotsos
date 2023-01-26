from hotsos.core.search import (
    FileSearcher,
    SearchDef,
    SearchConstraintSearchSince,
)
from hotsos.core.ycheck.events import CallbackHelper
from hotsos.core.plugins.openstack.common import OpenstackEventChecksBase
from hotsos.core.plugins.openstack.openstack import OPENSTACK_LOGS_TS_EXPR

EXT_EVENT_META = {'network-vif-plugged': {'stages_keys':
                                          ['Preparing', 'Received',
                                           'Processing']},
                  'network-changed': {'stages_keys': ['Received',
                                                      'Refreshing']}}
EVENTCALLBACKS = CallbackHelper()


class NovaExternalEventChecks(OpenstackEventChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(EVENTCALLBACKS, *args,
                         yaml_defs_group='nova.external-events',
                         searchobj=FileSearcher(),
                         **kwargs,)

    def get_state_dict(self, event_name):
        state = {}
        for key in EXT_EVENT_META[event_name]['stages_keys']:
            state[key] = False

        return state

    @EVENTCALLBACKS.callback(event_group='nova.external-events',
                             event_names=['network-changed',
                                          'network-vif-plugged'])
    def process_events(self, event):
        ext_output = {}
        events = {}
        events_found = {}

        c = SearchConstraintSearchSince(exprs=[OPENSTACK_LOGS_TS_EXPR])
        s = FileSearcher(constraint=c)
        for result in event.results:
            instance_id = result.get(1)
            event_id = result.get(3)
            result_path = self.searchobj.resolve_source_id(result.source_id)
            events[event_id] = {'instance_id': instance_id,
                                'data_source': result_path}

            for stage in EXT_EVENT_META[event.name]['stages_keys']:
                expr = (r".+\[instance: {}\]\s+{}\s.*\s?event\s+{}-{}.? "
                        ".+".
                        format(instance_id, stage, event.name, event_id))
                tag = "{}_{}_{}".format(instance_id, event_id, stage)
                sd = SearchDef(expr, tag, hint=event.name,
                               store_result_contents=False)
                s.add(sd, result_path)

        results = s.run()
        for event_id in events:
            instance_id = events[event_id]['instance_id']
            data_source = events[event_id]['data_source']
            stages = self.get_state_dict(event.name)
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

    def __summary_os_server_external_events(self):
        return self.run_checks()
