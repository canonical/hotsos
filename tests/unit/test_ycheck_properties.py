import datetime
import os
import shutil
import tempfile
from functools import cached_property
from unittest import mock

import yaml
from hotsos.core.config import HotSOSConfig
from hotsos.core.host_helpers import (
    DPKGVersion
)
from hotsos.core.host_helpers.config import SectionalConfigBase
from hotsos.core.issues.utils import IssuesStore
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
from hotsos.core.ycheck.engine.properties.search import YPropertySearch
from hotsos.core.ycheck.engine.properties.requires.types import (
    apt,
    binary,
    snap,
)
from hotsos.core.plugins import juju

from . import utils


class TestProperty(YPropertyBase):

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


class TestConfig(SectionalConfigBase):
    pass


class FakeServiceObjectManager(object):

    def __init__(self, start_times):
        self._start_times = start_times

    def __call__(self, name, state, has_instances):
        return FakeServiceObject(name, state, has_instances,
                                 start_time=self._start_times[name])


class FakeServiceObject(object):

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

DPKG_L = """
ii  openssh-server                       1:8.2p1-4ubuntu0.4                                   amd64        secure shell (SSH) server, for secure access from remote machines
"""  # noqa


class TempScenarioDefs(object):

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
            with open(tmpscenarios.path, 'w') as fd:
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
            with open(tmpscenarios.path, 'w') as fd:
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
            with open(tmpscenarios.path, 'w') as fd:
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
            with open(tmpscenarios.path, 'w') as fd:
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
            with open(tmpscenarios.path, 'w') as fd:
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
            with open(tmpscenarios.path, 'w') as fd:
                fd.write(scenario)

            with GlobalSearcher() as searcher:
                scenarios.YScenarioChecker(searcher).run()

            issues = list(IssuesStore().load().values())[0]
            self.assertEqual(issues[0]['message'], 'snapd')


class TestYamlRequiresTypeBinary(utils.BaseTestCase):

    def test_binary_check_comparison(self):
        items = binary.BinCheckItems({'juju': [{'min': '3.0', 'max': '3.2'}]},
                                     bin_handler=juju.JujuBinaryInterface)
        self.assertEqual(items.installed, ['juju'])
        self.assertEqual(items.not_installed, set())
        _bin, versions = list(items)[0]
        version = items.packaging_helper.get_version(_bin)
        self.assertFalse(DPKGVersion.is_version_within_ranges(version,
                                                              versions))

        items = binary.BinCheckItems({'juju': [{'min': '2.9', 'max': '3.2'}]},
                                     bin_handler=juju.JujuBinaryInterface)
        self.assertEqual(items.installed, ['juju'])
        self.assertEqual(items.not_installed, set())
        _bin, versions = list(items)[0]
        version = items.packaging_helper.get_version(_bin)
        self.assertTrue(DPKGVersion.is_version_within_ranges(version,
                                                             versions))

        items = binary.BinCheckItems({'juju': [{'min': '2.9.2',
                                                'max': '2.9.22'}]},
                                     bin_handler=juju.JujuBinaryInterface)
        self.assertEqual(items.installed, ['juju'])
        self.assertEqual(items.not_installed, set())
        _bin, versions = list(items)[0]
        version = items.packaging_helper.get_version(_bin)
        self.assertTrue(DPKGVersion.is_version_within_ranges(version,
                                                             versions))


