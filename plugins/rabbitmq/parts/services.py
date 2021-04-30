#!/usr/bin/python3
import os
from common import (
    checks,
    constants,
    plugin_yaml,
)

from common.searchtools import (
    SearchDef,
    SequenceSearchDef,
    FileSearcher,
)


import functools
import os.path
import re

RABBITMQ_INFO = {}
RMQ_SERVICES_EXPRS = [
    r"beam.smp",
    r"epmd",
    r"rabbitmq-server",
]
RMQ_PACKAGES = [
    r"rabbitmq-server",
]


class RabbitMQPackageChecks(checks.PackageChecksBase):

    def __call__(self):
        package_info = super().__call__()
        if package_info:
            RABBITMQ_INFO["dpkg"] = package_info


class RabbitMQServiceChecksBase(checks.ServiceChecksBase):
    pass


class RabbitMQServiceChecks(RabbitMQServiceChecksBase):

    def get_running_services_info(self):
        """Get string info for running services."""
        if self.services:
            RABBITMQ_INFO["services"] = self.get_service_info_str()

    def get_queues(self):
        """Get distribution of queues across cluster."""
        path = os.path.join(constants.DATA_ROOT,
                            "sos_commands/rabbitmq/rabbitmqctl_report")
        s = FileSearcher()
        sd = SequenceSearchDef(
            start=SearchDef(r"^Queues on ([^:]+):"),
            body=SearchDef(r"^<([^.\s]+)[.0-9]+>\s+(\S+)\s+.+"),
            end=SearchDef(r"^$"),
            tag="report-queues")
        s.add_search_term(sd, path)
        results = s.search()
        sections = results.find_sequence_sections(sd)
        resources = {"queues": {}}
        for id in sections:
            vhost = None
            queues = {}
            for r in sections[id]:
                if r.tag == sd.start_tag:
                    vhost = r.get(1)
                elif r.tag == sd.body_tag:
                    info = {"pid_name": r.get(1),
                            "queue": r.get(2)}
                    if info["pid_name"] not in queues:
                        queues[info["pid_name"]] = 1
                    else:
                        queues[info["pid_name"]] += 1
            total = functools.reduce(lambda x, y: x + y,
                                     list(queues.values()),
                                     0)
            if len(queues.keys()) > 0:
                resources["queues"][vhost] = {}
                for pid in queues:
                    if total > 0:
                        fraction = "{:.2f}%".format(queues[pid] / total * 100)
                    else:
                        fraction = "N/A"
                    resources["queues"][vhost][pid] = "{:d} ({})".format(
                        queues[pid], fraction)
            else:
                resources["queues"][vhost] = "no queues"

        for resource in resources:
            if not resources[resource]:
                continue

            if "resources" not in RABBITMQ_INFO:
                RABBITMQ_INFO["resources"] = {}

            if resource not in RABBITMQ_INFO["resources"]:
                RABBITMQ_INFO["resources"][resource] = {}

            for key in resources[resource]:
                value = resources[resource][key]
                RABBITMQ_INFO["resources"][resource][key] = value

    def __call__(self):
        super().__call__()
        self.get_running_services_info()
        self.get_queues()


def get_rabbitmq_service_checker():
    # Do this way to make it easier to write unit tests.
    return RabbitMQServiceChecks(RMQ_SERVICES_EXPRS, hint_range=(0, 3))


def get_rabbitmq_package_checker():
    # Do this way to make it easier to write unit tests.
    return RabbitMQPackageChecks(RMQ_PACKAGES)


if __name__ == "__main__":
    get_rabbitmq_service_checker()()
    get_rabbitmq_package_checker()()
    if RABBITMQ_INFO:
        plugin_yaml.save_part(RABBITMQ_INFO, priority=0)
