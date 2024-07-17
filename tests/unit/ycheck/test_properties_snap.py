
from hotsos.core.ycheck.engine.properties.requires.types import (
    snap,
)

from .. import utils


class TestYamlRequiresTypeSnap(utils.BaseTestCase):
    """ Tests requires type snap property. """

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
