from core import checks
from core.plugintools import PluginPartBase

PACEMAKER_PKGS_CORE = ['pacemaker', 'crmsh', 'corosync']
PACEMAKER_SVC_EXPR = ['pacemaker[a-zA-Z-]*',
                      'corosync']


class PacemakerChecksBase(PluginPartBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apt_check = checks.APTPackageChecksBase(
            core_pkgs=PACEMAKER_PKGS_CORE)
        svc_exprs = PACEMAKER_SVC_EXPR
        self.svc_check = checks.ServiceChecksBase(service_exprs=svc_exprs)

    @property
    def apt_packages_all(self):
        return self.apt_check.all_formatted

    @property
    def plugin_runnable(self):
        return len(self.apt_check.core) > 0
