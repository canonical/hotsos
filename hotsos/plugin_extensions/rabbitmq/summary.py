from hotsos.core.plugins.rabbitmq import RabbitMQChecksBase


class RabbitMQSummary(RabbitMQChecksBase):
    summary_part_index = 0

    def __0_summary_services(self):
        if self.systemd.services:
            return self.systemd.summary
        if self.pebble.services:
            return self.pebble.summary

        return None

    def __1_summary_dpkg(self):
        return self.apt.all_formatted or None

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

    def __2_summary_config(self):
        setting = self.report.partition_handling or 'unknown'
        return {'cluster-partition-handling': setting}

    def __3_summary_resources(self):
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
