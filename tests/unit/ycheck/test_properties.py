import datetime
import os
import shutil
import tempfile
from functools import cached_property
from unittest import mock

import yaml
from hotsos.core.config import HotSOSConfig
from hotsos.core.host_helpers.config import IniConfigBase
from hotsos.core.issues.utils import IssuesStore
from hotsos.core.search import ExtraSearchConstraints
from hotsos.core.ycheck import scenarios
from hotsos.core.ycheck.engine import (
    YDefsSection,
    YDefsLoader,
)
from hotsos.core.ycheck.engine.properties.common import (
    YPropertyBase,
    PropertyCacheRefResolver,
)
from hotsos.core.ycheck.common import GlobalSearcher

from .. import utils

# It is fine for a test to access a protected member so allow it for all tests
# pylint: disable=protected-access


class TestProperty(YPropertyBase):
    """ Test property """

    @cached_property
    def myattr(self):
        return '123'

    @property
    def myotherattr(self):
        return '456'

    @property
    def always_true(self):
        return True

    @property
    def always_false(self):
        return False


class TestConfig(IniConfigBase):
    """ Test Config """


class FakeServiceObjectManager():
    """ Fake service manager. """
    def __init__(self, start_times):
        self._start_times = start_times

    def __call__(self, name, state, has_instances):
        return FakeService(name, state, has_instances,
                           start_time=self._start_times[name])


class FakeService():
    """ Fake service """
    def __init__(self, name, state, has_instances, start_time):
        self.name = name
        self.state = state
        self.start_time = start_time
        self.has_instances = has_instances


YAML_DEF_REQUIRES_BIN_SHORT = """
pluginX:
  groupA:
    requires:
      binary:
        handler: hotsos.core.plugins.juju.JujuBinaryInterface
        name: juju
"""


YAML_DEF_REQUIRES_BIN = """
pluginX:
  groupA:
    requires:
      binary:
        handler: hotsos.core.plugins.juju.JujuBinaryInterface
        juju:
          - min: '2.9'
            max: '3.0'
"""


YAML_DEF_REQUIRES_APT = """
pluginX:
  groupA:
    requires:
      apt:
        mypackage:
          - min: '3.0'
            max: '3.2'
          - min: '4.0'
            max: '4.2'
          - min: '5.0'
            max: '5.2'
        altpackage:
          - min: '3.0'
            max: '3.2'
          - min: '4.0'
            max: '4.2'
          - min: '5.0'
            max: '5.2'
"""

YAML_DEF_REQUIRES_PEBBLE_FAIL = """
pluginX:
  groupA:
    requires:
      pebble:
        foo:
          state: active
"""


YAML_DEF_REQUIRES_SYSTEMD_PASS_1 = """
pluginX:
  groupA:
    requires:
      systemd:
        ondemand: enabled
        nova-compute: enabled
"""


YAML_DEF_REQUIRES_SYSTEMD_STARTED_AFTER = """
pluginX:
  groupA:
    requires:
      systemd:
        openvswitch-switch:
          state: enabled
          started-after: neutron-openvswitch-agent
"""


YAML_DEF_REQUIRES_SYSTEMD_FAIL_1 = """
pluginX:
  groupA:
    requires:
      systemd:
        ondemand: enabled
        nova-compute: disabled
"""

YAML_DEF_REQUIRES_MAPPED = """
checks:
  is_exists_mapped:
    systemd: nova-compute
  is_exists_unmapped:
    requires:
      systemd: nova-compute
conclusions:
"""

YAML_DEF_REQUIRES_SYSTEMD_FAIL_2 = """
pluginX:
  groupA:
    requires:
      systemd:
        ondemand:
          state: enabled
        nova-compute:
          state: disabled
          op: eq
"""


YAML_DEF_REQUIRES_GROUPED = """
passdef1:
  requires:
    - path: sos_commands/networking
    - not:
        path: sos_commands/networking_foo
    - apt: python3.8
    - and:
        - apt:
            systemd:
              - min: '245.4-4ubuntu3.14'
                max: '245.4-4ubuntu3.15'
      or:
        - apt: nova-compute
      not:
        - apt: blah
passdef2:
  requires:
    and:
      - apt: systemd
    or:
      - apt: nova-compute
    not:
      - apt: blah
faildef1:
  requires:
    - path: sos_commands/networking_foo
    - and:
        - apt: doo
        - apt: daa
      or:
        - apt: nova-compute
      not:
        - and:
            - apt: 'blah'
        - and:
            - apt: nova-compute
faildef2:
  requires:
    - apt: python3.8
    - apt: python1.0
"""


