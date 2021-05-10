import utils

from common.host_helpers import HostNetworkingHelper


class TestHostHelpers(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

    def test_HostNetworkingHelper_get_host_interfaces(self):
        expected = ['bond1', 'tap40f8453b-31', 'br-bond1', 'tap1fd66df1-42']
        helper = HostNetworkingHelper()
        ifaces = helper.get_host_interfaces()
        self.assertEqual(ifaces, expected)

    def test_HostNetworkingHelper_get_host_interfaces_w_ns(self):
        expected = ['bond1', 'tap40f8453b-31', 'br-bond1', 'tap1fd66df1-42']
        helper = HostNetworkingHelper()
        ifaces = helper.get_host_interfaces(include_namespaces=True)
        self.assertEqual(ifaces, expected)
