# Copyright 2017 Canonical Ltd
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from unit_tests.test_utils import CharmTestCase
from unittest.mock import patch

import ssl_utils

TO_PATCH = [
    'config',
]

TEST_CA = """-----SCRUBBED CERTIFICATE-----"""

B64_TEST_CA = """LS0tLS1CRUdJTiBDRVJUSUZJQ0FURS0tLS0tCk1JSURiVENDQWxXZ0F3SUJBZ0lVUnRkR0dLS2pja2lMUEx1ZThXbi9zQ1M1dStRd0RRWUpLb1pJaHZjTkFRRUwKQlFBd1BURTdNRGtHQTFVRUF4TXlWbUYxYkhRZ1VtOXZkQ0JEWlhKMGFXWnBZMkYwWlNCQmRYUm9iM0pwZEhrZwpLR05vWVhKdExYQnJhUzFzYjJOaGJDa3dJQmdQTURBd01UQXhNREV3TURBd01EQmFGdzB4T0RFeE1qUXhNelF4Ck1qZGFNRDB4T3pBNUJnTlZCQU1UTWxaaGRXeDBJRkp2YjNRZ1EyVnlkR2xtYVdOaGRHVWdRWFYwYUc5eWFYUjUKSUNoamFHRnliUzF3YTJrdGJHOWpZV3dwTUlJQklqQU5CZ2txaGtpRzl3MEJBUUVGQUFPQ0FROEFNSUlCQ2dLQwpBUUVBd1VFZzhYRk8yR3pJMTlhTkFmSDhLZUJzTHZwWVRYNG5OUkVFR0xNa2w3cWZxTytyY3dObU4vNjBVeFN1Ckhic3FmanY2QjZrV0Q2ZGQxL092dmVZanhxUEE5N09xTzVMT1VFNDNvanpVa3hhaTVHZUY1ZnZ1M1FHSVI3aVoKYTlQRURGakZLZUNkd3lLTG9JSE5kWHcxVE0wc1FtV003c1NpTWhDZnJwZVpFZStFbitLWlF1Z28rQmlMcmhLQQp5WlRJa0VQNSs2ci9Ocnhma3gyL0trbHJxOExPeUxmSDkxTGJtSkVWRUtRTmxvQ1lwaFpZd0I3bjlHUHZLbEd2CnB2UHVKYzd3RWttdENNcDBkTmpvM01aMGlqMVNJTjZOdHg4RHFoUEo4UUt2TkRvZ1ZtZUVHcFFGQmNyemZrb2wKTE1YUEJwWDJReDZkUHFMR0hDYldRRG52ZXdJREFRQUJvMk13WVRBT0JnTlZIUThCQWY4RUJBTUNBUVl3RHdZRApWUjBUQVFIL0JBVXdBd0VCL3pBZEJnTlZIUTRFRmdRVWMxcmgyQkVIU1FKMHF4aFBURFFLUkpnMkFHRXdId1lEClZSMGpCQmd3Rm9BVWMxcmgyQkVIU1FKMHF4aFBURFFLUkpnMkFHRXdEUVlKS29aSWh2Y05BUUVMQlFBRGdnRUIKQUJadnJldGljVzVVdW9RUzdOQVZJQ0N2aDVGd2dya0M1dG5IWDNwOFRPaE1JcEpUZ3JLaGVkSlpLekxjMjU0ZwovakFzYjdxNzc1SWNNT2hTMnZGSlNRZDZyVjBjTU5DZEZqazBzVFRlMDFPWG9KajJmTjNNTWJFRUdmczZjcndrClRLaVhFSjlYWWMwNFVsNGI4WEowZDVoWWVqcjVJRjlsZUoySkpNaUdUSkZHVTFPaThMY3RqN3F5WDBubG8reDUKWGhqOEJic0pzYlVHb0ErYlh2Q09PODh2b3lPWm9SR0NnMUpGenRicGdJQVY2azY0REo3eHA5dE5EaFpKajBVbwoyTURyV2JmVVlGV01pRDVMMGQ1TWplWDdhR0lQaEpzTXVuZDF6RkhyMWhvNjRPZENKMXpEbXRrNFVZelowZGVFCjVuTEEzRlhoK3NuYUVwbXBsN1g5WHVzPQotLS0tLUVORCBDRVJUSUZJQ0FURS0tLS0t"""  # noqa: E501


