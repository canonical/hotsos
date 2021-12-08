import re

from core.cli_helpers import CLIHelper
from core.plugins.openstack import OpenstackChecksBase

YAML_PRIORITY = 4


class OpenstackNetworkChecks(OpenstackChecksBase):

    def __init__(self):
        super().__init__()
        self.cli = CLIHelper()

    @property
    def output(self):
        if self._output:
            return {"network": self._output}

    def _get_port_stat_outliers(self, counters):
        """ For a given port's packet counters, identify outliers i.e. > 1%
        and create a new dict with count and percent values.
        """
        stats = {}
        for rxtx in counters:
            total = sum(counters[rxtx].values())
            del counters[rxtx]["packets"]
            for key, value in counters[rxtx].items():
                if value:
                    pcent = int(100 / float(total) * float(value))
                    if pcent <= 1:
                        continue

                    if rxtx not in stats:
                        stats[rxtx] = {}

                    stats[rxtx][key] = "{} ({}%)".format(int(value), pcent)

        return stats

    def get_config_network_info(self):
        """ Identify ports used by Openstack services, include them in output
        for informational purposes along with their health (dropped packets
        etc) for any outliers detected.
        """
        port_health_info = {}
        config_info = {}

        for project in ['nova', 'neutron', 'octavia']:
            _project = getattr(self, project)
            if _project and _project.bind_interfaces:
                config_info[project] = {name: port.to_dict() for name, port in
                                        _project.bind_interfaces.items()}
                for name, port in _project.bind_interfaces.items():
                    if project not in config_info:
                        config_info[project] = {}

                    config_info[project][name] = port.to_dict()
                    if port.stats:
                        stats = self._get_port_stat_outliers(port.stats)
                        if not stats:
                            continue

                        port_health_info[port.name] = stats

        if config_info:
            self._output['config'] = config_info

        if port_health_info:
            health = {'phy-ports': port_health_info}
            if 'port-health' in self._output:
                self._output['port-health'].update(health)
            else:
                self._output['port-health'] = health

    def get_ns_info(self):
        """Populate namespace information dict."""
        ns_info = {}
        for line in self.cli.ip_netns():
            ret = re.compile(r"^([a-z0-9]+)-([0-9a-z\-]+)\s+.+").match(line)
            if ret:
                if ret[1] in ns_info:
                    ns_info[ret[1]] += 1
                else:
                    ns_info[ret[1]] = 1

        if ns_info:
            self._output["namespaces"] = ns_info

    def get_instances_port_health(self):
        """ For each instance get its ports and check port health, reporting on
        any outliers. """
        if not self.nova.instances:
            return

        port_health_info = {}
        for guest in self.nova.instances:
            for port in guest.ports:
                stats = port.stats
                if stats:
                    outliers = self._get_port_stat_outliers(stats)
                    if not outliers:
                        continue

                    if guest.uuid not in port_health_info:
                        port_health_info[guest.uuid] = {}

                    port_health_info[guest.uuid][port.hwaddr] = outliers

        if port_health_info:
            health = {"vm-ports": {"num-vms-checked": len(self.nova.instances),
                                   "stats": port_health_info}}
            if "port-health" in self._output:
                self._output["port-health"].update(health)
            else:
                self._output["port-health"] = health

    def __call__(self):
        # Only run if we think Openstack is installed.
        if not self.openstack_installed:
            return

        self.get_ns_info()
        self.get_config_network_info()
        self.get_instances_port_health()
