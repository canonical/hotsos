import os
import re

from hotsos.core.config import HotSOSConfig
from hotsos.core.plugins.openstack.openstack import (
    OSTServiceBase,
    OpenstackConfig,
)
from hotsos.core.host_helpers import CLIHelper
from hotsos.core.plugins.kernel.config import (
    KernelConfig,
    SystemdConfig,
)
from hotsos.core.plugins.system.system import (
    NUMAInfo,
    SystemBase,
)
from hotsos.core.utils import cached_property


class NovaBase(OSTServiceBase):

    def __init__(self, *args, **kwargs):
        super().__init__('nova', *args, **kwargs)
        self.nova_config = self.project.config['main']

    @cached_property
    def instances(self):
        instances = {}
        for line in CLIHelper().ps():
            ret = re.compile('.+product=OpenStack Nova.+').match(line)
            if ret:
                name = None
                uuid = None

                expr = r'.+uuid\s+([a-z0-9\-]+)[\s,]+.+'
                ret = re.compile(expr).match(ret[0])
                if ret:
                    uuid = ret[1]

                expr = r'.+\s+-name\s+guest=(instance-\w+)[,]*.*\s+.+'
                ret = re.compile(expr).match(ret[0])
                if ret:
                    name = ret[1]

                if not all([name, uuid]):
                    continue

                guest = NovaInstance(uuid, name)
                ret = re.compile(r'mac=([a-z0-9:]+)').findall(line)
                if ret:
                    for mac in ret:
                        # convert libvirt to local/native
                        mac = 'fe' + mac[2:]
                        _port = self.nethelp.get_interface_with_hwaddr(mac)
                        if _port:
                            guest.add_port(_port)

                ret = re.compile(r'.+\s-m\s+(\d+)').search(line)
                if ret:
                    guest.memory_mbytes = int(ret.group(1))

                instances[uuid] = guest

        return instances

    def get_nova_config_port(self, cfg_key):
        """
        Fetch interface used by Openstack Nova config. Returns NetworkPort.
        """
        addr = self.nova_config.get(cfg_key)
        if not addr:
            return

        return self.nethelp.get_interface_with_addr(addr)

    @cached_property
    def my_ip_port(self):
        # NOTE: my_ip can be an address or fqdn, we currently only support
        # searching by address.
        return self.get_nova_config_port('my_ip')

    @cached_property
    def live_migration_inbound_addr_port(self):
        return self.get_nova_config_port('live_migration_inbound_addr')

    @cached_property
    def bind_interfaces(self):
        """
        Fetch interfaces used by Openstack Nova. Returned dict is keyed by
        config key used to identify interface.
        """
        interfaces = {}
        if self.my_ip_port:
            interfaces['my_ip'] = self.my_ip_port

        if self.live_migration_inbound_addr_port:
            port = self.live_migration_inbound_addr_port
            interfaces['live_migration_inbound_addr'] = port

        return interfaces


class CPUPinning(NovaBase):

    def __init__(self):
        super().__init__()
        self.numa = NUMAInfo()
        self.systemd = SystemdConfig()
        self.kernel = KernelConfig()
        self.nova_cfg = OpenstackConfig(os.path.join(HotSOSConfig.data_root,
                                                     'etc/nova/nova.conf'))
        self.isolcpus = set(self.kernel.get('isolcpus',
                                            expand_to_list=True) or [])
        self.cpuaffinity = set(self.systemd.get('CPUAffinity',
                                                expand_to_list=True) or [])

    @cached_property
    def cpu_dedicated_set(self):
        key = 'cpu_dedicated_set'
        return self.nova_cfg.get(key, expand_to_list=True) or []

    @cached_property
    def cpu_shared_set(self):
        key = 'cpu_shared_set'
        return self.nova_cfg.get(key, expand_to_list=True) or []

    @cached_property
    def vcpu_pin_set(self):
        key = 'vcpu_pin_set'
        return self.nova_cfg.get(key, expand_to_list=True) or []

    @cached_property
    def cpu_dedicated_set_name(self):
        """
        If the vcpu_pin_set option has a value, we use that option as the name.
        """
        if self.vcpu_pin_set:
            return 'vcpu_pin_set'

        return 'cpu_dedicated_set'

    @cached_property
    def cpu_dedicated_set_intersection_isolcpus(self):
        if self.vcpu_pin_set:
            pinset = set(self.vcpu_pin_set)
        else:
            pinset = set(self.cpu_dedicated_set)

        return list(pinset.intersection(self.isolcpus))

    @cached_property
    def cpu_dedicated_set_intersection_cpuaffinity(self):
        if self.vcpu_pin_set:
            pinset = set(self.vcpu_pin_set)
        else:
            pinset = set(self.cpu_dedicated_set)

        return list(pinset.intersection(self.cpuaffinity))

    @cached_property
    def cpu_shared_set_intersection_isolcpus(self):
        return list(set(self.cpu_shared_set).intersection(self.isolcpus))

    @cached_property
    def cpuaffinity_intersection_isolcpus(self):
        return list(self.cpuaffinity.intersection(self.isolcpus))

    @cached_property
    def cpu_shared_set_intersection_cpu_dedicated_set(self):
        if self.vcpu_pin_set:
            pinset = set(self.vcpu_pin_set)
        else:
            pinset = set(self.cpu_dedicated_set)

        return list(set(self.cpu_shared_set).intersection(pinset))

    @cached_property
    def num_unpinned_cpus(self):
        num_cpus = SystemBase().num_cpus
        total_isolated = len(self.isolcpus.union(self.cpuaffinity))
        return num_cpus - total_isolated

    @cached_property
    def unpinned_cpus_pcent(self):
        num_cpus = SystemBase().num_cpus
        if num_cpus and self.num_unpinned_cpus:
            return int((float(100) / num_cpus) * self.num_unpinned_cpus)

        return 0

    @cached_property
    def nova_pinning_from_multi_numa_nodes(self):
        if self.vcpu_pin_set:
            pinset = set(self.vcpu_pin_set)
        else:
            pinset = set(self.cpu_dedicated_set)

        node_count = 0
        for node in self.numa.nodes:
            node_cores = set(self.numa.cores(node))
            if pinset.intersection(node_cores):
                node_count += 1

        return node_count > 1


class NovaInstance(object):
    def __init__(self, uuid, name):
        self.uuid = uuid
        self.name = name
        self.ports = []
        self.memory_mbytes = None

    def add_port(self, port):
        self.ports.append(port)
