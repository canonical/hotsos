from hotsos.core.plugins.storage.bcache import BcacheChecks
from hotsos.core.plugintools import summary_entry


class BcacheSummary(BcacheChecks):
    """ Implementation of Bcache summary. """
    summary_part_index = 2

    @summary_entry('cachesets', 0)
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