class TempScenarioDefs():
    """ Context manager to load copies of scenario definitions into a temporary
    location. """
    def __init__(self):
        self.root = None
        self.path = None

    def __enter__(self):
        self.root = tempfile.mkdtemp()
        HotSOSConfig.plugin_yaml_defs = self.root
        self.path = os.path.join(self.root, 'scenarios',
                                 HotSOSConfig.plugin_name, 'test.yaml')
        os.makedirs(os.path.dirname(self.path))
        return self

    def __exit__(self, *args):
        shutil.rmtree(self.root)
        return False


class TestYamlRequiresTypeCache(utils.BaseTestCase):
    """ Tests requires type property caches. """

    @utils.create_data_root({'sos_commands/dpkg/dpkg_-l': 'ii foo 123 amd64'})
    def test_single_item(self):
        mydef = YDefsSection('mydef', yaml.safe_load("chk1:\n  apt: foo"))
        for entry in mydef.leaf_sections:
            self.assertTrue(entry.requires.result)
            expected = {'__PREVIOUSLY_CACHED_PROPERTY_TYPE':
                        'YRequirementTypeAPT',
                        'package': 'foo',
                        'passes': True,
                        'version': '123'}
            self.assertEqual(entry.requires.cache.data, expected)

    @utils.create_data_root({'sos_commands/dpkg/dpkg_-l':
                             'ii foo 123 amd64'})
    def test_grouped_items_first_true(self):
        """ If the first item evaluates to True we get that one. """
        scenario = """
        checks:
          c1:
            or:
              - apt: foo
              - apt: bar
        conclusions:
          c1:
            decision: c1
            raises:
              type: SystemWarning
              message: '{pkg}'
              format-dict:
                pkg: '@checks.c1.requires.package'
        """  # noqa
        with TempScenarioDefs() as tmpscenarios:
            with open(tmpscenarios.path, 'w', encoding='utf-8') as fd:
                fd.write(scenario)

            with GlobalSearcher() as searcher:
                scenarios.YScenarioChecker(searcher).run()

            issues = list(IssuesStore().load().values())[0]
            self.assertEqual(issues[0]['message'], 'foo')

    @utils.create_data_root({'sos_commands/dpkg/dpkg_-l':
                             'ii bar 123 amd64'})
    def test_grouped_items_last_true(self):
        """ If the last item evaluates to True we get that one. """
        scenario = """
        checks:
          c1:
            or:
              - apt: foo
              - apt: bar
        conclusions:
          c1:
            decision: c1
            raises:
              type: SystemWarning
              message: '{pkg}'
              format-dict:
                pkg: '@checks.c1.requires.package'
        """  # noqa
        with TempScenarioDefs() as tmpscenarios:
            with open(tmpscenarios.path, 'w', encoding='utf-8') as fd:
                fd.write(scenario)

            with GlobalSearcher() as searcher:
                scenarios.YScenarioChecker(searcher).run()

            issues = list(IssuesStore().load().values())[0]
            self.assertEqual(issues[0]['message'], 'bar')

    @utils.create_data_root({'sos_commands/dpkg/dpkg_-l':
                             'ii foo 123 amd64\nii bar 123 amd64'})
    def test_grouped_items_all_true(self):
        """ If all items evaluate to True we get the cache of the last one. """
        scenario = """
        checks:
          c1:
            or:
              - apt: foo
              - apt: bar
        conclusions:
          c1:
            decision: c1
            raises:
              type: SystemWarning
              message: '{pkg}'
              format-dict:
                pkg: '@checks.c1.requires.package'
        """  # noqa
        with TempScenarioDefs() as tmpscenarios:
            with open(tmpscenarios.path, 'w', encoding='utf-8') as fd:
                fd.write(scenario)

            with GlobalSearcher() as searcher:
                scenarios.YScenarioChecker(searcher).run()

            issues = list(IssuesStore().load().values())[0]
            self.assertEqual(issues[0]['message'], 'foo')

    @utils.create_data_root({'sos_commands/dpkg/dpkg_-l': ''})
    def test_grouped_items_all_false(self):
        """ If the all items evaluates to False nothing is copied. """
        scenario = """
        checks:
          c1:
            or:
              - apt: foo
              - apt: bar
        conclusions:
          c1:
            decision: c1
            raises:
              type: SystemWarning
              message: '{pkg}'
              format-dict:
                pkg: '@checks.c1.requires.package'
        """
        with TempScenarioDefs() as tmpscenarios:
            with open(tmpscenarios.path, 'w', encoding='utf-8') as fd:
                fd.write(scenario)

            with GlobalSearcher() as searcher:
                scenarios.YScenarioChecker(searcher).run()

            self.assertEqual(len(IssuesStore().load()), 0)

    @utils.create_data_root({'sos_commands/dpkg/dpkg_-l':
                             'ii foo 123 amd64\nii bar 123 amd64',
                             'sos_commands/snap/snap_list_--all':
                             'snapd 2.54.2 14549 latest/stable xxx'})
    def test_grouped_items_all_true_mixed_types_apt_first(self):
        """ If the all items evaluates to False nothing is copied. """
        scenario = """
        checks:
          c1:
            or:
              - apt: foo
              - apt: bar
              - snap: snapd
        conclusions:
          c1:
            decision: c1
            raises:
              type: SystemWarning
              message: '{pkg}'
              format-dict:
                pkg: '@checks.c1.requires.package'
        """
        with TempScenarioDefs() as tmpscenarios:
            with open(tmpscenarios.path, 'w', encoding='utf-8') as fd:
                fd.write(scenario)

            with GlobalSearcher() as searcher:
                scenarios.YScenarioChecker(searcher).run()

            issues = list(IssuesStore().load().values())[0]
            self.assertEqual(issues[0]['message'], 'foo')

    @utils.create_data_root({'sos_commands/dpkg/dpkg_-l':
                             'ii foo 123 amd64\nii bar 123 amd64',
                             'sos_commands/snap/snap_list_--all':
                             'snapd 2.54.2 14549 latest/stable xxx'})
    def test_grouped_items_all_true_mixed_types_snap_first(self):
        """ If the all items evaluates to False nothing is copied. """
        scenario = """
        checks:
          c1:
            or:
              - snap: snapd
              - apt: foo
              - apt: bar
        conclusions:
          c1:
            decision: c1
            raises:
              type: SystemWarning
              message: '{pkg}'
              format-dict:
                pkg: '@checks.c1.requires.package'
        """
        with TempScenarioDefs() as tmpscenarios:
            with open(tmpscenarios.path, 'w', encoding='utf-8') as fd:
                fd.write(scenario)

            with GlobalSearcher() as searcher:
                scenarios.YScenarioChecker(searcher).run()

            issues = list(IssuesStore().load().values())[0]
            self.assertEqual(issues[0]['message'], 'snapd')


