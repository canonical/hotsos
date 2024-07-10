from hotsos.core.config import (
    ConfigOpt,
    ConfigOptGroupBase,
    HotSOSConfig,
    RegisteredOpts,
)

from . import utils


class TestOptGroup(ConfigOptGroupBase):
    """ Unit tests for ConfigOpt groups """
    def __init__(self):
        super().__init__()
        self.add(ConfigOpt('opt1', 'its opt one', None, str))
        self.add(ConfigOpt('opt2', 'its opt two', True, bool))
        self.add(ConfigOpt('opt3', 'its opt three', False, bool))

    @property
    def name(self):
        return 'testopts'


class TestHotSOSConfig(utils.BaseTestCase):
    """ Unit tests for HotSOSConfig """
    def test_optgroup(self):
        tog = TestOptGroup()
        self.assertEqual(len(tog), 3)
        self.assertEqual(tog.name, 'testopts')
        self.assertEqual(tog, {'opt1': None, 'opt2': True, 'opt3': False})

    def test_optgroup_conflict_dup(self):

        class AltOptGroup(ConfigOptGroupBase):
            """ dummy alt group """
            def __init__(self):
                super().__init__()
                self.add(ConfigOpt('opt1', 'its opt one', None, str))

            @property
            def name(self):
                return 'altopts'

        with self.assertRaises(Exception):
            RegisteredOpts(TestOptGroup, AltOptGroup)

    def test_optgroup_conflict_case(self):

        class AltOptGroup(ConfigOptGroupBase):
            """ dummy alt group """
            def __init__(self):
                super().__init__()
                self.add(ConfigOpt('Opt1', 'its opt one', None, str))

            @property
            def name(self):
                return 'altopts'

        with self.assertRaises(Exception):
            RegisteredOpts(TestOptGroup, AltOptGroup)

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
