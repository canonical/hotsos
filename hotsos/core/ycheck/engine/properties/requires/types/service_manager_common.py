import abc

from hotsos.core.log import log
from hotsos.core.ycheck.engine.properties.requires import (
    intercept_exception,
    YRequirementTypeBase,
)


class ServiceManagerTypeBase(YRequirementTypeBase):
    """
    Base class for implementations for service manager requirement types such
    as systemd, pebble etc.
    """
    default_op = 'eq'

    @property
    @abc.abstractmethod
    def items_to_check(self):
        """ Return check items we want to iterate over until we find an error.

        The implementing class should have an accompanying implementation of
        ServiceCheckItemsBase and return that as an object here.
        """

    @property
    @intercept_exception
    def _result(self):
        cache_info = {}
        _result = True

        items = self.items_to_check
        if not items.not_installed:
            for svc, settings in items:
                svc_obj = items.installed[svc]
                cache_info[svc] = {'actual': svc_obj.state}
                if settings is None:
                    continue

                _result = self._check_item_settings(svc_obj, settings,
                                                    cache_info, items)
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
        svcs = [f"{svc}={settings}" for svc, settings in items]
        log.debug('requirement check: %s (result=%s)',
                  ', '.join(svcs), _result)
        return _result
