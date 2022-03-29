from hotsos.core.plugintools import summary_entry_offset as idx
from hotsos.core.plugins.kernel import (
    CPU,
    KernelChecksBase,
    SystemdConfig,
)


class KernelSummary(KernelChecksBase):

    @property
    def cpu_info(self):
        cpu = CPU()
        info = {}
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

    @idx(0)
    def __summary_version(self):
        if self.version:
            return self.version

    @idx(1)
    def __summary_boot(self):
        if self.boot_parameters:
            return ' '.join(self.boot_parameters)

    @idx(2)
    def __summary_systemd(self):
        cfg = SystemdConfig()
        if cfg.exists:
            if cfg.get('CPUAffinity'):
                return {'CPUAffinity': cfg.get('CPUAffinity')}

    @idx(3)
    def __summary_cpu(self):
        cpu_info = self.cpu_info
        if cpu_info:
            return cpu_info
