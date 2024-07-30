from hotsos.core.log import log
from hotsos.core.host_helpers import PebbleHelper
from hotsos.core.ycheck.engine.properties.requires import ServiceCheckItemsBase
from hotsos.core.ycheck.engine.properties.requires.types import (
    service_manager_common
)


class PebbleServiceCheckItems(ServiceCheckItemsBase):
    """
    Implementation for check items on pebble resource properties.
    """
    @property
    def _svcs_info(self):
        return PebbleHelper(self._svcs_all)


class YRequirementTypePebble(service_manager_common.ServiceManagerTypeBase):
    """
    Pebble requires type property. Provides support for defining checks on
    pebble service manager resources.
    """
    override_keys = ['pebble']
    override_autoregister = True
    default_op = 'eq'

    def _check_item_settings(self, svc_obj, settings, cache_info,
                             all_items):
        processes = None
        if isinstance(settings, str):
            state = settings
            ops = [[self.default_op, state]]
        else:
            processes = settings.get('processes')
            if processes:
                log.debug("checking systemd service processes: %s", processes)

            op = settings.get('op', self.default_op)
            if 'state' in settings:
                ops = [[op, settings.get('state')]]
            else:
                ops = []

        if processes and not all_items.processes_running(processes):
            log.debug("one or more pebble service processes not running "
                      "- %s", ', '.join(processes))
            return False

        cache_info[svc_obj.name]['ops'] = self.ops_to_str(ops)
        return self.apply_ops(ops, opinput=svc_obj.state)

    @property
    def items_to_check(self):
        return PebbleServiceCheckItems(self.content)
