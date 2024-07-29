import re

from hotsos.core.plugins.kernel.common import KernelChecks
from hotsos.core.plugins.kernel.config import SystemdConfig
from hotsos.core.plugins.kernel.memory import MemoryChecks
from hotsos.core.plugins.kernel.sysfs import CPU
from hotsos.core.plugintools import summary_entry


class KernelSummary(KernelChecks):
    """ Implementation of Kernel summary. """
    summary_part_index = 0

    # REMINDER: common entries are implemented in the SummaryBase base class
    #           and only application plugin specific customisations are
    #           implemented here. We use the get_min_available_entry_index() to
    #           ensure that additional entries don't clobber existing ones but
    #           conversely can also replace them by re-using their indices.

    @property
    def cpu_info(self):
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
        return self.version or None

    @summary_entry("boot", 1)
    def summary_boot(self):
        if self.boot_parameters:
            return ' '.join(self.boot_parameters)

        return None

    @staticmethod
    @summary_entry("systemd", 2)
    def summary_systemd():
        cfg = SystemdConfig()
        if cfg.exists:
            if cfg.get('CPUAffinity'):
                return {'CPUAffinity': cfg.get('CPUAffinity')}

        return None

    @summary_entry("cpu", 3)
    def summary_cpu(self):
        return self.cpu_info or None

    @staticmethod
    @summary_entry("memory", 4)
    def summary_memory():
        return MemoryChecks().nodes_with_limited_high_order_memory_full or None
