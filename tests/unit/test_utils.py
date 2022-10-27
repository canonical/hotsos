from . import utils

from hotsos.core import utils as core_utils


class TestUtils(utils.BaseTestCase):

    def test_sample_set_regressions(self):
        samples = [1, 2, 3]
        self.assertEqual(core_utils.sample_set_regressions(samples), 0)
        samples = [1, 2, 3, 1]
        self.assertEqual(core_utils.sample_set_regressions(samples), 1)
        samples = [1, 2, 3, 4, 1, 3]
        self.assertEqual(core_utils.sample_set_regressions(samples), 1)
        samples = [1, 2, 3, 4, 1, 4, 1]
        self.assertEqual(core_utils.sample_set_regressions(samples), 2)
        samples = [1, 2, 1, 2, 1, 5, 1]
        self.assertEqual(core_utils.sample_set_regressions(samples), 3)
        samples = [1, 1, 1, 2, 2, 2]
        self.assertEqual(core_utils.sample_set_regressions(samples), 0)
        samples = [1, 1, 1, 2, 2, 2, 1]
        self.assertEqual(core_utils.sample_set_regressions(samples), 1)

        samples = [1, 1, 1]
        self.assertEqual(core_utils.sample_set_regressions(samples,
                                                           ascending=False), 0)
        samples = [2, 1, 1]
        self.assertEqual(core_utils.sample_set_regressions(samples,
                                                           ascending=False), 0)
        samples = [2, 1, 2]
        self.assertEqual(core_utils.sample_set_regressions(samples,
                                                           ascending=False), 1)
        samples = [100, 99, 98, 100, 60, 60]
        self.assertEqual(core_utils.sample_set_regressions(samples,
                                                           ascending=False), 1)

    def test_mpcache(self):
        c = core_utils.MPCache('test', 'cacheroot')
        self.assertEqual(c.get('key1'), None)
        c.set('key1', 'value1')
        self.assertEqual(c.get('key1'), 'value1')
        c.set('key1', 'value2')
        self.assertEqual(c.get('key1'), 'value2')
        self.assertEqual(c.get('key2'), None)
        c.set('key2', {'abcd': 1234})
        self.assertEqual(c.get('key2'), {'abcd': 1234})
