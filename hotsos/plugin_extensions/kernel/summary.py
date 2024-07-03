import re

from hotsos.core.plugins.kernel.common import KernelChecksBase
from hotsos.core.plugins.kernel.config import SystemdConfig
from hotsos.core.plugins.kernel.memory import MemoryChecks
from hotsos.core.plugins.kernel.sysfs import CPU


class KernelSummary(KernelChecksBase):
    summary_part_index = 0

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

    def __0_summary_version(self):
        return self.version or None

    def __1_summary_boot(self):
        if self.boot_parameters:
            return ' '.join(self.boot_parameters)

        return None

    @staticmethod
    def __2_summary_systemd():
        cfg = SystemdConfig()
        if cfg.exists:
            if cfg.get('CPUAffinity'):
                return {'CPUAffinity': cfg.get('CPUAffinity')}

        return None

    def __3_summary_cpu(self):
        return self.cpu_info or None

    @staticmethod
    def __4_summary_memory():
        return MemoryChecks().nodes_with_limited_high_order_memory_full or None
