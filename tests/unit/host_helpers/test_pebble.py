
from hotsos.core.host_helpers import pebble as host_pebble

from .. import utils

PEBBLE_SERVICES = """Service         Startup  Current  Since
nova-conductor  enabled  backoff  today at 10:25 UTC
"""

#  pylint: disable=C0301
PEBBLE_PS = """USER         PID %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND
root           1  0.0  0.0 717708 10516 ?        Ssl  08:43   0:01 /charm/bin/pebble run --create-dirs --hold --http :38814 --verbose
root        3048  0.0  0.0   2620   600 pts/0    Ss   10:14   0:00 sh -c bash
root        3055  0.0  0.0   7372  4036 pts/0    S    10:14   0:00 bash
root        3225  0.0  0.2  80748 65780 ?        R    10:42   0:00 /usr/bin/python3 /usr/bin/nova-conductor
"""  # noqa


class TestPebbleHelper(utils.BaseTestCase):

    @utils.create_data_root({'sos_commands/pebble/pebble_services':
                             PEBBLE_SERVICES})
    def test_service_factory(self):
        svc = getattr(host_pebble.ServiceFactory(), 'nova-conductor')
        self.assertEqual(svc.state, 'backoff')

        self.assertIsNone(host_pebble.ServiceFactory().noexist)

    @utils.create_data_root({'sos_commands/pebble/pebble_services':
                             PEBBLE_SERVICES,
                             'ps': PEBBLE_PS})
    def test_pebble_helper(self):
        expected = {'ps': ['nova-conductor (1)'],
                    'pebble': {'backoff': ['nova-conductor']}}
        s = host_pebble.PebbleHelper([r'nova\S+'])
        self.assertEqual(s.summary, expected)
