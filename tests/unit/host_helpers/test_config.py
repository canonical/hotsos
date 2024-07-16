import os

from hotsos.core.config import HotSOSConfig
from hotsos.core.host_helpers import config as host_config

from .. import utils

DUMMY_CONFIG = """
[a-section]
a-key = 1023
b-key = 10-23
c-key = 2-8,10-31
"""


class TestConfigHelper(utils.BaseTestCase):
    """ Unit tests for config helper """
    @utils.create_data_root({'test.conf': DUMMY_CONFIG})
    def test_iniconfig_base(self):
        conf = os.path.join(HotSOSConfig.data_root, 'test.conf')
        cfg = host_config.IniConfigBase(conf)
        self.assertTrue(cfg.exists)
        self.assertEqual(cfg.get('a-key'), '1023')
        self.assertEqual(cfg.get('a-key', section='a-section'), '1023')
        self.assertIsNone(cfg.get('a-key', section='missing-section'))
        self.assertEqual(cfg.get('a-key', expand_to_list=True), [1023])

        expanded = cfg.get('b-key', expand_to_list=True)
        self.assertEqual(expanded, list(range(10, 24)))
        self.assertEqual(cfg.squash_int_range(expanded), '10-23')

        expanded = cfg.get('c-key', expand_to_list=True)
        self.assertEqual(expanded, list(range(2, 9)) + list(range(10, 32)))
        self.assertEqual(cfg.squash_int_range(expanded), '2-8,10-31')

    @utils.create_data_root({'test.conf': DUMMY_CONFIG})
    def test_squash_int_range(self):
        self.assertEqual(host_config.ConfigBase.squash_int_range([]), '')
        expanded = list(range(2, 9))
        self.assertEqual(host_config.ConfigBase.squash_int_range(expanded),
                         '2-8')
        expanded = list(range(2, 9)) + list(range(10, 32))
        self.assertEqual(host_config.ConfigBase.squash_int_range(expanded),
                         '2-8,10-31')
        expanded = list(range(2, 9)) + [10] + list(range(12, 32))
        self.assertEqual(host_config.ConfigBase.squash_int_range(expanded),
                         '2-8,10,12-31')
