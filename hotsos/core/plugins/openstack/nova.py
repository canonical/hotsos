import os
import re
from functools import cached_property
from dataclasses import dataclass

from hotsos.core.plugins.kernel.sysfs import CPU
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
from hotsos.core.search import (
    FileSearcher,
    SearchDef,
    SequenceSearchDef,
)
from hotsos.core.plugins.system.system import (
    NUMAInfo,
    SystemBase,
)


@dataclass
class NovaQemuProcessIdentifierBase():
    """
    Base class for identifiers used to find qemu processes in ps output.
    """
    item: str = r'.+qemu.+product=OpenStack Nova.+'
    uuid: str = r'.+uuid\s+([a-z0-9\-]+)[\s,]+.+'
    name: str = r'.+\s+-name\s+guest=(instance-\w+)[,]*.*\s+.+'
    mac: str = r'mac=([a-z0-9:]+)'
    guest_mem: str = r'.+\s-m\s+(\d+)'


@dataclass
class NovaQemuProcessIdentifierx86(NovaQemuProcessIdentifierBase):
    """ Identifies qemu entries in ps output on x86 machines. """


@dataclass
class NovaQemuProcessIdentifierARM(NovaQemuProcessIdentifierBase):
    """ Identifies qemu entries in ps output on ARM machines. """
    item: str = r'.+qemu.+nova.+'


class NovaBase(OSTServiceBase):
    """ Base class for Nova checks. """
    def __init__(self, *args, **kwargs):
        super().__init__('nova', *args, **kwargs)
        self.nova_config = self.project.config['main']

    def get_instances(self, identifiers):
        """
        Get UUIDs of Nova instances.

        This looks for qemu processes in ps output that look like they were
        started by Nova.
        """
        instances = {}
        for line in CLIHelper().ps():
            ret = re.compile(identifiers.item).match(line)
            if not ret:
                continue

            ret = re.compile(identifiers.uuid).match(ret[0])
            if not ret:
                continue

            uuid = ret[1]
            ret = re.compile(identifiers.name).match(ret[0])
            if not ret:
                continue

            name = ret[1]
            guest = NovaInstance(uuid, name)
            ret = re.compile(identifiers.mac).findall(line)
            if ret:
                for mac in ret:
                    # convert libvirt to local/native
                    mac = 'fe' + mac[2:]
                    _port = self.nethelp.get_interface_with_hwaddr(mac)
                    if _port:
                        guest.add_port(_port)

            ret = re.compile(identifiers.guest_mem).search(line)
            if ret:
                guest.memory_mbytes = int(ret.group(1))

            instances[uuid] = guest

        return instances

    @cached_property
    def instances(self):
        return self.get_instances(NovaQemuProcessIdentifierx86) or \
                   self.get_instances(NovaQemuProcessIdentifierARM)

    def get_nova_config_port(self, cfg_key):
        """
        Fetch interface used by Openstack Nova config. Returns NetworkPort.
        """
        addr = self.nova_config.get(cfg_key)
        if not addr:
            return None

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


class NovaLibvirt(NovaBase):
    """ Interface to Nova information from libvirt. """

    @property
    def xmlpath(self):
        return os.path.join(HotSOSConfig.data_root, 'etc/libvirt/qemu')

    @cached_property
    def cpu_models(self):
        """ Fetch cpu models used by all nova instances.

        @return: dictionary of cpu models each with a count of how many
                 guests are using them.
        """
        _cpu_models = {}
        if not self.instances:
            return _cpu_models

        guests = []
        seqs = {}
        s = FileSearcher()
        for i in self.instances.values():
            guests.append(i.name)
            start = SearchDef(r"\s+<cpu .+>")
            body = SearchDef(r".+")
            end = SearchDef(r"\s+</cpu>")
            tag = f"{i.name}.cpu"
            seqs[i.name] = SequenceSearchDef(start=start, body=body,
                                             end=end, tag=tag)
            path = os.path.join(self.xmlpath, f"{i.name}.xml")
            s.add(seqs[i.name], path)

        results = s.run()
        for guest in guests:
            sections = results.find_sequence_sections(seqs[guest]).values()
            for section in sections:
                for r in section:
                    if 'body' not in r.tag:
                        continue

                    if '<model' not in r.get(0):
                        continue

                    ret = re.search(r'.+>(\S+)<.+', r.get(0))
                    if ret:
                        model = ret.group(1)
                        if model in _cpu_models:
                            _cpu_models[model] += 1
                        else:
                            _cpu_models[model] = 1

        return _cpu_models

    @property
    def vcpu_info(self):
        """ Fetch vcpu usage info used by all nova instances.

        @return: dictionary of cpu resource usage.
        """
        vcpu_info = {}
        if not self.instances:
            return vcpu_info

        guests = []
        s = FileSearcher()
        for i in self.instances.values():
            guests.append(i.name)
            tag = f"{i.name}.vcpus"
            path = os.path.join(self.xmlpath, f"{i.name}.xml")
            s.add(SearchDef(".+vcpus>([0-9]+)<.+", tag=tag), path)

        total_vcpus = 0
        results = s.run()
        for guest in guests:
            for r in results.find_by_tag(f"{guest}.vcpus"):
                vcpus = r.get(1)
                total_vcpus += int(vcpus)

        vcpu_info["used"] = total_vcpus

        sysinfo = SystemBase()
        if sysinfo.num_cpus is None:
            return vcpu_info

        total_cores = sysinfo.num_cpus
        vcpu_info["system-cores"] = total_cores

        nova_config = OpenstackConfig(os.path.join(HotSOSConfig.data_root,
                                                   "etc/nova/nova.conf"))
        pinset = nova_config.get("vcpu_pin_set",
                                 expand_to_list=True) or []
        pinset += nova_config.get("cpu_dedicated_set",
                                  expand_to_list=True) or []
        pinset += nova_config.get("cpu_shared_set",
                                  expand_to_list=True) or []
        if pinset:
            # if pinning is used, reduce total num of cores available
            # to those included in nova cpu sets.
            available_cores = len(set(pinset))
        else:
            available_cores = total_cores

        vcpu_info["available-cores"] = available_cores

        cpu = CPU()
        # put this here so that available cores value has
        # context
        if cpu.smt is not None:
            vcpu_info["smt"] = cpu.smt

        factor = float(total_vcpus) / available_cores
        vcpu_info["overcommit-factor"] = round(factor, 2)

        return vcpu_info


class CPUPinning(NovaBase):
    """ Interface to Nova CPU pinning. """
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
    def cpu_dedicated_set_hex(self):
        cores = self.cpu_dedicated_set
        if not cores:
            return 0

        _hex = 0
        for core in cores:
            _hex = _hex | 1 << core

        return _hex

    @cached_property
    def cpu_shared_set_hex(self):
        cores = self.cpu_shared_set
        if not cores:
            return 0

        _hex = 0
        for core in cores:
            _hex = _hex | 1 << core

        return _hex

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


class NovaInstance():
    """ Representation of a Nova instance. """
    def __init__(self, uuid, name):
        self.uuid = uuid
        self.name = name
        self.ports = []
        self.memory_mbytes = None

    def add_port(self, port):
        self.ports.append(port)
