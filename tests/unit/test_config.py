from . import utils

from hotsos.core.config import (
    ConfigOpt,
    ConfigOptGroupBase,
    HotSOSConfig
    )


class TestOptGroup(ConfigOptGroupBase):

    def __init__(self):
        super().__init__()
        self.add(ConfigOpt('opt1', 'its opt one', None))
        self.add(ConfigOpt('opt2', 'its opt two', True))
        self.add(ConfigOpt('opt3', 'its opt three', False))

    @property
    def name(self):
        return 'testopts'


class TestHotSOSConfig(utils.BaseTestCase):

    def test_optgroup(self):
        tog = TestOptGroup()
        self.assertEqual(len(tog), 3)
        self.assertEqual(tog.name, 'testopts')
        self.assertEqual(tog, {'opt1': None, 'opt2': True, 'opt3': False})

    def test_restore_defaults(self):
        path = 'tests/unit/fake_data_root/openstack'
        try:
            self.assertTrue(HotSOSConfig.data_root.endswith(path))
            self.assertTrue(HotSOSConfig.use_all_logs)
            self.assertEqual(HotSOSConfig.max_logrotate_depth, 7)

            HotSOSConfig.set(data_root='foo', use_all_logs=False,
                             max_logrotate_depth=1)
            self.assertEqual(HotSOSConfig.data_root, 'foo')
            self.assertFalse(HotSOSConfig.use_all_logs)
            self.assertEqual(HotSOSConfig.max_logrotate_depth, 1)
        finally:
            HotSOSConfig.reset()
            # check global defaults
            self.assertFalse(HotSOSConfig.use_all_logs)
            self.assertEqual(HotSOSConfig.max_logrotate_depth, 7)
            super().setUp()
            # check unit test defaults
            self.assertTrue(HotSOSConfig.data_root.endswith(path))
            self.assertTrue(HotSOSConfig.use_all_logs)
