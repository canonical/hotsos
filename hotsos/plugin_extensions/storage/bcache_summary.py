from hotsos.core.plugins.storage.bcache import BcacheChecks
from hotsos.core.plugintools import (
    summary_entry,
    get_min_available_entry_index,
)


class BcacheSummary(BcacheChecks):
    """ Implementation of Bcache summary. """
    summary_part_index = 2

    # REMINDER: common entries are implemented in the SummaryBase base class
    #           and only application plugin specific customisations are
    #           implemented here. We use the get_min_available_entry_index() to
    #           ensure that additional entries don't clobber existing ones but
    #           conversely can also replace them by re-using their indices.

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
