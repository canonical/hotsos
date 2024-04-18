from datetime import timedelta

from hotsos.core.host_helpers import SystemdHelper
from hotsos.core.log import log
from hotsos.core.ycheck.engine.properties.requires import (
    intercept_exception,
    ServiceCheckItemsBase,
    YRequirementTypeBase,
)


class SystemdServiceCheckItems(ServiceCheckItemsBase):

    @property
    def _svcs_info(self):
        return SystemdHelper(self._svcs_all)


class YRequirementTypeSystemd(YRequirementTypeBase):
    """ Provides logic to perform checks on systemd resources. """
    _override_keys = ['systemd']
    _overrride_autoregister = True

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

    @property
    @intercept_exception
    def _result(self):
        cache_info = {}
        default_op = 'eq'
        _result = True

        items = SystemdServiceCheckItems(self.content)
        if not items.not_installed:
            for svc, settings in items:
                svc_obj = items.installed[svc]
                cache_info[svc] = {'actual': svc_obj.state}
                if settings is None:
                    continue

                processes = None
                started_after_obj = None
                if isinstance(settings, str):
                    state = settings
                    ops = [[default_op, state]]
                else:
                    processes = settings.get('processes')
                    if processes:
                        log.debug("checking service processes: %s", processes)

                    op = settings.get('op', default_op)
                    started_after = settings.get('started-after')
                    started_after_obj = items.installed.get(started_after)
                    if 'state' in settings:
                        ops = [[op, settings.get('state')]]
                    else:
                        ops = []

                if processes and not items.processes_running(processes):
                    log.debug("one or more processes not running "
                              "- %s", ', '.join(processes))
                    _result = False
                else:
                    cache_info[svc]['ops'] = self.ops_to_str(ops)
                    _result = self._check_service(
                                               svc_obj, ops,
                                               started_after=started_after_obj)
                if not _result:
                    # bail on first fail
                    break
        else:
            log.debug("one or more services not installed so returning False "
                      "- %s", ', '.join(items.not_installed))
            # bail on first fail i.e. if any not installed
            _result = False

        # this will represent what we have actually checked
        self.cache.set('services', ', '.join(cache_info))
        svcs = ["{}={}".format(svc, settings) for svc, settings in items]
        log.debug('requirement check: %s (result=%s)',
                  ', '.join(svcs), _result)
        return _result
