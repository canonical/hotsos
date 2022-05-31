import os
from hotsos.core.host_helpers import (
    APTPackageChecksBase,
    ServiceChecksBase,
)
from hotsos.core import (
    host_helpers,
    plugintools,
)

from hotsos.core.config import HotSOSConfig

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


class MySQLConfig(host_helpers.SectionalConfigBase):
    def __init__(self, *args, **kwargs):
        path = os.path.join(HotSOSConfig.DATA_ROOT,
                            'etc/mysql/mysql.conf.d/mysqld.cnf')
        super().__init__(*args, path=path, **kwargs)
