import os

from common import constants
from common.searchtools import (
    SearchDef,
    FileSearcher,
)
from common.plugins.openstack import OpenstackChecksBase

EXT_EVENT_META = {"network-vif-plugged": {"stages_keys":
                                          ["Preparing", "Received",
                                           "Processing"]},
                  "network-changed": {"stages_keys": ["Received",
                                                      "Refreshing"]}}
YAML_PRIORITY = 2


class NovaExternalEventChecks(OpenstackChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.data_source = os.path.join(constants.DATA_ROOT,
                                        "var/log/nova/nova-compute.log")

    @property
    def output(self):
        if self._output:
            return {"os-server-external-events": self._output}

    def get_state_dict(self, event_name):
        state = {}
        for key in EXT_EVENT_META[event_name]["stages_keys"]:
            state[key] = False

        return state

    def _get_events(self, event_name):
        ext_output = {}
        events = {}

        s = FileSearcher()

        # look for sequence starter
        if event_name == "network-vif-plugged":
            sd = SearchDef(r".+\[instance: (\S+)\].+Preparing to wait for "
                           r"external event ({})-(\S+)\s+".format(event_name))
            s.add_search_term(sd, self.data_source)
        elif event_name == "network-changed":
            expr = (r".+\[instance: (\S+)\].+Received event ({})-(\S+)\s+".
                    format(event_name))
            sd = SearchDef(expr)
            s.add_search_term(sd, self.data_source)

        master_results = s.search()

        # now start a fresh one
        s = FileSearcher()

        for file, results in master_results:
            for result in results:
                instance_id = result.get(1)
                event_id = result.get(3)
                events[event_id] = {"instance_id": instance_id,
                                    "data_source": file}

                for stage in EXT_EVENT_META[event_name]["stages_keys"]:
                    expr = (r".+\[instance: {}\]\s+{}\s.*\s?event\s+{}-{}.? "
                            ".+".
                            format(instance_id, stage, event_name, event_id))
                    tag = "{}_{}_{}".format(instance_id, event_id, stage)
                    sd = SearchDef(expr, tag, hint=event_name)
                    s.add_search_term(sd, self.data_source)

        results = s.search()
        for event_id in events:
            instance_id = events[event_id]["instance_id"]
            data_source = events[event_id]["data_source"]
            stages = self.get_state_dict(event_name)
            for stage in stages:
                tag = "{}_{}_{}".format(instance_id, event_id, stage)
                r = results.find_by_tag(tag, path=data_source)
                if r:
                    stages[stage] = True

            if all([stages[stage] for stage in stages]):
                result = "succeeded"
            else:
                result = "failed"

            if event_name not in ext_output:
                ext_output[event_name] = {}

            if result not in ext_output[event_name]:
                ext_output[event_name][result] = []

            info = {"port": event_id, "instance": instance_id}
            ext_output[event_name][result].append(info)

        if ext_output:
            for event in ext_output:
                if event not in self._output:
                    self._output[event] = {}
                for result in ext_output[event]:
                    s = ext_output[event][result]
                    self._output[event][result] = list(s)

    def __call__(self):
        # Supported events - https://docs.openstack.org/api-ref/compute/?expanded=run-events-detail#create-external-events-os-server-external-events  # noqa E501
        self._get_events("network-changed")
        self._get_events("network-vif-plugged")
