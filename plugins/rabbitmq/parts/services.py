#!/usr/bin/python3
import os

import functools

from common import (
    checks,
    cli_helpers,
    issue_types,
    issues_utils,
    plugin_yaml,
)
from common.searchtools import (
    SearchDef,
    SequenceSearchDef,
    FileSearcher,
)
from common.utils import mktemp_dump

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
        p = self.packages
        if p:
            RABBITMQ_INFO["dpkg"] = p


class RabbitMQServiceChecksBase(checks.ServiceChecksBase):
    pass


class RabbitMQServiceChecks(RabbitMQServiceChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        out = cli_helpers.get_rabbitmqctl_report()
        # save to file so we can search it later
        self.f_report = mktemp_dump(''.join(out))
        self.searcher = FileSearcher()
        self.resources = {}

    def __del__(self):
        if os.path.exists(self.f_report):
            os.unlink(self.f_report)

    def get_running_services_info(self):
        """Get string info for running services."""
        if self.services:
            RABBITMQ_INFO["services"] = self.get_service_info_str()

    def get_queues(self):
        """Get distribution of queues across cluster."""
        sd = self._sequences["queues"]["searchdef"]
        vhost_queues = {}
        raise_issues = []
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

            vhost_queues[vhost] = {}
            if len(queues.keys()) == 0:
                continue

            total = functools.reduce(lambda x, y: x + y,
                                     list(queues.values()), 0)
            vhost_queues[vhost] = {}
            for pid in queues:
                if total > 0:
                    fraction = queues[pid] / total
                    fraction_string = "{:.2f}%".format(fraction * 100)
                    if fraction > 2 / 3:
                        raise_issues.append(
                            "{} holds more than 2/3 of queues".format(pid))
                else:
                    fraction_string = "N/A"

                vhost_queues[vhost][pid] = "{:d} ({})".format(
                    queues[pid], fraction_string)

        for issue in raise_issues:
            issues_utils.add_issue(issue_types.RabbitMQWarning(issue))

        if vhost_queues:
            # list all vhosts but only show their queues if not []
            self.resources["vhosts"] = sorted(list(vhost_queues.keys()))
            self.resources["vhost-queue-distributions"] = \
                {k: v for k, v in vhost_queues.items() if v}

    def get_queue_connection_distribution(self):
        """Get distribution of connections across cluster."""
        sd = self._sequences["connections"]["searchdef"]
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
        sd = self._sequences["memory"]["searchdef"]
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

    def register_report_searches(self):
        """Register all sequence search definitions that we will execute
        against rabbitmqctl report.
        """
        self._sequences = {
            "queues": {
                "searchdef":
                    SequenceSearchDef(
                        start=SearchDef(r"^Queues on ([^:]+):"),
                        body=SearchDef(r"^<([^.\s]+)[.0-9]+>\s+(\S+)\s+.+"),
                        end=SearchDef(r"^$"),
                        tag="queues"),
                "callbacks":
                    [self.get_queues]
                },
            "connections": {
                "searchdef":
                    SequenceSearchDef(
                        start=SearchDef(r"^Connections:$"),
                        body=SearchDef(r"^<(rabbit[^>.]*)(?:[.][0-9]+)+>.*$"),
                        end=SearchDef(r"^$"),
                        tag="connections"),
                "callbacks":
                    [self.get_queue_connection_distribution]
                },
            "memory": {
                "searchdef":
                    SequenceSearchDef(
                        start=SearchDef(r"^Status of node '([^']*)'$"),
                        body=SearchDef(r"^\s+\[{total,([0-9]+)}.+"),
                        end=SearchDef(r"^$"),
                        tag="memory"),
                "callbacks":
                    [self.get_memory_used]
                }
            }
        for s in self._sequences.values():
            self.searcher.add_search_term(s["searchdef"], self.f_report)

    def run_report_callbacks(self):
        for s in self._sequences.values():
            for f in s["callbacks"]:
                f()

    def run_report_searches(self):
        self.register_report_searches()
        self.results = self.searcher.search()
        self.run_report_callbacks()
        if not self.resources:
            return

        RABBITMQ_INFO["resources"] = self.resources

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
