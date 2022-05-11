from hotsos.core.host_helpers import (
    APTPackageChecksBase,
    ServiceChecksBase,
)
from hotsos.core import plugintools


SVC_VALID_SUFFIX = r'[0-9a-zA-Z-_]*'
MYSQL_SVC_EXPRS = [r'mysql{}'.format(SVC_VALID_SUFFIX)]
CORE_APT = ['mysql']


class MySQLChecksBase(plugintools.PluginPartBase):

    def __init__(self, *args, **kwargs):
        super().__init__()
        self.apt_info = APTPackageChecksBase(core_pkgs=CORE_APT)
        self.systemd_info = ServiceChecksBase(service_exprs=MYSQL_SVC_EXPRS)

    @property
    def plugin_runnable(self):
        return self.apt_info.core is not None
