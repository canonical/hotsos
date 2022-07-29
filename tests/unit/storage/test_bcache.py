import os
import tempfile

from unittest import mock

from .. import utils

from hotsos.core.issues import IssuesManager
from hotsos.core.config import setup_config
from hotsos.core.ycheck.scenarios import YScenarioChecker
from hotsos.core.plugins.storage import bcache as bcache_core
from hotsos.plugin_extensions.storage import bcache_summary


class StorageBCacheTestsBase(utils.BaseTestCase):

    def setup_bcachefs(self, path, bdev_error=False, cacheset_error=False):
        cset = os.path.join(path, 'sys/fs/bcache/1234')
        os.makedirs(cset)
        for cfg, val in {'congested_read_threshold_us': '0',
                         'congested_write_threshold_us': '0'}.items():
            with open(os.path.join(cset, cfg), 'w') as fd:
                if cacheset_error:
                    val = '100'

                fd.write(val)

        for cfg, val in {'cache_available_percent': '34'}.items():
            if cacheset_error:
                if cfg == 'cache_available_percent':
                    # i.e. >= 33 for lp1900438 check
                    val = '33'

            with open(os.path.join(cset, cfg), 'w') as fd:
                fd.write(val)

        bdev = os.path.join(cset, 'bdev1')
        os.makedirs(bdev)
        for cfg, val in {'sequential_cutoff': '0.0k',
                         'cache_mode':
                         'writethrough [writeback] writearound none',
                         'writeback_percent': '10'}.items():
            if bdev_error:
                if cfg == 'writeback_percent':
                    val = '1'

            with open(os.path.join(bdev, cfg), 'w') as fd:
                fd.write(val)

    def setUp(self):
        super().setUp()
        setup_config(PLUGIN_NAME='storage', MACHINE_READABLE=True)


class TestBcacheBase(StorageBCacheTestsBase):

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


class TestStorageBCache(StorageBCacheTestsBase):

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


class TestBCacheScenarioChecks(StorageBCacheTestsBase):

    @mock.patch('hotsos.core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter('cacheset.yaml'))
    def test_cacheset(self):
        with tempfile.TemporaryDirectory() as dtmp:
            self.setup_bcachefs(dtmp, cacheset_error=True)
            setup_config(DATA_ROOT=dtmp)
            YScenarioChecker()()
            bug_msg = (
                'bcache cache_available_percent is 33 (i.e. approx. 30%) '
                'which implies this node could be suffering from bug LP '
                '1900438 - please check.')
            issue_msg = (
                'bcache cacheset config congested_write_threshold_us '
                'expected to be eq 0 but actual=100.')
            issues = list(IssuesManager().load_issues().values())[0]
            self.assertEqual([issue['desc'] for issue in issues], [issue_msg])
            bugs = list(IssuesManager().load_bugs().values())[0]
            self.assertEqual([issue['desc'] for issue in bugs], [bug_msg])

    @mock.patch('hotsos.core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter('bdev.yaml'))
    def test_bdev(self):
        with tempfile.TemporaryDirectory() as dtmp:
            self.setup_bcachefs(dtmp, bdev_error=True)
            setup_config(DATA_ROOT=dtmp)
            YScenarioChecker()()
            msg = ('bcache config writeback_percent expected to be ge '
                   '10 but actual=1.')
            issues = list(IssuesManager().load_issues().values())[0]
            self.assertEqual([issue['desc'] for issue in issues], [msg])
