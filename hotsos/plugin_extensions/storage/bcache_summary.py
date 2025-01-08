from hotsos.core.plugins.storage.bcache import BcacheChecks
from hotsos.core.plugintools import (
    summary_entry,
    get_min_available_entry_index,
)


class BcacheSummary(BcacheChecks):
    """ Implementation of Bcache summary. """
    summary_part_index = 2

    # REMINDER: Common entries are implemented in
    #           plugintools.ApplicationSummaryBase. Only customisations are
    #           implemented here. See
    #           plugintools.get_min_available_entry_index() for an explanation
    #           on how entry indices are managed.

    @summary_entry('cachesets', get_min_available_entry_index())
    def summary_cachesets(self):
        _state = {}
        for cset in self.cachesets:
            _cset = {'cache_available_percent':
                     int(cset.cache_available_percent), 'bdevs': {}}
            for bdev in cset.bdevs:
                _cset['bdevs'][bdev.name] = {'dev': bdev.dev,
                                             'backing_dev':
                                             bdev.backing_dev_name}
                if bdev.dev_to_dname:
                    _cset['bdevs'][bdev.name]['dname'] = bdev.dev_to_dname

            _state[cset.uuid] = _cset

        return _state
