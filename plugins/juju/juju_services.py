#!/usr/bin/python3
import re
import os

from common import (
    constants,
    helpers,
    plugin_yaml,
)
from juju_common import (
    JUJU_LOG_PATH
)

JUJU_MACHINE_INFO = {"machines": {}}


def get_machine_info():
    ps_machines = set()
    log_machines = set()
    machines_running = set()
    machines_stopped = set()

    if not os.path.exists(JUJU_LOG_PATH):
        return

    for line in helpers.get_ps():
        if "machine-" in line:
            ret = re.compile(r".+machine-([0-9]+).*").match(line)
            if ret:
                ps_machines.add(ret[1])

    for f in os.listdir(JUJU_LOG_PATH):
        ret = re.compile(r"machine-([0-9]+)\.log.*").match(f)
        if ret:
            log_machines.add(ret[1])

    combined_machines = ps_machines.union(log_machines)
    for machine in combined_machines:
        agent_conf = os.path.join(constants.DATA_ROOT,
                                  "var/lib/juju/agents/machine-{}/agent.conf".
                                  format(machine))
        version = "unknown"
        if os.path.exists(agent_conf):
            for line in open(agent_conf).readlines():
                ret = re.compile(r"upgradedToVersion:\s+(.+)").match(line)
                if ret:
                    version = ret[1]

        if machine in ps_machines:
            machines_running.add("{} (version={})".format(machine, version))
        else:
            machines_stopped.add(machine)

    if machines_running:
        JUJU_MACHINE_INFO["machines"]["running"] = list(machines_running)

    if machines_stopped:
        JUJU_MACHINE_INFO["machines"]["stopped"] = list(machines_stopped)


if __name__ == "__main__":
    get_machine_info()
    if JUJU_MACHINE_INFO:
        plugin_yaml.save_part(JUJU_MACHINE_INFO, priority=0)
