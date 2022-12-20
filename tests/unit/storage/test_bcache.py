from .. import utils

from hotsos.core.config import HotSOSConfig
from hotsos.core.plugins.storage import bcache as bcache_core
from hotsos.plugin_extensions.storage import bcache_summary


class BCacheTestsBase(utils.BaseTestCase):

    def setUp(self):
        super().setUp()
        HotSOSConfig.plugin_name = 'storage'


class TestBcacheBase(BCacheTestsBase):

    def test_bcache_enabled(self):
        b = bcache_core.BcacheBase()
        self.assertTrue(b.bcache_enabled)

    def test_get_cacheset_bdevs(self):
        b = bcache_core.BcacheBase()
        result = sorted([b.name for b in b.cachesets[0].bdevs])
        self.assertEqual(result, ['bdev0', 'bdev1'])

    def test_get_cachesets(self):
        b = bcache_core.BcacheBase()
        expected = [{'cache_available_percent': 99,
                     'uuid': 'd7696818-1be9-4dea-9991-de95e24d7256'}]
        actual = [{'uuid': c.uuid,
                   'cache_available_percent': int(c.cache_available_percent)}
                  for c in b.cachesets]
        self.assertEqual(actual, expected)

    def test_udev_bcache_devs(self):
        b = bcache_core.BcacheBase()
        expected = [{'by-uuid': '88244ad9-372d-427e-9d82-c411c73d900a',
                     'name': 'bcache0'},
                    {'by-uuid': 'c3332949-19ba-40f7-91b6-48ee86157980',
                     'name': 'bcache1'}]

        self.assertEqual(b.udev_bcache_devs, expected)

    def test_is_bcache_device(self):
        b = bcache_core.BcacheBase()
        self.assertTrue(b.is_bcache_device('bcache0'))
        self.assertTrue(b.is_bcache_device('/dev/bcache0'))
        self.assertTrue(b.is_bcache_device('/dev/mapper/crypt-88244ad9-372d-'
                                           '427e-9d82-c411c73d900a'))


class TestBCacheSummary(BCacheTestsBase):

    def test_get_cacheset_info(self):
        cachesets = {'d7696818-1be9-4dea-9991-de95e24d7256': {
                       'cache_available_percent': 99,
                       'bdevs': {
                           'bdev1': {
                               'dev': 'bcache1',
                               'backing_dev': 'vdc',
                               'dname': 'bcache0'},
                           'bdev0': {
                               'dev': 'bcache0',
                               'backing_dev': 'vdd',
                               'dname': 'bcache1'}}}}

        inst = bcache_summary.BcacheSummary()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual['cachesets'], cachesets)

    def test_resolve_bdev_from_dev(self):
        inst = bcache_summary.BcacheSummary()
        devpath = '/dev/mapper/crypt-88244ad9-372d-427e-9d82-c411c73d900a'
        bdev = inst.resolve_bdev_from_dev(devpath)
        self.assertEqual(bdev.backing_dev_name, 'vdd')


@utils.load_templated_tests('scenarios/storage/bcache')
class TestBCacheScenarios(BCacheTestsBase):
    """
    Scenario tests can be written using YAML templates that are auto-loaded
    into this test runner. This is the recommended way to write tests for
    scenarios. It is however still possible to write the tests in Python if
    required. See defs/tests/README.md for more info.
    """
