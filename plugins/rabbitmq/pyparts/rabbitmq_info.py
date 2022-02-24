from core.plugins.rabbitmq import (
    RabbitMQChecksBase,
    RabbitMQServiceChecksBase,
)

YAML_PRIORITY = 0


class RabbitMQServiceChecks(RabbitMQServiceChecksBase):

    def __call__(self):
        if not self.plugin_runnable:
            return

        if self.services:
            self._output['services'] = {'systemd': self.service_info,
                                        'ps': self.process_info}

        apt = self.apt_check.all_formatted
        if apt:
            self._output['dpkg'] = apt


class RabbitMQClusterInfo(RabbitMQChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # save to file so we can search it later
        self.resources = {}

    def get_queue_info(self):
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
                    vhost_queue_dists[vhost.name][node] = (
                        "{:d} ({:.2f}%)".format(vhost_dist['queues'],
                                                vhost_dist['pcent']))
                else:
                    vhost_queue_dists[vhost.name][node] = "{:d} (N/A)".format(
                        vhost_dist['queues'])

        if vhost_queue_dists:
            # list all vhosts but only show their queues if not []
            self.resources["vhosts"] = sorted([vhost.name for vhost in vhosts])
            self.resources["vhost-queue-distributions"] = \
                {k: v for k, v in vhost_queue_dists.items() if v}

    def __call__(self):
        self.get_queue_info()

        setting = self.report.partition_handling or 'unknown'
        self._output['config'] = {'cluster-partition-handling': setting}

        connections = self.report.connections
        if connections['host']:
            self.resources["connections-per-host"] = connections['host']

        if connections['client']:
            self.resources["client-connections"] = connections['client']

        if self.report.memory_used:
            self.resources["memory-used-mib"] = self.report.memory_used

        if self.resources:
            self._output["resources"] = self.resources
