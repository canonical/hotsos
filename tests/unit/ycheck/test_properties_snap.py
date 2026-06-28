
from hotsos.core.ycheck.engine.properties.requires.types import (
    snap,
)

from .. import utils


class TestYamlRequiresTypeSnap(utils.BaseTestCase):
    """ Tests requires type snap property. """

    def test_snap_revision_within_ranges_no_channel_true(self):
        """ Test snap revision within range without channel. """
        ci = snap.SnapCheckItems('core20')
        result = ci.package_info_matches('core20', [
          {
            'revision': {'min': '1327',
                         'max': '1328'}
          }
        ])
        self.assertTrue(result)

    def test_snap_revision_within_ranges_no_channel_false(self):
        """ Test snap revision outside range without channel. """
        ci = snap.SnapCheckItems('core20')
        result = ci.package_info_matches('core20', [
          {
            'revision': {'min': '1326',
                         'max': '1327'}
          }
        ])
        self.assertFalse(result)

    def test_snap_revision_within_ranges_channel_true(self):
        """ Test snap revision within range with matching channel. """
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
        """ Test snap revision within range with wrong channel. """
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
        """ Test snap revision matching one of multiple ranges. """
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
        """ Test that invalid revision range keys raise an error. """
        with self.assertRaises(Exception):
            snap.SnapCheckItems('core20').package_info_matches('core20', [
              {
                'revision': {'mix': '1327'}
              }
            ])

    def test_snap_version_check_min_max(self):
        """ Test snap version within min/max range. """
        ci = snap.SnapCheckItems('core20')
        result = ci.package_info_matches('core20', [
            {
              'version': {'min': '20220114',
                          'max': '20220114'}
            }
          ])
        self.assertTrue(result)

    def test_snap_version_check_lt(self):
        """ Test snap version less-than comparison. """
        ci = snap.SnapCheckItems('core20')
        result = ci.package_info_matches('core20', [
            {
              'version': {'lt': '20220115'}
            }
          ])
        self.assertTrue(result)

    def test_snap_version_check_gt_lt(self):
        """ Test snap version within gt/lt range. """
        ci = snap.SnapCheckItems('core20')
        result = ci.package_info_matches('core20', [
            {
              'version': {'gt': '20220113',
                          'lt': '20220115'}
            }
          ])
        self.assertTrue(result)

    def test_snap_version_check_everything(self):
        """ Test snap check with version, channel, and revision. """
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
