#!/usr/bin/python3
import os

import functools

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.report_path = "sos_commands/rabbitmq/rabbitmqctl_report"
        self.report_path = os.path.join(constants.DATA_ROOT, self.report_path)
        self.searcher = FileSearcher()
        self.resources = {}

    def get_running_services_info(self):
        """Get string info for running services."""
        if self.services:
            RABBITMQ_INFO["services"] = self.get_service_info_str()

    def register_report_searches(self):
        """Register all sequence search definitions that we will execute
        against rabbitmqctl report.
        """
        self._sequences = {
            "queues":
                SequenceSearchDef(
                    start=SearchDef(r"^Queues on ([^:]+):"),
                    body=SearchDef(r"^<([^.\s]+)[.0-9]+>\s+(\S+)\s+.+"),
                    end=SearchDef(r"^$"),
                    tag="queues"),
            "connections":
                SequenceSearchDef(
                    start=SearchDef(r"^Connections:$"),
                    body=SearchDef(r"^<(rabbit[^>.]*)(?:[.][0-9]+)+>.*$"),
                    end=SearchDef(r"^$"),
                    tag="connections"),
            "memory":
                SequenceSearchDef(
                    start=SearchDef(r"^Status of node '([^']*)'$"),
                    body=SearchDef(r"^\s+\[{total,([0-9]+)}.+"),
                    end=SearchDef(r"^$"),
                    tag="memory")
            }
        for sd in self._sequences.values():
            self.searcher.add_search_term(sd, self.report_path)

    def get_queues(self):
        """Get distribution of queues across cluster."""
        sd = self._sequences["queues"]
        vhost_queues = {}
        for results in self.results.find_sequence_sections(sd).values():
            vhost = None
            queues = {}
            for result in results:
                if result.tag == sd.start_tag:
                    vhost = result.get(1)
                elif result.tag == sd.body_tag:
                    info = {"pid_name": result.get(1),
                            "queue": result.get(2)}
                    if info["pid_name"] not in queues:
                        queues[info["pid_name"]] = 1
                    else:
                        queues[info["pid_name"]] += 1

            if len(queues.keys()) == 0:
                vhost_queues[vhost] = "no queues"
                continue

            total = functools.reduce(lambda x, y: x + y,
                                     list(queues.values()), 0)
            vhost_queues[vhost] = {}
            for pid in queues:
                if total > 0:
                    fraction = "{:.2f}%".format(queues[pid] / total * 100)
                else:
                    fraction = "n/a"

                vhost_queues[vhost][pid] = "{:d} ({})".format(
                    queues[pid], fraction)

        if vhost_queues:
            self.resources["queues"] = vhost_queues

    def get_queue_connection_distribution(self):
        """Get distribution of connections across cluster."""
        sd = self._sequences["connections"]
        queue_connections = {}
        for results in self.results.find_sequence_sections(sd).values():
            for result in results:
                if result.tag == sd.body_tag:
                    queue_name = result.get(1)
                    if queue_name not in queue_connections:
                        queue_connections[queue_name] = 1
                    else:
                        queue_connections[queue_name] += 1

        if queue_connections:
            self.resources["queue-connections"] = queue_connections

    def get_memory_used(self):
        """Get the memory used per broker."""
        sd = self._sequences["memory"]
        memory_used = {}
        for results in self.results.find_sequence_sections(sd).values():
            for result in results:
                if result.tag == sd.start_tag:
                    node_name = result.get(1)
                elif result.tag == sd.body_tag:
                    total = result.get(1)
                    mib_used = int(total) / 1024. / 1024.
                    memory_used[node_name] = "{:.3f}".format(mib_used)

        if memory_used:
            self.resources["memory-used-mib"] = memory_used

    def run_report_searches(self):
        self.register_report_searches()
        self.results = self.searcher.search()
        self.get_queues()
        self.get_queue_connection_distribution()
        self.get_memory_used()
        for resource in self.resources:
            if not self.resources[resource]:
                continue

            if "resources" not in RABBITMQ_INFO:
                RABBITMQ_INFO["resources"] = {}

            if resource not in RABBITMQ_INFO["resources"]:
                RABBITMQ_INFO["resources"][resource] = {}

            for key in self.resources[resource]:
                value = self.resources[resource][key]
                RABBITMQ_INFO["resources"][resource][key] = value

    def __call__(self):
        super().__call__()
        self.get_running_services_info()
        self.run_report_searches()


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
