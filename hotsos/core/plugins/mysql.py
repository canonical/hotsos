import glob
import os
from dataclasses import dataclass, field

from hotsos.core.config import HotSOSConfig
from hotsos.core.host_helpers import (
    APTPackageHelper,
    InstallInfoBase,
    PebbleHelper,
    SystemdHelper,
)
from hotsos.core import (
    host_helpers,
    plugintools,
)

SVC_VALID_SUFFIX = r'[0-9a-zA-Z-_]*'
MYSQL_SVC_EXPRS = [rf'mysql{SVC_VALID_SUFFIX}']
CORE_APT = ['mysql']


@dataclass
class MySQLInstallInfo(InstallInfoBase):
    """ MySQL installation information. """
    apt: APTPackageHelper = field(default_factory=lambda:
                                  APTPackageHelper(core_pkgs=CORE_APT))
    pebble: PebbleHelper = field(default_factory=lambda:
                                 PebbleHelper(service_exprs=MYSQL_SVC_EXPRS))
    systemd: SystemdHelper = field(default_factory=lambda:
                                   SystemdHelper(
                                                service_exprs=MYSQL_SVC_EXPRS))


class MySQLChecks(plugintools.PluginPartBase):
    """ MySQL checks. """
    plugin_name = 'mysql'
    plugin_root_index = 3

    def __init__(self, *args, **kwargs):
        super().__init__()
        MySQLInstallInfo().mixin(self)

    @classmethod
    def is_runnable(cls):
        """
        Determine whether or not this plugin can and should be run.

        @return: True or False
        """
        return len(MySQLInstallInfo().apt.core) > 0


class MySQLConfig(host_helpers.IniConfigBase):
    """ MySQL config interface. """
    def __init__(self, *args, **kwargs):
        path = os.path.join(HotSOSConfig.data_root,
                            'etc/mysql/mysql.conf.d/mysqld.cnf')
        super().__init__(*args, path=path, **kwargs)


class MySQLRouterConfig(host_helpers.IniConfigBase):
    """ MySQL Router config interface. """
    def __init__(self, *args, **kwargs):
        path = os.path.join(HotSOSConfig.data_root,
                            'var/lib/mysql/*mysql-router/mysqlrouter.conf')
        # expect only one
        for f in glob.glob(path):
            path = f

        super().__init__(*args, path=path, **kwargs)
