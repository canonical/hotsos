import os

from core import (
    checks,
    constants,
)
from core.plugintools import PluginPartBase

CORE_APT = ['sosreport']


class SOSReportChecksBase(PluginPartBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apt_check = checks.APTPackageChecksBase(core_pkgs=CORE_APT)

    @property
    def data_root_is_sosreport(self):
        path = os.path.join(constants.DATA_ROOT, 'sos_commands')
        if os.path.isdir(path):
            return True

        return False

    @property
    def version(self):
        if not self.data_root_is_sosreport:
            return

        path = os.path.join(constants.DATA_ROOT, 'version.txt')
        if not os.path.exists(path):
            return

        with open(path) as fd:
            for line in fd:
                if line.startswith('sosreport:'):
                    return line.partition(' ')[2].strip()

    @property
    def plugin_runnable(self):
        return self.data_root_is_sosreport
