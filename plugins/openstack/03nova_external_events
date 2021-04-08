#!/usr/bin/python3
import os

from common import (
    constants,
    searchtools,
    plugin_yaml,
)

EXT_EVENT_META = {"network-vif-plugged": {"stages_keys":
                                          ["Preparing", "Received",
                                           "Processing"]},
                  "network-changed": {"stages_keys": ["Received",
                                                      "Refreshing"]}}
EXT_EVENT_INFO = {}


def get_state_dict(event_name):
    state = {}
    for key in EXT_EVENT_META[event_name]["stages_keys"]:
        state[key] = False

    return state


def get_events(event_name, data_source):
    ext_event_info = {}
    events = {}

    s = searchtools.FileSearcher()

    # look for sequence starter
    if event_name == "network-vif-plugged":
        key = (r".+\[instance: (\S+)\].+Preparing to wait for external "
               r"event ({})-(\S+)\s+".format(event_name))
        s.add_search_term(key, [1, 2, 3], data_source)
    elif event_name == "network-changed":
        key = (r".+\[instance: (\S+)\].+Received "
               r"event ({})-(\S+)\s+".format(event_name))
        s.add_search_term(key, [1, 2, 3], data_source)

    master_results = s.search()

    # now start a fresh one
    s = searchtools.FileSearcher()

    for file, results in master_results:
        for result in results:
            instance_id = result.get(1)
            event_id = result.get(3)
            events[event_id] = {"instance_id": instance_id,
                                "data_source": file}

            for stage in EXT_EVENT_META[event_name]["stages_keys"]:
                key = (r".+\[instance: {}\]\s+{}\s.*\s?event\s+{}-{}.? .+".
                       format(instance_id, stage, event_name, event_id))
                tag = "{}_{}_{}".format(instance_id, event_id, stage)
                s.add_search_term(key, [0], data_source, tag=tag)

    results = s.search()
    for event_id in events:
        instance_id = events[event_id]["instance_id"]
        data_source = events[event_id]["data_source"]
        stages = get_state_dict(event_name)
        for stage in stages:
            tag = "{}_{}_{}".format(instance_id, event_id, stage)
            r = results.find_by_tag(tag, path=data_source)
            if r:
                stages[stage] = True

        if all([stages[stage] for stage in stages]):
            result = "succeeded"
        else:
            result = "failed"

        if event_name not in ext_event_info:
            ext_event_info[event_name] = {}

        if result not in ext_event_info[event_name]:
            ext_event_info[event_name][result] = []

        ext_event_info[event_name][result].append({"port": event_id,
                                                   "instance": instance_id})

    if ext_event_info:
        for event in ext_event_info:
            if event not in EXT_EVENT_INFO:
                EXT_EVENT_INFO[event] = {}
            for result in ext_event_info[event]:
                s = ext_event_info[event][result]
                EXT_EVENT_INFO[event][result] = list(s)


if __name__ == "__main__":
    # Supported events - https://docs.openstack.org/api-ref/compute/?expanded=run-events-detail#create-external-events-os-server-external-events  # noqa E501
    data_source = os.path.join(constants.DATA_ROOT,
                               "var/log/nova/nova-compute.log")

    get_events("network-changed", data_source)
    get_events("network-vif-plugged", data_source)
    if EXT_EVENT_INFO:
        EXT_EVENT_INFO = {"os-server-external-events": EXT_EVENT_INFO}
        plugin_yaml.dump(EXT_EVENT_INFO)