class TestSSLUtils(CharmTestCase):

    def setUp(self):
        super(TestSSLUtils, self).setUp(ssl_utils, TO_PATCH)

    @patch('ssl_utils.get_hostname')
    @patch('ssl_utils.get_relation_ip')
    def test_get_unit_amqp_endpoint_data(self, get_relation_ip, get_hostname):
        self.config.return_value = '10.0.0.0/24'
        get_relation_ip.return_value = '10.0.0.10'
        get_hostname.return_value = 'myhost'
        self.assertEqual(
            ssl_utils.get_unit_amqp_endpoint_data(),
            ('10.0.0.10', 'myhost'))
        get_relation_ip.assert_called_once_with(
            'amqp',
            cidr_network='10.0.0.0/24')
        get_hostname.assert_called_once_with('10.0.0.10')

    @patch('ssl_utils.ch_cert_utils.get_bundle_for_cn')
    @patch('ssl_utils.get_unit_amqp_endpoint_data')
    def test_get_relation_cert_data(self, get_unit_amqp_endpoint_data,
                                    get_bundle_for_cn):
        get_unit_amqp_endpoint_data.return_value = ('10.0.0.10',
                                                    'juju-345.lcd')
        get_bundle_for_cn.return_value = {
            'ca': 'vaultca',
            'cert': 'vaultcert',
            'key': 'vaultkey'}
        self.assertEqual(
            ssl_utils.get_relation_cert_data(),
            {'ca': 'vaultca', 'cert': 'vaultcert', 'key': 'vaultkey'})
        get_bundle_for_cn.assert_called_once_with('juju-345.lcd')

    @patch('ssl_utils.get_relation_cert_data')
    def test_get_ssl_mode_off(self, get_relation_cert_data):
        get_relation_cert_data.return_value = {}
        test_config = {
            'ssl': 'off',
            'ssl_enabled': False,
            'ssl_on': False,
            'ssl_key': None,
            'ssl_cert': None}
        self.config.side_effect = lambda x: test_config[x]
        self.assertEqual(
            ssl_utils.get_ssl_mode(),
            ('off', False))

    @patch('ssl_utils.get_relation_cert_data')
    def test_get_ssl_enabled_true(self, get_relation_cert_data):
        get_relation_cert_data.return_value = {}
        test_config = {
            'ssl': 'off',
            'ssl_enabled': True,
            'ssl_on': False,
            'ssl_key': None,
            'ssl_cert': None}
        self.config.side_effect = lambda x: test_config[x]
        self.assertEqual(
            ssl_utils.get_ssl_mode(),
            ('on', False))

    @patch('ssl_utils.get_relation_cert_data')
    def test_get_ssl_enabled_false(self, get_relation_cert_data):
        get_relation_cert_data.return_value = {}
        test_config = {
            'ssl': 'on',
            'ssl_enabled': False,
            'ssl_on': False,
            'ssl_key': None,
            'ssl_cert': None}
        self.config.side_effect = lambda x: test_config[x]
        self.assertEqual(
            ssl_utils.get_ssl_mode(),
            ('on', False))

    @patch('ssl_utils.get_relation_cert_data')
    def test_get_ssl_enabled_external_ca(self, get_relation_cert_data):
        get_relation_cert_data.return_value = {}
        test_config = {
            'ssl': 'on',
            'ssl_enabled': False,
            'ssl_on': False,
            'ssl_key': 'key1',
            'ssl_cert': 'cert1'}
        self.config.side_effect = lambda x: test_config[x]
        self.assertEqual(
            ssl_utils.get_ssl_mode(),
            ('on', True))

    @patch('ssl_utils.get_relation_cert_data')
    def test_get_ssl_enabled_relation_certs(self, get_relation_cert_data):
        get_relation_cert_data.return_value = {
            'cert': 'vaultcert',
            'key': 'vaultkey',
            'ca': 'vaultca'}
        self.assertEqual(
            ssl_utils.get_ssl_mode(),
            ('certs-relation', True))

    @patch('ssl_utils.get_relation_cert_data')
    @patch('ssl_utils.get_ssl_mode')
    def test_get_ssl_mode_ssl_off(self, get_ssl_mode, get_relation_cert_data):
        get_ssl_mode.return_value = ('off', False)
        get_relation_cert_data.return_value = {}
        relation_data = {}
        ssl_utils.configure_client_ssl(relation_data)
        self.assertEqual(relation_data, {})

    @patch('ssl_utils.ServiceCA')
    @patch('ssl_utils.get_ssl_mode')
    def test_get_ssl_mode_ssl_on_no_ca(self, get_ssl_mode, ServiceCA):
        ServiceCA.get_ca().get_ca_bundle.return_value = 'cert1'
        get_ssl_mode.return_value = ('on', False)
        test_config = {
            'ssl_port': '9090'}
        self.config.side_effect = lambda x: test_config[x]
        relation_data = {}
        ssl_utils.configure_client_ssl(relation_data)
        self.assertEqual(
            relation_data,
            {'ssl_port': '9090', 'ssl_ca': 'Y2VydDE='})

    @patch('ssl_utils.get_ssl_mode')
    def test_get_ssl_mode_ssl_on_ext_ca(self, get_ssl_mode):
        get_ssl_mode.return_value = ('on', True)
        test_config = {
            'ssl_port': '9090',
            'ssl_ca': TEST_CA}
        self.config.side_effect = lambda x: test_config[x]
        relation_data = {}
        ssl_utils.configure_client_ssl(relation_data)
        self.maxDiff = None
        self.assertEqual(
            relation_data,
            {'ssl_port': '9090', 'ssl_ca': B64_TEST_CA})

    @patch('ssl_utils.get_ssl_mode')
    def test_get_ssl_mode_ssl_on_ext_ca_b64(self, get_ssl_mode):
        get_ssl_mode.return_value = ('on', True)
        test_config = {
            'ssl_port': '9090',
            'ssl_ca': 'ZXh0X2Nh'}
        self.config.side_effect = lambda x: test_config[x]
        relation_data = {}
        ssl_utils.configure_client_ssl(relation_data)
        self.assertEqual(
            relation_data,
            {'ssl_port': '9090', 'ssl_ca': 'ZXh0X2Nh'})

    @patch('ssl_utils.local_unit')
    @patch('ssl_utils.relation_ids')
    @patch('ssl_utils.relation_get')
    @patch('ssl_utils.configure_client_ssl')
    @patch('ssl_utils.relation_set')
    def test_reconfigure_client_ssl_no_ssl(self, relation_set,
                                           configure_client_ssl, relation_get,
                                           relation_ids, local_unit):
        relation_ids.return_value = ['rel1']
        relation_get.return_value = {'ssl_key': 'aa'}
        ssl_utils.reconfigure_client_ssl(ssl_enabled=False)
        relation_set.assert_called_with(
            relation_id='rel1',
            ssl_ca='',
            ssl_cert='',
            ssl_key='',
            ssl_port='')

    @patch('ssl_utils.local_unit')
    @patch('ssl_utils.relation_ids')
    @patch('ssl_utils.relation_get')
    @patch('ssl_utils.configure_client_ssl')
    @patch('ssl_utils.relation_set')
    def test_reconfigure_client_ssl(self, relation_set, configure_client_ssl,
                                    relation_get, relation_ids, local_unit):
        relation_ids.return_value = ['rel1']
        relation_get.return_value = {}
        ssl_utils.reconfigure_client_ssl(ssl_enabled=True)
        configure_client_ssl.assert_called_with({})
