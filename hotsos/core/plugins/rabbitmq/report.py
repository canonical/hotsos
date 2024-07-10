from functools import cached_property

from hotsos.core.log import log
from hotsos.core.utils import sorted_dict
from hotsos.core.search import (
    SearchDef,
    SequenceSearchDef,
    FileSearcher,
)
from hotsos.core.host_helpers import CLIHelperFile


class RabbitMQReport():
    """
    Class providing easy access to the contents of a rabbitmqctl report.

    First registers search definitions to execute against rabbitmqctl report
    then runs the search to fetch the information that is then expose through
    properties.

    NOTE: the rabbitmqctl report output differs between versions 3.6.x and
          3.8.x and we try to account for either by providing optional
          regex expressions to match either.
    """

    def __init__(self):
        # save to file so we can search it later
        with CLIHelperFile() as cli:
            searcher = FileSearcher()
            fout = cli.rabbitmqctl_report()
            searcher.add(self.connections_searchdef, fout)
            searcher.add(self.memory_searchdef, fout)
            searcher.add(self.cluster_partition_handling_searchdef, fout)
            searcher.add(self.queues_searchdef, fout)
            self.results = searcher.run()

    @cached_property
    def queues_searchdef(self):
        start = SearchDef([r"^Queues on ([^:]+):",
                           (r"^Listing queues for vhost ([^:]+) "
                            r"...")])
        # NOTE: we don't use a list for the body here because
        # we need to know which expression matched so that we
        # can know in which order to retrieve the columns since
        # their order is inverted between 3.6.x and 3.8.x
        body = SearchDef(r"^(?:<([^.\s]+)[.0-9]+>\s+(\S+)|"
                         r"(\S+)\s+(?:\S+\s+){4}<([^.\s]+)[.0-9]"
                         r"+>)\s+.+")
        end = SearchDef(r"^$")
        return SequenceSearchDef(start=start, body=body, end=end,
                                 tag='queues')

    @cached_property
    def skewed_nodes(self):
        vhosts = self.vhosts
        _skewed_nodes = {}
        skewed_queue_nodes = {}
        global_total_queues = sum(vhost.total_queues for vhost in vhosts)
        for vhost in self.vhosts:
            if not vhost.total_queues:
                continue

            total_pcent = (float(100) / global_total_queues *
                           vhost.total_queues)

            for node, vhost_dist in vhost.node_queue_distributions.items():
                if total_pcent >= 1 and vhost_dist['pcent'] > 75:
                    if node not in skewed_queue_nodes:
                        skewed_queue_nodes[node] = 0

                    skewed_queue_nodes[node] += 1

            # Report the node with the greatest skew of queues/vhost
            if skewed_queue_nodes:
                max_node = None
                for node_name, count in skewed_queue_nodes.items():
                    if max_node is None:
                        max_node = node_name
                    elif count >= skewed_queue_nodes[max_node]:
                        max_node = node_name

                if (skewed_queue_nodes[max_node] >
                        _skewed_nodes.get(max_node, 0)):
                    _skewed_nodes[max_node] = skewed_queue_nodes[max_node]

        return _skewed_nodes

    @cached_property
    def vhosts(self):
        seq_def = self.queues_searchdef
        vhosts = []
        for section in self.results.find_sequence_sections(seq_def).values():
            vhost = None
            # ensure we get vhost before the rest
            for result in section:
                if result.tag == seq_def.start_tag:
                    # check both report formats
                    vhost = RabbitMQVhost(result.get(1))
                    break

            for result in section:
                if result.tag == seq_def.body_tag:
                    node_name = result.get(1) or result.get(4)
                    # if we matched the section header, skip
                    if node_name == "pid":
                        continue

                    queue = result.get(2) or result.get(3)
                    # if we matched the section header, skip
                    if queue == "name":
                        continue

                    vhost.node_inc_queue_count(node_name)

            log.debug(vhost.name)
            vhosts.append(vhost)

        return vhosts

    @cached_property
    def connections_searchdef(self):
        start = SearchDef([r"^Connections:$",
                           r"^Listing connections ...$"])
        # Again, the user and protocol columns are inverted
        # between 3.6.x and 3.8.x so we have to catch both and
        # decide.
        body = SearchDef(r"^<(rabbit[^>.]*)(?:[.][0-9]+)+>.+(?:[A-Z]+\s+{[\d,]+}\s+(\S+)|\d+\s+{[\d,]+}\s+\S+\s+(\S+)).+{\"connection_name\",\"([^:]+):\d+:.+$")  # pylint: disable=C0301  # noqa
        end = SearchDef(r"^$")
        return SequenceSearchDef(start=start, body=body, end=end,
                                 tag='connections')

    @cached_property
    def memory_searchdef(self):
        start = SearchDef([r"^Status of node '([^']*)'$",
                           r"^Status of node ([^']*) ...$"])
        body = SearchDef(r"^\s+\[{total,([0-9]+)}.+")
        end = SearchDef(r"^$")
        return SequenceSearchDef(start=start, body=body, end=end,
                                 tag='memory')

    @cached_property
    def cluster_partition_handling_searchdef(self):
        return SearchDef(r"^\s*{cluster_partition_handling,([^}]*)}",
                         tag='cluster_partition_handling')

    @cached_property
    def connections(self):
        _connections = {'host': {}, 'client': {}}
        sd = self.connections_searchdef
        for results in self.results.find_sequence_sections(sd).values():
            for result in results:
                if result.tag == sd.body_tag:
                    host = result.get(1)
                    if host not in _connections['host']:
                        _connections['host'][host] = 1
                    else:
                        _connections['host'][host] += 1

                    # detect 3.6.x or 3.8.x format
                    user = result.get(2)
                    if user is None:
                        user = result.get(3)

                    client_name = result.get(4)
                    if user not in _connections['client']:
                        _connections['client'][user] = {}

                    if client_name not in _connections['client'][user]:
                        _connections['client'][user][client_name] = 1
                    else:
                        _connections['client'][user][client_name] += 1

        if _connections['host']:
            for client, users in _connections['client'].items():
                sorted_users = sorted_dict(users, key=lambda e: e[1],
                                           reverse=True)
                _connections['client'][client] = sorted_users

        return _connections

    @cached_property
    def memory_used(self):
        sd = self.memory_searchdef
        _memory_used = {}
        for results in self.results.find_sequence_sections(sd).values():
            for result in results:
                if result.tag == sd.start_tag:
                    # check both report formats
                    node_name = result.get(1)
                elif result.tag == sd.body_tag:
                    total = result.get(1)
                    mib_used = int(total) / 1024. / 1024.
                    _memory_used[node_name] = f"{mib_used:.3f}"

        return _memory_used

    @cached_property
    def partition_handling(self):
        results = self.results.find_by_tag("cluster_partition_handling")
        if not results:
            return None

        return results[0].get(1)


class RabbitMQVhost():
    """ Representation of a vhost """
    def __init__(self, name):
        self.name = name
        self._node_queues = {}

    def node_inc_queue_count(self, node):
        if node not in self._node_queues:
            self._node_queues[node] = 0

        self._node_queues[node] += 1

    @property
    def total_queues(self):
        return sum(self.node_queues.values())

    @property
    def node_queues(self):
        return self._node_queues

    def node_queues_vhost_pcent(self, node):
        return float(100) / self.total_queues * self.node_queues[node]

    @property
    def node_queue_distributions(self):
        dists = {}
        for node, queues in self.node_queues.items():
            if queues:
                vhost_pcent = self.node_queues_vhost_pcent(node)
                dists[node] = {'queues': queues, 'pcent': vhost_pcent}
            else:
                dists[node] = {'queues': 0, 'pcent': 0}

        return dists
