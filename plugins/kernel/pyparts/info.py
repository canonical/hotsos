from core.plugins.kernel import (
    CPU,
    KernelChecksBase,
    SystemdConfig,
)

YAML_PRIORITY = 0


class KernelGeneralChecks(KernelChecksBase):

    def get_cpu_info(self):
        cpu = CPU()
        info = {}
        if cpu.smt is not None:
            if cpu.smt:
                info['smt'] = 'enabled'
            else:
                info['smt'] = 'disabled'

        if cpu.isolated is not None and cpu.isolated != '':
            info['isolated'] = cpu.isolated

        return info

    def __call__(self):
        if self.version:
            self._output['version'] = self.version

        if self.boot_parameters:
            self._output['boot'] = " ".join(self.boot_parameters)

        cfg = SystemdConfig()
        if cfg.exists:
            if cfg.get('CPUAffinity'):
                self._output['systemd'] = {'CPUAffinity':
                                           cfg.get('CPUAffinity')}

        cpu_info = self.get_cpu_info()
        if cpu_info:
            self._output['cpu'] = cpu_info
