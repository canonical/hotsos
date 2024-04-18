from hotsos.core.log import log
from hotsos.core.host_helpers import PebbleHelper
from hotsos.core.ycheck.engine.properties.requires import (
    intercept_exception,
    ServiceCheckItemsBase,
    YRequirementTypeBase,
)


class PebbleServiceCheckItems(ServiceCheckItemsBase):

    @property
    def _svcs_info(self):
        return PebbleHelper(self._svcs_all)


class YRequirementTypePebble(YRequirementTypeBase):
    """ Provides logic to perform checks on pebble resources. """
    _override_keys = ['pebble']
    _overrride_autoregister = True

    @property
    @intercept_exception
    def _result(self):
        cache_info = {}
        default_op = 'eq'
        _result = True

        items = PebbleServiceCheckItems(self.content)
        if not items.not_installed:
            for svc, settings in items:
                svc_obj = items.installed[svc]
                cache_info[svc] = {'actual': svc_obj.state}
                if settings is None:
                    continue

                processes = None
                if isinstance(settings, str):
                    state = settings
                    ops = [[default_op, state]]
                else:
                    processes = settings.get('processes')
                    if processes:
                        log.debug("checking service processes: %s", processes)

                    op = settings.get('op', default_op)
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
                    _result = self.self.apply_ops(ops, input=svc_obj.state)

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
