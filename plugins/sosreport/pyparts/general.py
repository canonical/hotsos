from core.plugins.sosreport import SOSReportChecksBase

YAML_PRIORITY = 0


class SOSReportInfo(SOSReportChecksBase):

    def __call__(self):
        if self.version is not None:
            self._output['version'] = self.version

        if self.apt_check.core:
            self._output['dpkg'] = self.apt_check.all_formatted

        if self.timed_out_plugins:
            self._output['plugin-timeouts'] = self.timed_out_plugins
