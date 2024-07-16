
from hotsos.core.host_helpers import uptime as host_uptime

from .. import utils


class TestUptimeHelper(utils.BaseTestCase):
    """ Unit tests for uptime helper """
    def test_loadavg(self):
        self.assertEqual(host_uptime.UptimeHelper().loadavg,
                         "3.58, 3.27, 2.58")

    def test_uptime(self):
        uptime = host_uptime.UptimeHelper()
        self.assertEqual(uptime.in_seconds, 63660)
        self.assertEqual(uptime.in_hours, 17)
        self.assertEqual(repr(uptime), '0d:17h:41m')

    @utils.create_data_root({'uptime':
                             (' 14:51:10 up 1 day,  6:27,  1 user,  '
                              'load average: 0.55, 0.73, 0.70')})
    def test_uptime_alt_format(self):
        uptime = host_uptime.UptimeHelper()
        self.assertEqual(uptime.in_seconds, 109620)
        self.assertEqual(uptime.in_hours, 30)
        self.assertEqual(repr(uptime), '1d:6h:27m')

    @utils.create_data_root({'uptime':
                             (' 19:12:40 up  1:55,  2 users,  '
                              'load average: 3.92, 4.05, 3.90')})
    def test_uptime_alt_format2(self):
        uptime = host_uptime.UptimeHelper()
        self.assertEqual(uptime.in_seconds, 6900)
        self.assertEqual(uptime.in_hours, 1)
        self.assertEqual(uptime.loadavg,
                         '3.92, 4.05, 3.90')
        self.assertEqual(repr(uptime), '0d:1h:55m')
