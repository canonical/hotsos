from datetime import datetime

from hotsos.core.search import (
    CommonTimestampMatcher,
    SearchConstraintSearchSince,
)

from . import utils


class TestSearchTimestamps(utils.BaseTestCase):
    """Tests for timestamps used by file search constraints."""

    def test_priority_syslog_age_constraint(self):
        """Apply the age boundary to traditional syslog priority prefixes."""
        constraint = SearchConstraintSearchSince(
            ts_matcher_cls=CommonTimestampMatcher, hours=24)
        for prefix in ('', '<6>'):
            for timestamp, expected in (('Feb 09 16:19:18', True),
                                        ('Feb 09 16:19:16', False)):
                with self.subTest(prefix=prefix, timestamp=timestamp):
                    self.assertEqual(constraint.apply_to_line(
                        f'{prefix}{timestamp} host kernel: message'), expected)

    def test_iso_timestamp_timezone(self):
        """Convert ISO timestamps to the constraint's UTC time base."""
        for prefix in ('', '<6>'):
            for timestamp in ('2022-02-09T16:19:18Z',
                              '2022-02-09T16:19:18.000000+00:00',
                              '2022-02-09T16:19:18.123456789+00:00',
                              '2022-02-09T21:49:18+05:30',
                              '2022-02-09T12:19:18-04:00'):
                with self.subTest(prefix=prefix, timestamp=timestamp):
                    matcher = CommonTimestampMatcher(
                        f'{prefix}{timestamp} host kernel: message')
                    self.assertTrue(matcher.matched)
                    self.assertEqual(matcher.strptime,
                                     datetime(2022, 2, 9, 16, 19, 18))

    def test_iso_timestamp_age_constraint(self):
        """Apply the age boundary to priority-prefixed ISO timestamps."""
        constraint = SearchConstraintSearchSince(
            ts_matcher_cls=CommonTimestampMatcher, hours=24)
        for prefix in ('', '<6>'):
            for timestamp, expected in (
                    ('2022-02-09T16:19:18+00:00', True),
                    ('2022-02-09T16:19:16+00:00', False),
                    ('2022-02-09T21:49:18+05:30', True),
                    ('2022-02-09T21:49:16+05:30', False)):
                with self.subTest(prefix=prefix, timestamp=timestamp):
                    self.assertEqual(constraint.apply_to_line(
                        f'{prefix}{timestamp} host kernel: message'), expected)
