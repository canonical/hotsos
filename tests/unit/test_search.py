from datetime import datetime

from hotsos.core.search import CommonTimestampMatcher

from . import utils


class TestCommonTimestampMatcher(utils.BaseTestCase):
    """Tests for CommonTimestampMatcher timestamp formats."""

    def test_apache_error_log_timestamp(self):
        """Apache error logs use [Www Mmm DD HH:MM:SS.ffffff YYYY]."""
        line = ('[Thu Feb 10 06:14:46.123456 2022] [wsgi:error] '
                '[pid 19692:tid 140252996032064] 2022-02-10 06:14:46.123 '
                '19692 ERROR octavia.api.drivers.driver_factory [-] done')
        matcher = CommonTimestampMatcher(line)
        self.assertTrue(matcher.matched)
        self.assertEqual(matcher.strptime,
                         datetime(2022, 2, 10, 6, 14, 46))

    def test_openstack_timestamp(self):
        """Existing OpenStack service log timestamp format still matches."""
        line = ('2022-02-10 06:14:46.123 19692 ERROR '
                'octavia.api.drivers.driver_factory [-] done')
        matcher = CommonTimestampMatcher(line)
        self.assertTrue(matcher.matched)
        self.assertEqual(matcher.strptime,
                         datetime(2022, 2, 10, 6, 14, 46))

    def test_apache_access_log_timestamp(self):
        """Existing Apache access log timestamp format still matches."""
        line = ('127.0.0.1 - - [10/Feb/2022:06:14:46 +0000] '
                '"GET / HTTP/1.0" 200 -')
        matcher = CommonTimestampMatcher(line)
        self.assertTrue(matcher.matched)
        self.assertEqual(matcher.strptime,
                         datetime(2022, 2, 10, 6, 14, 46))