class TestYamlProperties(utils.BaseTestCase):
    """ Miscellaneous tests for YAML properties. """

    def test_yaml_def_requires_grouped(self):
        mydef = YDefsSection('mydef',
                             yaml.safe_load(YAML_DEF_REQUIRES_GROUPED))
        tested = 0
        for entry in mydef.leaf_sections:
            if entry.name == 'passdef1':
                tested += 1
                self.assertTrue(entry.requires.result)
            elif entry.name == 'passdef2':
                tested += 1
                self.assertTrue(entry.requires.result)
            elif entry.name == 'faildef1':
                tested += 1
                self.assertFalse(entry.requires.result)
            elif entry.name == 'faildef2':
                tested += 1
                self.assertFalse(entry.requires.result)

        self.assertEqual(tested, 4)

    def test_get_datetime_from_result(self):
        result = mock.MagicMock()
        # The lambda is necessary here. _result is changing so
        # we can't bind result's get() function directly, otherwise
        # we'd have to update the side effect too.
        # pylint: disable-next= unnecessary-lambda
        result.get.side_effect = lambda idx: _result.get(idx)
        _result = {1: '2022-01-06', 2: '12:34:56.123'}

        ts = ExtraSearchConstraints._get_datetime_from_result(result)
        self.assertEqual(ts, datetime.datetime(2022, 1, 6, 12, 34, 56))

        _result = {1: '2022-01-06', 2: '12:34:56'}
        ts = ExtraSearchConstraints._get_datetime_from_result(result)
        self.assertEqual(ts, datetime.datetime(2022, 1, 6, 12, 34, 56))

        _result = {1: '2022-01-06'}
        ts = ExtraSearchConstraints._get_datetime_from_result(result)
        self.assertEqual(ts, datetime.datetime(2022, 1, 6, 0, 0))

        _result = {1: '2022-01-06 12:34:56.123'}
        ts = ExtraSearchConstraints._get_datetime_from_result(result)
        self.assertEqual(ts, datetime.datetime(2022, 1, 6, 12, 34, 56))

        _result = {1: '2022-01-06 12:34:56'}
        ts = ExtraSearchConstraints._get_datetime_from_result(result)
        self.assertEqual(ts, datetime.datetime(2022, 1, 6, 12, 34, 56))

        _result = {1: '2022-01-06'}
        ts = ExtraSearchConstraints._get_datetime_from_result(result)
        self.assertEqual(ts, datetime.datetime(2022, 1, 6, 0, 0))

        _result = {1: '2022-01-06', 2: 'foo'}
        with self.assertLogs(logger='hotsos', level='WARNING') as log:
            ts = ExtraSearchConstraints._get_datetime_from_result(result)
            self.assertIsNone(ts)
            self.assertEqual(len(log.output), 1)
            self.assertIn('failed to parse timestamp string', log.output[0])

        _result = {1: 'foo'}
        with self.assertLogs(logger='hotsos', level='WARNING') as log:
            ts = ExtraSearchConstraints._get_datetime_from_result(result)
            self.assertIsNone(ts)
            self.assertEqual(len(log.output), 1)
            self.assertIn('failed to parse timestamp string', log.output[0])

    @utils.create_data_root({'mytype/myplugin/defs.yaml':
                             'foo: bar\n',
                             'mytype/myplugin/mytype.yaml':
                             'requires:\n  property: foo\n'})
    def test_fs_override_inheritance(self):
        """
        When a directory is used to group definitions and overrides are
        provided in a <dirname>.yaml file, we need to make sure those overrides
        do not supersceded overrides of the same type used by definitions in
        the same directory.
        """
        HotSOSConfig.set(plugin_yaml_defs=HotSOSConfig.data_root,
                         plugin_name='myplugin')
        expected = {'mytype': {
                        'requires': {
                            'property': 'foo'}},
                    'defs': {'foo': 'bar'}}
        self.assertEqual(YDefsLoader('mytype').plugin_defs,
                         expected)

    @utils.create_data_root({'mytype/myplugin/defs.yaml':
                             'requires:\n  apt: apackage\n',
                             'mytype/myplugin/mytype.yaml':
                             'requires:\n  property: foo\n'})
    def test_fs_override_inheritance2(self):
        """
        When a directory is used to group definitions and overrides are
        provided in a <dirname>.yaml file, we need to make sure those overrides
        do not supersceded overrides of the same type used by definitions in
        the same directory.
        """
        HotSOSConfig.set(plugin_yaml_defs=HotSOSConfig.data_root,
                         plugin_name='myplugin')
        expected = {'mytype': {
                        'requires': {
                            'property': 'foo'}},
                    'defs': {
                        'requires': {
                            'apt': 'apackage'}}}
        self.assertEqual(YDefsLoader('mytype').plugin_defs,
                         expected)

    @mock.patch('hotsos.core.plugins.openstack.OpenStackChecks')
    def test_requires_grouped(self, mock_plugin):  # pylint: disable=R0915
        mock_plugin.return_value = mock.MagicMock()
        r1 = {'property':
              'hotsos.core.plugins.openstack.OpenStackChecks.r1'}
        r2 = {'property':
              'hotsos.core.plugins.openstack.OpenStackChecks.r2'}
        r3 = {'property':
              'hotsos.core.plugins.openstack.OpenStackChecks.r3'}
        requires = {'requires': [{'or': [r1, r2]}]}

        mock_plugin.return_value.r1 = False
        mock_plugin.return_value.r2 = False
        group = YDefsSection('test', requires)
        for leaf in group.leaf_sections:
            self.assertEqual(len(leaf.requires), 1)
            self.assertFalse(leaf.requires.result)

        self.assertFalse(group.requires.result)

        mock_plugin.return_value.r1 = True
        mock_plugin.return_value.r2 = False
        group = YDefsSection('test', requires)
        self.assertTrue(group.requires.result)

        mock_plugin.return_value.r1 = True
        mock_plugin.return_value.r2 = True
        group = YDefsSection('test', requires)
        self.assertTrue(group.requires.result)

        requires = {'requires': [{'and': [r1, r2]}]}

        mock_plugin.return_value.r1 = False
        mock_plugin.return_value.r2 = False
        group = YDefsSection('test', requires)
        self.assertFalse(group.requires.result)

        mock_plugin.return_value.r1 = True
        mock_plugin.return_value.r2 = False
        group = YDefsSection('test', requires)
        self.assertFalse(group.requires.result)

        mock_plugin.return_value.r1 = True
        mock_plugin.return_value.r2 = True
        group = YDefsSection('test', requires)
        self.assertTrue(group.requires.result)

        requires = {'requires': [{'and': [r1, r2],
                                  'or': [r1, r2]}]}

        mock_plugin.return_value.r1 = True
        mock_plugin.return_value.r2 = False
        group = YDefsSection('test', requires)
        self.assertFalse(group.requires.result)

        mock_plugin.return_value.r1 = True
        mock_plugin.return_value.r2 = True
        group = YDefsSection('test', requires)
        self.assertTrue(group.requires.result)

        requires = {'requires': [{'and': [r1, r2],
                                  'or': [r1, r2]}]}

        mock_plugin.return_value.r1 = True
        mock_plugin.return_value.r2 = False
        group = YDefsSection('test', requires)
        self.assertFalse(group.requires.result)

        requires = {'requires': [r1, {'and': [r3],
                                      'or': [r1, r2]}]}

        mock_plugin.return_value.r1 = True
        mock_plugin.return_value.r2 = False
        mock_plugin.return_value.r3 = True
        group = YDefsSection('test', requires)
        self.assertTrue(group.requires.result)

        requires = {'requires': [{'and': [r3],
                                  'or': [r1, r2]}]}

        mock_plugin.return_value.r1 = True
        mock_plugin.return_value.r2 = False
        mock_plugin.return_value.r3 = True
        group = YDefsSection('test', requires)
        self.assertTrue(group.requires.result)

        # same as prev test but with dict instead list
        requires = {'requires': {'and': [r3],
                                 'or': [r1, r2]}}

        mock_plugin.return_value.r1 = True
        mock_plugin.return_value.r2 = False
        mock_plugin.return_value.r3 = True
        group = YDefsSection('test', requires)
        self.assertTrue(group.requires.result)

    def test_yaml_def_requires_bin_installed_only(self):
        mydef = YDefsSection('mydef',
                             yaml.safe_load(YAML_DEF_REQUIRES_BIN_SHORT))
        for entry in mydef.leaf_sections:
            self.assertTrue(entry.requires.result)

    def test_yaml_def_requires_bin_true(self):
        mydef = YDefsSection('mydef',
                             yaml.safe_load(YAML_DEF_REQUIRES_BIN))
        for entry in mydef.leaf_sections:
            self.assertTrue(entry.requires.result)

    @mock.patch('hotsos.core.plugins.juju.JujuBinaryInterface')
    def test_yaml_def_requires_bin_false_lt(self, mock_bininterface):
        mock_bininterface.return_value = mock.MagicMock()
        mock_bininterface.return_value.is_installed.return_value = True
        mock_bininterface.return_value.get_version.return_value = 2.8
        mydef = YDefsSection('mydef',
                             yaml.safe_load(YAML_DEF_REQUIRES_BIN))
        for entry in mydef.leaf_sections:
            self.assertFalse(entry.requires.result)

    @mock.patch('hotsos.core.plugins.juju.JujuBinaryInterface')
    def test_yaml_def_requires_bin_false_gt(self, mock_bininterface):
        mock_bininterface.return_value = mock.MagicMock()
        mock_bininterface.return_value.is_installed.return_value = True
        mock_bininterface.return_value.get_version.return_value = 3.1
        mydef = YDefsSection('mydef',
                             yaml.safe_load(YAML_DEF_REQUIRES_BIN))
        for entry in mydef.leaf_sections:
            self.assertFalse(entry.requires.result)

    @mock.patch('hotsos.core.ycheck.engine.properties.requires.types.apt.'
                'APTPackageHelper')
    def test_yaml_def_requires_apt(self, mock_apt):
        tested = 0
        expected = {'2.0': False,
                    '3.0': True,
                    '3.1': True,
                    '4.0': True,
                    '5.0': True,
                    '5.2': True,
                    '5.3': False,
                    '6.0': False}
        mock_apt.return_value = mock.MagicMock()
        mock_apt.return_value.is_installed.return_value = True
        for ver, result in expected.items():
            mock_apt.return_value.get_version.return_value = ver
            mydef = YDefsSection('mydef',
                                 yaml.safe_load(YAML_DEF_REQUIRES_APT))
            for entry in mydef.leaf_sections:
                tested += 1
                self.assertEqual(entry.requires.result, result)

        self.assertEqual(tested, len(expected))

    def test_yaml_def_requires_pebble_fail(self):
        mydef = YDefsSection('mydef',
                             yaml.safe_load(YAML_DEF_REQUIRES_PEBBLE_FAIL))
        for entry in mydef.leaf_sections:
            self.assertFalse(entry.requires.result)

    def test_yaml_def_requires_systemd_pass(self):
        mydef = YDefsSection('mydef',
                             yaml.safe_load(YAML_DEF_REQUIRES_SYSTEMD_PASS_1))
        for entry in mydef.leaf_sections:
            self.assertTrue(entry.requires.result)

    def test_yaml_def_requires_systemd_fail(self):
        mydef = YDefsSection('mydef',
                             yaml.safe_load(YAML_DEF_REQUIRES_SYSTEMD_FAIL_1))
        for entry in mydef.leaf_sections:
            self.assertFalse(entry.requires.result)

        mydef = YDefsSection('mydef',
                             yaml.safe_load(YAML_DEF_REQUIRES_SYSTEMD_FAIL_2))
        for entry in mydef.leaf_sections:
            self.assertFalse(entry.requires.result)

    def test_yaml_def_requires_systemd_started_after_pass(self):
        current = datetime.datetime.now()
        with mock.patch('hotsos.core.host_helpers.systemd.SystemdService',
                        FakeServiceObjectManager({
                            'neutron-openvswitch-agent':
                                current,
                            'openvswitch-switch':
                                current + datetime.timedelta(seconds=120)})):
            content = yaml.safe_load(YAML_DEF_REQUIRES_SYSTEMD_STARTED_AFTER)
            mydef = YDefsSection('mydef', content)
            for entry in mydef.leaf_sections:
                self.assertTrue(entry.requires.result)

    def test_yaml_def_requires_systemd_started_after_fail(self):
        current = datetime.datetime.now()
        with mock.patch('hotsos.core.host_helpers.systemd.SystemdService',
                        FakeServiceObjectManager({'neutron-openvswitch-agent':
                                                  current,
                                                  'openvswitch-switch':
                                                  current})):
            content = yaml.safe_load(YAML_DEF_REQUIRES_SYSTEMD_STARTED_AFTER)
            mydef = YDefsSection('mydef', content)
            for entry in mydef.leaf_sections:
                self.assertFalse(entry.requires.result)

        with mock.patch('hotsos.core.host_helpers.systemd.SystemdService',
                        FakeServiceObjectManager({
                            'neutron-openvswitch-agent': current,
                            'openvswitch-switch':
                                current + datetime.timedelta(seconds=119)})):
            content = yaml.safe_load(YAML_DEF_REQUIRES_SYSTEMD_STARTED_AFTER)
            mydef = YDefsSection('mydef', content)
            for entry in mydef.leaf_sections:
                self.assertFalse(entry.requires.result)

    def test_cache_resolver(self):
        self.assertFalse(PropertyCacheRefResolver.is_valid_cache_ref('foo'))
        with self.assertLogs(logger='hotsos', level='WARNING') as log:
            for test in [('foo', 'first', 'foo'),
                         (['foo', 'second'], 'first', 'foo'),
                         (['1', '2'], 'comma_join', '1, 2'),
                         (['1', '2', '1'], 'unique_comma_join', '1, 2'),
                         ({'1': 'foo', '2': 'bar', '3': 'blah'},
                          'comma_join', '1, 2, 3'),
                         ({'1': 'foo', '2': 'bar', '3': 'blah'},
                          'len', 3)]:
                out = PropertyCacheRefResolver.apply_renderer(test[0], test[1])
                self.assertEqual(out, test[2])
                # If input == output, log.warning() will have been called
                if test[0] == test[2]:
                    self.assertEqual(len(log.output), 1)
                    self.assertIn('attempted to apply', log.output[0])
