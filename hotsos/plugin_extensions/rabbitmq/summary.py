from hotsos.core.plugins.rabbitmq import RabbitMQChecks
from hotsos.core.plugintools import (
    summary_entry,
    get_min_available_entry_index,
)


class RabbitMQSummary(RabbitMQChecks):
    """ Implementation of RabbitMQ summary. """
    summary_part_index = 0

    # REMINDER: common entries are implemented in the SummaryBase base class
    #           and only application plugin specific customisations are
    #           implemented here. We use the get_min_available_entry_index() to
    #           ensure that additional entries don't clobber existing ones but
    #           conversely can also replace them by re-using their indices.

    @property
    def queue_info(self):
        """Get distribution of queues across cluster."""
        vhosts = self.report.vhosts
        vhost_queue_dists = {}
        for vhost in vhosts:
            # include anyway to show empty vhosts
            vhost_queue_dists[vhost.name] = {}
            if not vhost.total_queues:
                continue

            for node, vhost_dist in vhost.node_queue_distributions.items():
                if vhost_dist['queues']:
                    vhost_queue_dists[vhost.name][node] = \
                        (f"{vhost_dist['queues']:d} "
                         f"({vhost_dist['pcent']:.2f}%)")
                else:
                    vhost_queue_dists[vhost.name][node] = \
                        f"{vhost_dist['queues']:d} (N/A)"

        _queue_info = {}
        if vhost_queue_dists:
            # list all vhosts but only show their queues if not []
            _queue_info["vhosts"] = sorted([vhost.name for vhost in vhosts])
            _queue_info["vhost-queue-distributions"] = \
                {k: v for k, v in vhost_queue_dists.items() if v}
            return _queue_info

        return None

    @summary_entry('config', get_min_available_entry_index())
    def summary_config(self):
        setting = self.report.partition_handling or 'unknown'
        return {'cluster-partition-handling': setting}

    @summary_entry('resources', get_min_available_entry_index() + 1)
    def summary_resources(self):
        resources = {}
        _queue_info = self.queue_info
        if _queue_info:
            resources.update(_queue_info)

        connections = self.report.connections
        if connections['host']:
            resources["connections-per-host"] = connections['host']

        if connections['client']:
            resources["client-connections"] = connections['client']

        if self.report.memory_used:
            resources["memory-used-mib"] = self.report.memory_used

        return resources or None