class TestYamlRequiresTypeAPT(utils.BaseTestCase):

    @staticmethod
    def load_apt_requires(yaml_content):
        return apt.YRequirementTypeAPT(
            "requires",
            "apt",
            yaml.safe_load(yaml_content),
            "requires.apt")

    @utils.create_data_root({'sos_commands/dpkg/dpkg_-l': DPKG_L})
    def test_apt_no_criteria(self):
        content = r"""
        openssh-server:
        """
        self.assertTrue(self.load_apt_requires(content).result)

    @utils.create_data_root({'sos_commands/dpkg/dpkg_-l': DPKG_L})
    def test_apt_no_criteria_alt_form(self):
        content = r"""
        - openssh-server
        """
        self.assertTrue(self.load_apt_requires(content).result)

    @utils.create_data_root({'sos_commands/dpkg/dpkg_-l': DPKG_L})
    def test_apt_no_criteria_name_mismatch(self):
        # We expect test to fail because no such package exist.
        content = r"""
        openssh-serverx:
        """
        self.assertFalse(self.load_apt_requires(content).result)

    @utils.create_data_root({'sos_commands/dpkg/dpkg_-l': DPKG_L})
    def test_apt_name_mismatch(self):
        content = r"""
        openssh-serverx:
            - eq: '1:8.2p1-4ubuntu0.4'
        """
        self.assertFalse(self.load_apt_requires(content).result)

    @utils.create_data_root({'sos_commands/dpkg/dpkg_-l': DPKG_L})
    def test_apt_gt_single_true(self):
        content = r"""
        openssh-server:
            - gt: '1:8.2'
        """
        self.assertTrue(self.load_apt_requires(content).result)

    @utils.create_data_root({'sos_commands/dpkg/dpkg_-l': DPKG_L})
    def test_apt_gt_single_false(self):
        content = r"""
        openssh-server:
            - gt: '1:8.2p1-4ubuntu0.4'
        """
        self.assertFalse(self.load_apt_requires(content).result)

    @utils.create_data_root({'sos_commands/dpkg/dpkg_-l': DPKG_L})
    def test_apt_ge_single_true(self):
        content = r"""
        openssh-server:
            - ge: '1:8.2'
        """
        self.assertTrue(self.load_apt_requires(content).result)

    @utils.create_data_root({'sos_commands/dpkg/dpkg_-l': DPKG_L})
    def test_apt_ge_single_false(self):
        content = r"""
        openssh-server:
            - ge: '1:8.2p1-4ubuntu0.5'
        """
        self.assertFalse(self.load_apt_requires(content).result)

    @utils.create_data_root({'sos_commands/dpkg/dpkg_-l': DPKG_L})
    def test_apt_lt_single_true(self):
        content = r"""
        openssh-server:
            - lt: '1:8.2p1-4ubuntu0.5'
        """
        self.assertTrue(self.load_apt_requires(content).result)

    @utils.create_data_root({'sos_commands/dpkg/dpkg_-l': DPKG_L})
    def test_apt_lt_single_false(self):
        content = r"""
        openssh-server:
            - lt: '1:8.2p1-4ubuntu0.3'
        """
        self.assertFalse(self.load_apt_requires(content).result)

    @utils.create_data_root({'sos_commands/dpkg/dpkg_-l': DPKG_L})
    def test_apt_le_single_true(self):
        content = r"""
        openssh-server:
            - le: '1:8.2p1-4ubuntu0.4'
        """
        self.assertTrue(self.load_apt_requires(content).result)

    @utils.create_data_root({'sos_commands/dpkg/dpkg_-l': DPKG_L})
    def test_apt_le_single_false(self):
        content = r"""
        openssh-server:
            - le: '1:8.2p1-4ubuntu0.3'
        """
        self.assertFalse(self.load_apt_requires(content).result)

    @utils.create_data_root({'sos_commands/dpkg/dpkg_-l': DPKG_L})
    def test_apt_eq_single_true(self):
        content = r"""
        openssh-server:
            - eq: '1:8.2p1-4ubuntu0.4'
        """
        self.assertTrue(self.load_apt_requires(content).result)

    @utils.create_data_root({'sos_commands/dpkg/dpkg_-l': DPKG_L})
    def test_apt_eq_single_false(self):
        content = r"""
        openssh-server:
            - eq: '1:8.2p1-4ubuntu0.4.4'
        """
        self.assertFalse(self.load_apt_requires(content).result)

    @utils.create_data_root({'sos_commands/dpkg/dpkg_-l': DPKG_L})
    def test_apt_eq_multiple_true(self):
        content = r"""
        openssh-server:
            - eq: '1:8.2p1-4ubuntu0.1'
            - eq: '1:8.2p1-4ubuntu0.2'
            - eq: '1:8.2p1-4ubuntu0.3'
            - eq: '1:8.2p1-4ubuntu0.4' # <-- should match this
            - eq: '1:8.2p1-4ubuntu0.5'
        """
        self.assertTrue(self.load_apt_requires(content).result)

    @utils.create_data_root({'sos_commands/dpkg/dpkg_-l': DPKG_L})
    def test_apt_eq_multiple_false(self):
        content = r"""
        openssh-server:
            - eq: '1:8.2p1-4ubuntu0.1'
            - eq: '1:8.2p1-4ubuntu0.2'
            - eq: '1:8.2p1-4ubuntu0.3'
            - eq: '1:8.2p1-4ubuntu0.5'
            - eq: '1:8.2p1-4ubuntu0.6'
        """
        self.assertFalse(self.load_apt_requires(content).result)

    @utils.create_data_root({'sos_commands/dpkg/dpkg_-l': DPKG_L})
    def test_apt_ge_multiple(self):
        content = r"""
        openssh-server:
            - ge: '1:8.9'
            - gt: '1:8.1' # <-- should match
              lt: '1:8.3'
        """
        self.assertTrue(self.load_apt_requires(content).result)

    @utils.create_data_root({'sos_commands/dpkg/dpkg_-l': DPKG_L})
    def test_apt_mixed(self):
        content = r"""
        openssh-server:
            - ge: '1:8.9 '
            - lt: '1:4'
            - ge: '1:6.3'
              lt: '1:7.2'
        """
        self.assertFalse(self.load_apt_requires(content).result)


