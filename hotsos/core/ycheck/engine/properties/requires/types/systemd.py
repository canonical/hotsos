from datetime import timedelta

from hotsos.core.log import log
from hotsos.core.host_helpers import SystemdHelper
from hotsos.core.ycheck.engine.properties.requires import YRequirementTypeBase


class YRequirementTypeSystemd(YRequirementTypeBase):
    """ Provides logic to perform checks on systemd resources. """

    @classmethod
    def _override_keys(cls):
        return ['systemd']

    def check_service(self, svc, ops, started_after_svc_obj=None):
        if started_after_svc_obj:
            a = svc.start_time
            b = started_after_svc_obj.start_time
            if a and b:
                log.debug("%s started=%s, %s started=%s", svc.name,
                          a, started_after_svc_obj.name, b)
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
                                  started_after_svc_obj.name, delta)
                    else:
                        log.debug("svc %s started < %ds of start of %s "
                                  "(delta=%s)", svc.name, grace,
                                  started_after_svc_obj.name, delta)
                        return False
                else:
                    log.debug("svc %s started before or same as %s "
                              "(delta=%s)", svc.name,
                              started_after_svc_obj.name, delta)
                    return False

        return self.apply_ops(ops, input=svc.state)

    @property
    def _result(self):
        default_op = 'eq'
        _result = True

        if type(self.content) != dict:
            service_checks = {self.content: None}
        else:
            service_checks = self.content

        services_under_test = list(service_checks.keys())
        for settings in service_checks.values():
            if type(settings) == dict and 'started-after' in settings:
                services_under_test.append(settings['started-after'])

        svcinfo = SystemdHelper(services_under_test).services
        cache_info = {}
        for svc, settings in service_checks.items():
            if svc not in svcinfo:
                _result = False
                # bail on first fail
                break

            svc_obj = svcinfo[svc]
            cache_info[svc] = {'actual': svc_obj.state}

            # The service criteria can be defined in three different ways;
            # string svc name, dict of svc name: state and dict of svc name:
            # dict of settings.
            if settings is None:
                continue

            started_after_svc_obj = None
            if type(settings) == str:
                state = settings
                ops = [[default_op, state]]
            else:
                op = settings.get('op', default_op)
                started_after = settings.get('started-after')
                if started_after:
                    started_after_svc_obj = svcinfo.get(started_after)
                    if not started_after_svc_obj:
                        # if a started-after service has been provided but
                        # that service does not exist then we return False.
                        _result = False
                        continue

                if 'state' in settings:
                    ops = [[op, settings.get('state')]]
                else:
                    ops = []

            cache_info[svc]['ops'] = self.ops_to_str(ops)
            _result = self.check_service(
                                   svc_obj, ops,
                                   started_after_svc_obj=started_after_svc_obj)
            if not _result:
                # bail on first fail
                break

        self.cache.set('services', ', '.join(cache_info))
        svcs = ["{}={}".format(svc, state)
                for svc, state in service_checks.items()]
        log.debug('requirement check: %s (result=%s)',
                  ', '.join(svcs), _result)
        return _result
