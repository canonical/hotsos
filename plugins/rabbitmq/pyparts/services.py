import os

from core import (
    checks,
    plugintools,
)
from core.issues import (
    issue_types,
    issue_utils,
)
from core.cli_helpers import CLIHelper
from core.searchtools import (
    SearchDef,
    SequenceSearchDef,
    FileSearcher,
)
from core.utils import mktemp_dump, sorted_dict
from core.plugins.rabbitmq import (
    RabbitMQChecksBase,
    RMQ_PACKAGES,
)

YAML_PRIORITY = 0


class RabbitMQPackageChecks(plugintools.PluginPartBase,
                            checks.APTPackageChecksBase):

    def __init__(self):
        super().__init__(core_pkgs=RMQ_PACKAGES)

    def __call__(self):
        # require at least one core package to be installed to include
        # this in the report.
        if self.core:
            self._output["dpkg"] = self.all


class RabbitMQServiceChecks(RabbitMQChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        out = CLIHelper().rabbitmqctl_report()
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
            self._output["services"] = self.get_service_info_str()

    def register_report_searches(self):
        """Register all sequence search definitions that we will execute
        against rabbitmqctl report.

        NOTE: the rabbitmqctl report output differs between versions 3.6.x and
              3.8.x and we try to account for either by providing optional
              regex expressions to match either.
        """
        self._sequences = {
            "queues": {
                "searchdef":
                    SequenceSearchDef(
                        start=SearchDef([r"^Queues on ([^:]+):",
                                         (r"^Listing queues for vhost ([^:]+) "
                                          r"...")]),
                        # NOTE: we don't use a list for the body here because
                        # we need to know which expression matched so that we
                        # can know in which order to retrieve the columns since
                        # their order is inverted between 3.6.x and 3.8.x
                        body=SearchDef(r"^(?:<([^.\s]+)[.0-9]+>\s+(\S+)|"
                                       r"(\S+)\s+(?:\S+\s+){4}<([^.\s]+)[.0-9]"
                                       r"+>)\s+.+"),
                        end=SearchDef(r"^$"),
                        tag="queues"),
                "callbacks":
                    [self.get_queue_info]
                },
            "connections": {
                "searchdef":
                    SequenceSearchDef(
                        start=SearchDef([r"^Connections:$",
                                         r"^Listing connections ...$"]),
                        # Again, the user and protocol columns are inverted
                        # between 3.6.x and 3.8.x so we have to catch both and
                        # decide.
                        body=SearchDef(r"^<(rabbit[^>.]*)(?:[.][0-9]+)+>.+(?:[A-Z]+\s+{[\d,]+}\s+(\S+)|\d+\s+{[\d,]+}\s+\S+\s+(\S+)).+{\"connection_name\",\"([^:]+):\d+:.+$"),  # noqa
                        end=SearchDef(r"^$"),
                        tag="connections"),
                "callbacks":
                    [self.get_connection_distribution]
                },
            "memory": {
                "searchdef":
                    SequenceSearchDef(
                        start=SearchDef([r"^Status of node '([^']*)'$",
                                         r"^Status of node ([^']*) ...$"]),
                        body=SearchDef(r"^\s+\[{total,([0-9]+)}.+"),
                        end=SearchDef(r"^$"),
                        tag="memory"),
                "callbacks":
                    [self.get_memory_used]
                },
            "partitioning": {
                "searchdef":
                    SearchDef(r"^\s*{cluster_partition_handling,([^}]*)}",
                              tag="cluster_partition_handling"),
                "callbacks":
                [self.get_partition_handling]
            }
        }
        for s in self._sequences.values():
            self.searcher.add_search_term(s["searchdef"], self.f_report)

    def _get_vhost_queue_counts(self, section, seq_def):
        vhost = None
        queues = {}
        for result in section:
            if result.tag == seq_def.start_tag:
                # check both report formats
                vhost = result.get(1)
            elif result.tag == seq_def.body_tag:
                node_name = result.get(1) or result.get(4)
                # if we matched the section header, skip
                if node_name == "pid":
                    continue

                queue = result.get(2) or result.get(3)
                # if we matched the section header, skip
                if queue == "name":
                    continue

                if node_name not in queues:
                    queues[node_name] = 0

                queues[node_name] += 1

        return vhost, queues

    def get_queue_info(self):
        """Get distribution of queues across cluster."""
        seq_def = self._sequences["queues"]["searchdef"]
        vhost_queues = {}
        vhost_info = {}
        issues_raised = {}
        skewed_queue_nodes = {}
        for section in self.results.find_sequence_sections(seq_def).values():
            vhost, queues = self._get_vhost_queue_counts(section, seq_def)
            vhost_info[vhost] = queues

        global_total_queues = sum([sum(queues.values())
                                   for queues in vhost_info.values()])
        for vhost, queues in vhost_info.items():
            # log anyway to show empty vhosts
            vhost_queues[vhost] = {}
            if not queues:
                continue

            total = sum(queues.values())
            for node_name in queues:
                total_pcent = float(100) / global_total_queues * total
                if total > 0:
                    fraction = queues[node_name] / total
                    fraction_string = "{:.2f}%".format(fraction * 100)
                    # ignore vhosts that have < 1% of total number of queues
                    if total_pcent >= 1 and fraction > 2 / 3:
                        if node_name not in skewed_queue_nodes:
                            skewed_queue_nodes[node_name] = 0

                        skewed_queue_nodes[node_name] += 1
                else:
                    fraction_string = "N/A"

                vhost_queues[vhost][node_name] = "{:d} ({})".format(
                    queues[node_name], fraction_string)

            # Report the node with the greatest skew of queues/vhost
            if skewed_queue_nodes:
                max_node = None
                for node_name in skewed_queue_nodes:
                    if max_node is None:
                        max_node = node_name
                    elif (skewed_queue_nodes[node_name] >=
                            skewed_queue_nodes[max_node]):
                        max_node = node_name

                if (skewed_queue_nodes[max_node] >
                        issues_raised.get(max_node, 0)):
                    issues_raised[max_node] = skewed_queue_nodes[max_node]

        # this should only actually ever report one node
        for node_name in issues_raised:
            msg = ("{} holds more than 2/3 of queues for {}/{} vhost(s)".
                   format(node_name, issues_raised[node_name],
                          len(vhost_queues)))
            issue_utils.add_issue(issue_types.RabbitMQWarning(msg))

        if vhost_queues:
            # list all vhosts but only show their queues if not []
            self.resources["vhosts"] = sorted(list(vhost_queues.keys()))
            self.resources["vhost-queue-distributions"] = \
                {k: v for k, v in vhost_queues.items() if v}

    def get_connection_distribution(self):
        """Get distribution of connections across cluster."""
        sd = self._sequences["connections"]["searchdef"]
        host_connections = {}
        client_connections = {}

        for results in self.results.find_sequence_sections(sd).values():
            for result in results:
                if result.tag == sd.body_tag:
                    host = result.get(1)
                    if host not in host_connections:
                        host_connections[host] = 1
                    else:
                        host_connections[host] += 1

                    # detect 3.6.x or 3.8.x format
                    user = result.get(2)
                    if user is None:
                        user = result.get(3)

                    client_name = result.get(4)
                    if user not in client_connections:
                        client_connections[user] = {}

                    if client_name not in client_connections[user]:
                        client_connections[user][client_name] = 1
                    else:
                        client_connections[user][client_name] += 1

        if host_connections:
            for client, vals in client_connections.items():
                client_connections[client] = sorted_dict(vals,
                                                         key=lambda e: e[1],
                                                         reverse=True)
            self.resources["connections-per-host"] = host_connections
            self.resources["client-connections"] = client_connections

    def get_memory_used(self):
        """Get the memory used per broker."""
        sd = self._sequences["memory"]["searchdef"]
        memory_used = {}
        for results in self.results.find_sequence_sections(sd).values():
            for result in results:
                if result.tag == sd.start_tag:
                    # check both report formats
                    node_name = result.get(1)
                elif result.tag == sd.body_tag:
                    total = result.get(1)
                    mib_used = int(total) / 1024. / 1024.
                    memory_used[node_name] = "{:.3f}".format(mib_used)

        if memory_used:
            self.resources["memory-used-mib"] = memory_used

    def get_partition_handling(self):
        """Get the partition handling settings."""
        results = self.results.find_by_tag("cluster_partition_handling")
        if not results:
            return

        setting = results[0].get(1)
        if setting == "ignore":
            msg = "Cluster partition handling is currently set to ignore. " \
                "This is potentially dangerous and a setting of " \
                "pause_minority is recommended."
            issue_utils.add_issue(issue_types.RabbitMQWarning(msg))
            self.resources["cluster-partition-handling"] = setting

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

        self._output["resources"] = self.resources

    def __call__(self):
        self.get_running_services_info()
        self.run_report_searches()