class TestYamlRequiresTypeSnap(utils.BaseTestCase):

    def test_snap_revision_within_ranges_no_channel_true(self):
        ci = snap.SnapCheckItems('core20')
        result = ci.package_info_matches('core20', [
          {
            'revision': {'min': '1327',
                         'max': '1328'}
          }
        ])
        self.assertTrue(result)

    def test_snap_revision_within_ranges_no_channel_false(self):
        ci = snap.SnapCheckItems('core20')
        result = ci.package_info_matches('core20', [
          {
            'revision': {'min': '1326',
                         'max': '1327'}
          }
        ])
        self.assertFalse(result)

    def test_snap_revision_within_ranges_channel_true(self):
        ci = snap.SnapCheckItems('core20')
        result = ci.package_info_matches('core20', [
          {
            'revision': {'min': '1327',
                         'max': '1328'},
            'channel': 'latest/stable'
          }
        ])
        self.assertTrue(result)

    def test_snap_revision_within_ranges_channel_false(self):
        ci = snap.SnapCheckItems('core20')
        result = ci.package_info_matches('core20', [
          {
            'revision': {'min': '1327',
                         'max': '1328'},
            'channel': 'foo'
          }
        ])
        self.assertFalse(result)

    def test_snap_revision_within_multi_ranges_channel_true(self):
        ci = snap.SnapCheckItems('core20')
        result = ci.package_info_matches('core20', [
          {
            'revision': {'min': '1326',
                         'max': '1327'},
            'channel': 'foo'
          },
          {
            'revision': {'min': '1327',
                         'max': '1328'},
            'channel': 'latest/stable'
          },
          {
            'revision': {'min': '1329',
                         'max': '1330'},
            'channel': 'bar'
          }
        ])
        self.assertTrue(result)

    def test_snap_revision_with_invalid_range(self):
        with self.assertRaises(Exception):
            snap.SnapCheckItems('core20').package_info_matches('core20', [
              {
                'revision': {'mix': '1327'}
              }
            ])

    def test_snap_version_check_min_max(self):
        ci = snap.SnapCheckItems('core20')
        result = ci.package_info_matches('core20', [
            {
              'version': {'min': '20220114',
                          'max': '20220114'}
            }
          ])
        self.assertTrue(result)

    def test_snap_version_check_lt(self):
        ci = snap.SnapCheckItems('core20')
        result = ci.package_info_matches('core20', [
            {
              'version': {'lt': '20220115'}
            }
          ])
        self.assertTrue(result)

    def test_snap_version_check_gt_lt(self):
        ci = snap.SnapCheckItems('core20')
        result = ci.package_info_matches('core20', [
            {
              'version': {'gt': '20220113',
                          'lt': '20220115'}
            }
          ])
        self.assertTrue(result)

    def test_snap_version_check_everything(self):
        ci = snap.SnapCheckItems('core20')
        print(ci.installed_revisions)
        result = ci.package_info_matches('core20', [
            {
              'version': {'gt': '20220113',
                          'lt': '20220115'},
              'channel': 'latest/stable',
              'revision': {'eq': '1328'}
            }
          ])
        self.assertTrue(result)


class TestYamlProperties(utils.BaseTestCase):

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
        result.get.side_effect = lambda idx: _result.get(idx)

        _result = {1: '2022-01-06', 2: '12:34:56.123'}
        ts = YPropertySearch.get_datetime_from_result(result)
        self.assertEqual(ts, datetime.datetime(2022, 1, 6, 12, 34, 56))

        _result = {1: '2022-01-06', 2: '12:34:56'}
        ts = YPropertySearch.get_datetime_from_result(result)
        self.assertEqual(ts, datetime.datetime(2022, 1, 6, 12, 34, 56))

        _result = {1: '2022-01-06'}
        ts = YPropertySearch.get_datetime_from_result(result)
        self.assertEqual(ts, datetime.datetime(2022, 1, 6, 0, 0))

        _result = {1: '2022-01-06 12:34:56.123'}
        ts = YPropertySearch.get_datetime_from_result(result)
        self.assertEqual(ts, datetime.datetime(2022, 1, 6, 12, 34, 56))

        _result = {1: '2022-01-06 12:34:56'}
        ts = YPropertySearch.get_datetime_from_result(result)
        self.assertEqual(ts, datetime.datetime(2022, 1, 6, 12, 34, 56))

        _result = {1: '2022-01-06'}
        ts = YPropertySearch.get_datetime_from_result(result)
        self.assertEqual(ts, datetime.datetime(2022, 1, 6, 0, 0))

        _result = {1: '2022-01-06', 2: 'foo'}
        ts = YPropertySearch.get_datetime_from_result(result)
        self.assertIsNone(ts)

        _result = {1: 'foo'}
        ts = YPropertySearch.get_datetime_from_result(result)
        self.assertIsNone(ts)

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

    @mock.patch('hotsos.core.plugins.openstack.OpenstackChecksBase')
    def test_requires_grouped(self, mock_plugin):
        mock_plugin.return_value = mock.MagicMock()
        r1 = {'property':
              'hotsos.core.plugins.openstack.OpenstackChecksBase.r1'}
        r2 = {'property':
              'hotsos.core.plugins.openstack.OpenstackChecksBase.r2'}
        r3 = {'property':
              'hotsos.core.plugins.openstack.OpenstackChecksBase.r3'}
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
