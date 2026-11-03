import re

from hotsos.core.host_helpers import SYSCtlFactory
from hotsos.core.plugins.kernel.common import KernelChecks
from hotsos.core.plugins.kernel.config import SystemdConfig
from hotsos.core.plugins.kernel.memory import MemoryChecks
from hotsos.core.plugins.kernel.net import (
    NetStatTCP,
    SNMPTcp,
    SNMPUdp,
)
from hotsos.core.plugins.kernel.netdata import (
    HostData,
    LinkData,
    TCPData,
    UDPData,
)
from hotsos.core.plugins.kernel.sysfs import CPU
from hotsos.core.plugintools import summary_entry


class KernelSummary(KernelChecks):
    """ Implementation of Kernel summary. """
    summary_part_index = 0

    # sysctl settings surfaced as context for the kernel network scenarios.
    # Per-interface net.ipv4.conf.<iface>.rp_filter keys are collected
    # separately (see _network_sysctls) since the interface names are dynamic.
    NETWORK_SYSCTLS = (
        'net.core.somaxconn',
        'net.core.netdev_max_backlog',
        'net.core.netdev_budget',
        'net.core.netdev_budget_usecs',
        'net.core.rmem_default',
        'net.core.rmem_max',
        'net.core.wmem_default',
        'net.core.wmem_max',
        'net.ipv4.tcp_max_syn_backlog',
        'net.ipv4.tcp_abort_on_overflow',
        'net.ipv4.tcp_syncookies',
        'net.ipv4.tcp_rmem',
        'net.ipv4.tcp_mem',
        'net.ipv4.udp_mem',
        'net.ipv4.udp_rmem_min',
        'net.ipv4.udp_wmem_min',
        'net.netfilter.nf_conntrack_buckets',
        'net.netfilter.nf_conntrack_tcp_timeout_established',
        'vm.min_free_kbytes',
        'vm.swappiness',
    )

    # REMINDER: Common entries are implemented in
    #           plugintools.ApplicationSummaryBase. Only customisations are
    #           implemented here. See
    #           plugintools.get_min_available_entry_index() for an explanation
    #           on how entry indices are managed.

    @property
    def cpu_info(self):
        """Return CPU vendor, model, SMT and isolation info."""
        cpu = CPU()
        info = {}
        if cpu.vendor:
            info['vendor'] = cpu.vendor

        if cpu.model:
            model = cpu.model.lower()
            ret = None
            # strip intel or amd trailing info
            if 'intel' in cpu.vendor:
                ret = re.search(r'(.+) cpu @ .+', model)
            elif 'amd' in cpu.vendor:
                ret = re.search(r'(.+) \d+-core .+', model)

            if ret:
                model = ret.group(1).strip()

            info['model'] = model

        if cpu.smt is not None:
            if cpu.smt:
                info['smt'] = 'enabled'
            else:
                info['smt'] = 'disabled'

        if cpu.isolated is not None and cpu.isolated != '':
            info['isolated'] = cpu.isolated

        cpu_gov_all = cpu.cpufreq_scaling_governor_all
        info['cpufreq-scaling-governor'] = cpu_gov_all
        return info

    @summary_entry("version", 0)
    def summary_version(self):
        """Return the kernel version."""
        return self.version or None

    @summary_entry("boot", 1)
    def summary_boot(self):
        """Return kernel boot parameters."""
        if self.boot_parameters:
            return ' '.join(self.boot_parameters)

        return None

    @staticmethod
    @summary_entry("systemd", 2)
    def summary_systemd():
        """Return systemd CPUAffinity config if set."""
        cfg = SystemdConfig()
        if cfg.exists:
            if cfg.get('CPUAffinity'):
                return {'CPUAffinity': cfg.get('CPUAffinity')}

        return None

    @summary_entry("cpu", 3)
    def summary_cpu(self):
        """Return CPU information."""
        return self.cpu_info or None

    @staticmethod
    @summary_entry("memory", 4)
    def summary_memory():
        """Return nodes with limited high-order memory."""
        return MemoryChecks().nodes_with_limited_high_order_memory_full or None

    @staticmethod
    def _prune(data):
        """ Recursively drop empty, None or zero valued entries. """
        pruned = {}
        for key, value in data.items():
            if isinstance(value, dict):
                value = KernelSummary._prune(value)

            if not value:
                continue

            pruned[key] = value

        return pruned

    @classmethod
    def _network_sysctls(cls, sysctl):
        """ Relevant network sysctl settings. """
        keys = [key for key in cls.NETWORK_SYSCTLS if key in sysctl]
        return {key: sysctl[key] for key in keys}

    @staticmethod
    def _proc_net_counters():
        """
        Raw /proc/net counters referenced by the kernel network scenarios,
        grouped by transport. Only non-zero counters survive _prune so this
        surfaces just the counters currently reporting activity.
        """
        return {
            'tcp': {
                **NetStatTCP().notable_counters,
                **SNMPTcp().notable_counters,
            },
            'udp': SNMPUdp().notable_counters,
        }

    def network_info(self):
        """
        Collect network context datapoints referenced by the kernel network
        scenarios. Empty, None and zero valued entries are omitted so that the
        section only surfaces information that is actually present.
        """
        tcp = TCPData()
        udp = UDPData()
        link = LinkData()
        host = HostData()
        sysctl = SYSCtlFactory().sysctl_all
        info = {
            'tcp-sockets': {
                'states': tcp.socket_states,
                'queued-listeners': tcp.queued_listeners,
                'half-open-connections': tcp.half_open_connections,
                'half-open-ports': tcp.half_open_ports,
                'unaccepted-connections': tcp.unaccepted_connections,
                'memory-consumers': tcp.socket_memory_consumers,
                'sockets-w-non-empty-recv-buffer':
                    tcp.sockets_w_non_empty_recv_buffer,
                'socket-count-consumers': tcp.socket_count_consumers,
                'retransmitting-connections': tcp.retransmitting_connections,
            },
            'udp-sockets': {
                'receive-queue': udp.receive_queue_sockets,
                'send-queue': udp.send_queue_sockets,
                'memory-consumers': udp.socket_memory_consumers,
                'sockets-w-non-empty-recv-buffer':
                    udp.sockets_w_non_empty_recv_buffer,
                'socket-count-consumers': udp.socket_count_consumers,
            },
            'interfaces': {
                'rx-errors': link.rx_error_interfaces,
                'tx-errors': link.tx_error_interfaces,
            },
            'softnet-drops': host.softnet_drops,
            'softnet-time-squeeze': host.softnet_time_squeeze,
            'interrupts': {
                'total': host.nic_interrupt_total,
                'busiest-cpu': host.nic_interrupt_busiest_cpu,
                'busiest-cpu-pcent': host.nic_interrupt_busiest_pcent,
                'nic-irqs': host.nic_irqs,
            },
            'conntrack': {
                'usage-pcent': host.conntrack_usage_pcent,
                'entries-by-protocol': host.conntrack_entries_by_protocol,
                'tcp-states': host.conntrack_tcp_states,
            },
            'reverse-path-filter': {
                'strict-interfaces': host.strict_rp_filter_interfaces,
                'routing-daemons': host.routing_daemons,
            },
            'proc-net-counters': self._proc_net_counters(),
            'sysctl': self._network_sysctls(sysctl),
        }
        return self._prune(info)

    @summary_entry("network", 5)
    def summary_network(self):
        """Return network context datapoints relevant to kernel checks."""
        return self.network_info() or None
