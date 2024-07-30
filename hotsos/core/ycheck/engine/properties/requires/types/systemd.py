from datetime import timedelta

from hotsos.core.host_helpers import SystemdHelper
from hotsos.core.log import log
from hotsos.core.ycheck.engine.properties.requires import ServiceCheckItemsBase
from hotsos.core.ycheck.engine.properties.requires.types import (
    service_manager_common
)


class SystemdServiceCheckItems(ServiceCheckItemsBase):
    """
    Provides means to run checks on one or more systemd check item.
    """
    @property
    def _svcs_info(self):
        return SystemdHelper(self._svcs_all)


class YRequirementTypeSystemd(service_manager_common.ServiceManagerTypeBase):
    """
    Systemd requires type property. Provides support for defining checks on
    systemd resources.
    """
    override_keys = ['systemd']
    override_autoregister = True
    default_op = 'eq'

    def _check_service(self, svc, ops, started_after=None):
        """
        @param svc: SystemdService object of service we are checking.
        @param ops: list of operations to apply
        @param started_after: optional SystemdService object. If provided we
                                       will assert that svc was started after
                                       this service.
        """
        if started_after:
            a = svc.start_time
            b = started_after.start_time
            if not all([a, b]):
                log.debug("could not get start time for services %s and %s "
                          "so assuming started-after constraint is False",
                          svc.name, started_after.name)
                return False

            log.debug("%s started=%s, %s started=%s", svc.name,
                      a, started_after.name, b)
            if a < b:
                delta = b - a
            else:
                delta = a - b

            # Allow a small grace period to avoid false positives e.g.
            # on node boot when services are started all at once.
            grace = 120
            # In order for a service A to have been started after B it must
            # have been started more than GRACE seconds after B.
            if a > b:
                if delta >= timedelta(seconds=grace):
                    log.debug("svc %s started >= %ds of start of %s "
                              "(delta=%s)", svc.name, grace,
                              started_after.name, delta)
                else:
                    log.debug("svc %s started < %ds of start of %s "
                              "(delta=%s)", svc.name, grace,
                              started_after.name, delta)
                    return False
            else:
                log.debug("svc %s started before or same as %s "
                          "(delta=%s)", svc.name,
                          started_after.name, delta)
                return False

        return self.apply_ops(ops, opinput=svc.state)

    def _check_item_settings(self, svc_obj, settings, cache_info,
                             all_items):
        # pylint: disable=duplicate-code
        processes = None
        started_after_obj = None
        if isinstance(settings, str):
            state = settings
            ops = [[self.default_op, state]]
        else:
            processes = settings.get('processes')
            if processes:
                log.debug("checking systemd service processes: %s", processes)
                processes = settings.get('processes')

            op = settings.get('op', self.default_op)
            started_after = settings.get('started-after')
            started_after_obj = all_items.installed.get(started_after)
            if 'state' in settings:
                ops = [[op, settings.get('state')]]
            else:
                ops = []

        if processes and not all_items.processes_running(processes):
            log.debug("one or more systemd service processes not running "
                      "- %s", ', '.join(processes))
            return False

        cache_info[svc_obj.name]['ops'] = self.ops_to_str(ops)
        return self._check_service(svc_obj, ops,
                                   started_after=started_after_obj)

    @property
    def items_to_check(self):
        return SystemdServiceCheckItems(self.content)
