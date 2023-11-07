from hotsos.core.plugins.storage.bcache import BcacheChecksBase


class BcacheSummary(BcacheChecksBase):
    summary_part_index = 2

    def __0_summary_cachesets(self):
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
