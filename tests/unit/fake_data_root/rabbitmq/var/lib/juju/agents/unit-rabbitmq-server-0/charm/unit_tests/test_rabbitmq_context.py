# Copyright 2016 Canonical Ltd
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

import rabbitmq_context

from unittest import mock
import unittest
import tempfile


class TestRabbitMQSSLContext(unittest.TestCase):

    @mock.patch("rabbitmq_context.config")
    @mock.patch("rabbitmq_context.close_port")
    @mock.patch("rabbitmq_context.ssl_utils.reconfigure_client_ssl")
    @mock.patch("rabbitmq_context.ssl_utils.get_ssl_mode")
    def test_context_ssl_off(self, get_ssl_mode, reconfig_ssl, close_port,
                             config):
        get_ssl_mode.return_value = ("off", "off")
        self.assertEqual(rabbitmq_context.RabbitMQSSLContext().__call__(), {
            "ssl_mode": "off"
        })

        self.assertTrue(close_port.called)
        self.assertTrue(reconfig_ssl.called)

    @mock.patch.object(rabbitmq_context, 'cmp_pkgrevno')
    @mock.patch("rabbitmq_context.open_port")
    @mock.patch("rabbitmq_context.os.chmod")
    @mock.patch("rabbitmq_context.os.chown")
    @mock.patch("rabbitmq_context.os.path.exists")
    @mock.patch("rabbitmq_context.pwd.getpwnam")
    @mock.patch("rabbitmq_context.grp.getgrnam")
    @mock.patch("rabbitmq_context.config")
    @mock.patch("rabbitmq_context.close_port")
    @mock.patch("rabbitmq_context.ssl_utils.reconfigure_client_ssl")
    @mock.patch("rabbitmq_context.ssl_utils.get_ssl_mode")
    def test_context_ssl_on(self, get_ssl_mode, reconfig_ssl, close_port,
                            config, gr, pw, exists, chown, chmod, open_port,
                            cmp_pkgrevno):

        exists.return_value = True
        get_ssl_mode.return_value = ("on", "on")
        cmp_pkgrevno.return_value = 1

        def config_get(n):
            return None

        config.side_effect = config_get

        def pw(name):
            class Uid(object):
                pw_uid = 1
                gr_gid = 100
            return Uid()

        pw.side_effect = pw
        gr.side_effect = pw

        m = mock.mock_open()
        with mock.patch('rabbitmq_context.open', m, create=True):
            self.assertEqual(
                rabbitmq_context.RabbitMQSSLContext().__call__(), {
                    "ssl_port": None,
                    "ssl_cert_file": "/etc/rabbitmq/rabbit-server-cert.pem",
                    "ssl_key_file": '/etc/rabbitmq/rabbit-server-privkey.pem',
                    "ssl_client": False,
                    "ssl_ca_file": "",
                    "ssl_only": False,
                    "ssl_mode": "on",
                    "tls13": True,
                })

        self.assertTrue(reconfig_ssl.called)
        self.assertTrue(open_port.called)
        cmp_pkgrevno.assert_has_calls([
            mock.call("erlang-base", "23.0"),
            mock.call("rabbitmq-server", "3.8.11")
        ])

        # Check older erlang toggles tls13 flag off.
        cmp_pkgrevno.return_value = -1
        m = mock.mock_open()
        with mock.patch('rabbitmq_context.open', m, create=True):
            self.assertEqual(
                rabbitmq_context.RabbitMQSSLContext().__call__(), {
                    "ssl_port": None,
                    "ssl_cert_file": "/etc/rabbitmq/rabbit-server-cert.pem",
                    "ssl_key_file": '/etc/rabbitmq/rabbit-server-privkey.pem',
                    "ssl_client": False,
                    "ssl_ca_file": "",
                    "ssl_only": False,
                    "ssl_mode": "on",
                    "tls13": False,
                })

        cmp_pkgrevno.assert_called_with("erlang-base", "23.0")


class TestRabbitMQClusterContext(unittest.TestCase):

    @mock.patch.object(rabbitmq_context, 'leader_get')
    @mock.patch.object(rabbitmq_context, 'cmp_pkgrevno')
    @mock.patch("rabbitmq_context.config")
    def test_context_ssl_off(self, config, mock_cmp_pkgrevno, mock_leader_get):
        mock_leader_get.return_value = 'ignore'
        config_data = {'cluster-partition-handling': 'ignore',
                       'connection-backlog': 200,
                       'mnesia-table-loading-retry-timeout': 25000,
                       'mnesia-table-loading-retry-limit': 12,
                       'queue-master-locator': 'client-local'}
        config.side_effect = config_data.get
        mock_cmp_pkgrevno.return_value = 0

        self.assertEqual(
            rabbitmq_context.RabbitMQClusterContext().__call__(), {
                'cluster_partition_handling': "ignore",
                'mnesia_table_loading_retry_timeout': 25000,
                'mnesia_table_loading_retry_limit': 12,
                'connection_backlog': 200,
                'queue_master_locator': 'client-local',
            })

        config.assert_has_calls(
            [mock.call("mnesia-table-loading-retry-timeout"),
             mock.call("mnesia-table-loading-retry-limit"),
             mock.call("connection-backlog")],
            mock.call('queue-master-locator'))
        mock_leader_get.assert_called_once_with("cluster-partition-handling")

    @mock.patch.object(rabbitmq_context, 'leader_get')
    @mock.patch.object(rabbitmq_context, 'cmp_pkgrevno')
    @mock.patch("rabbitmq_context.config")
    def test_queue_master_locator_min_masters(self, config, mock_cmp_pkgrevno,
                                              mock_leader_get):
        mock_leader_get.return_value = 'ignore'
        config_data = {'cluster-partition-handling': 'ignore',
                       'connection-backlog': 200,
                       'mnesia-table-loading-retry-timeout': 25000,
                       'mnesia-table-loading-retry-limit': 12,
                       'queue-master-locator': 'min-masters'}
        config.side_effect = config_data.get
        mock_cmp_pkgrevno.return_value = 0

        self.assertEqual(
            rabbitmq_context.RabbitMQClusterContext().__call__(), {
                'cluster_partition_handling': "ignore",
                'connection_backlog': 200,
                'mnesia_table_loading_retry_timeout': 25000,
                'mnesia_table_loading_retry_limit': 12,
                'queue_master_locator': 'min-masters',
            })

        config.assert_has_calls([mock.call("connection-backlog")],
                                mock.call('queue-master-locator'))
        mock_leader_get.assert_called_once_with("cluster-partition-handling")

    @mock.patch.object(rabbitmq_context, 'leader_get')
    @mock.patch.object(rabbitmq_context, 'cmp_pkgrevno')
    @mock.patch("rabbitmq_context.config")
    def test_rabbit_server_3pt6(self, config, mock_cmp_pkgrevno,
                                mock_leader_get):
        mock_leader_get.return_value = 'ignore'
        config_data = {'cluster-partition-handling': 'ignore',
                       'connection-backlog': 200,
                       'mnesia-table-loading-retry-timeout': 25000,
                       'mnesia-table-loading-retry-limit': 12,
                       'queue-master-locator': 'min-masters'}
        config.side_effect = config_data.get
        mock_cmp_pkgrevno.return_value = -1

        self.assertEqual(
            rabbitmq_context.RabbitMQClusterContext().__call__(), {
                'cluster_partition_handling': "ignore",
                'connection_backlog': 200,
                'mnesia_table_loading_retry_timeout': 25000,
                'mnesia_table_loading_retry_limit': 12,
            })

        config.assert_has_calls(
            [mock.call("mnesia-table-loading-retry-timeout"),
             mock.call("mnesia-table-loading-retry-limit"),
             mock.call("connection-backlog")])
        assert mock.call('queue-master-locator') not in config.mock_calls
        mock_leader_get.assert_called_once_with("cluster-partition-handling")

    @mock.patch.object(rabbitmq_context, 'leader_get')
    @mock.patch.object(rabbitmq_context, 'cmp_pkgrevno')
    @mock.patch("rabbitmq_context.config")
    def test_partition_handling(self, config, mock_cmp_pkgrevno,
                                mock_leader_get):
        mock_leader_get.return_value = 'ignore'
        config_data = {'cluster-partition-handling': 'autoheal',
                       'connection-backlog': 200,
                       'mnesia-table-loading-retry-timeout': 25000,
                       'mnesia-table-loading-retry-limit': 12,
                       'queue-master-locator': 'min-masters'}
        config.side_effect = config_data.get
        mock_cmp_pkgrevno.return_value = -1

        self.assertEqual(
            rabbitmq_context.RabbitMQClusterContext().__call__(), {
                'cluster_partition_handling': "ignore",
                'connection_backlog': 200,
                'mnesia_table_loading_retry_timeout': 25000,
                'mnesia_table_loading_retry_limit': 12,
            })
        mock_leader_get.return_value = None
        self.assertEqual(
            rabbitmq_context.RabbitMQClusterContext().__call__(), {
                'cluster_partition_handling': "ignore",
                'connection_backlog': 200,
                'mnesia_table_loading_retry_timeout': 25000,
                'mnesia_table_loading_retry_limit': 12,
            })


class TestRabbitMQEnvContext(unittest.TestCase):

    @mock.patch.object(rabbitmq_context.psutil, 'NUM_CPUS', 2)
    @mock.patch.object(rabbitmq_context, 'relation_ids', lambda *args: [])
    @mock.patch.object(rabbitmq_context, 'service_name')
    @mock.patch.object(rabbitmq_context, 'config')
    def test_rabbitmqenv(self, mock_config, mock_service_name):
        config = {}

        def fake_config(key):
            return config.get(key)

        mock_service_name.return_value = 'svc_foo'
        mock_config.side_effect = fake_config

        with tempfile.NamedTemporaryFile() as tmpfile:
            with mock.patch('rabbitmq_context.ENV_CONF', tmpfile.name):
                config['prefer-ipv6'] = True
                config['erl-vm-io-thread-multiplier'] = 36
                ctxt = rabbitmq_context.RabbitMQEnvContext()()
                self.assertEqual(ctxt['settings'],
                                 {'RABBITMQ_SERVER_START_ARGS':
                                  "'-proto_dist inet6_tcp'",
                                  'RABBITMQ_SERVER_ADDITIONAL_ERL_ARGS':
                                  "'+A 72'"})

    @mock.patch.object(rabbitmq_context.psutil, 'NUM_CPUS', 2)
    @mock.patch.object(rabbitmq_context, 'relation_ids')
    @mock.patch.object(rabbitmq_context, 'service_name')
    @mock.patch.object(rabbitmq_context, 'config')
    def test_rabbitmqenv_legacy_ha_support(self, mock_config,
                                           mock_service_name,
                                           mock_relation_ids):
        config = {}

        def fake_config(key):
            return config.get(key)

        def fake_relation_ids(key):
            if 'ha':
                return ['ha:1']

        mock_relation_ids.side_effect = fake_relation_ids
        mock_service_name.return_value = 'svc_foo'
        mock_config.side_effect = fake_config

        with tempfile.NamedTemporaryFile() as tmpfile:
            with mock.patch('rabbitmq_context.ENV_CONF', tmpfile.name):
                ctxt = rabbitmq_context.RabbitMQEnvContext()()
                self.assertEqual(ctxt['settings'],
                                 {'RABBITMQ_NODENAME': 'svc_foo@localhost',
                                  'RABBITMQ_SERVER_ADDITIONAL_ERL_ARGS':
                                  "'+A 48'"})

        mock_relation_ids.side_effect = lambda key: []
        with tempfile.NamedTemporaryFile() as tmpfile:
            with mock.patch('rabbitmq_context.ENV_CONF', tmpfile.name):
                ctxt = rabbitmq_context.RabbitMQEnvContext()()
                self.assertEqual(ctxt['settings'],
                                 {'RABBITMQ_SERVER_ADDITIONAL_ERL_ARGS':
                                  "'+A 48'"})

    @mock.patch.object(rabbitmq_context.psutil, 'NUM_CPUS', 2)
    @mock.patch.object(rabbitmq_context, 'relation_ids')
    @mock.patch.object(rabbitmq_context, 'service_name')
    @mock.patch.object(rabbitmq_context, 'config')
    def test_rabbitmqenv_existing_nodename(self, mock_config,
                                           mock_service_name,
                                           mock_relation_ids):
        def fake_relation_ids(key):
            if 'ha':
                return ['ha:1']

        mock_relation_ids.side_effect = fake_relation_ids
        mock_service_name.return_value = 'svc_foo'
        mock_config.return_value = None

        with tempfile.NamedTemporaryFile() as tmpfile:
            with mock.patch('rabbitmq_context.ENV_CONF', tmpfile.name):
                with open(tmpfile.name, 'w') as fd:
                    fd.write("RABBITMQ_NODENAME = blah@localhost")

                ctxt = rabbitmq_context.RabbitMQEnvContext()()
                self.assertEqual(ctxt['settings'],
                                 {'RABBITMQ_NODENAME': 'blah@localhost',
                                  'RABBITMQ_SERVER_ADDITIONAL_ERL_ARGS':
                                  "'+A 48'"})

    @mock.patch.object(rabbitmq_context, 'relation_ids', lambda *args: [])
    @mock.patch.object(rabbitmq_context.psutil, 'NUM_CPUS', 128)
    @mock.patch.object(rabbitmq_context, 'service_name')
    @mock.patch.object(rabbitmq_context, 'config')
    def test_rabbitmqenv_in_container(self, mock_config, mock_service_name):
        mock_service_name.return_value = 'svc_foo'

        config = {}

        def fake_config(key):
            return config.get(key)

        mock_config.side_effect = fake_config

        with mock.patch.object(rabbitmq_context, 'is_container') as \
                mock_is_ctnr:
            mock_is_ctnr.return_value = True
            ctxt = rabbitmq_context.RabbitMQEnvContext()()
            self.assertEqual(ctxt['settings'],
                             {'RABBITMQ_SERVER_ADDITIONAL_ERL_ARGS':
                              "'+A 48'"})

            config['erl-vm-io-thread-multiplier'] = 24
            ctxt = rabbitmq_context.RabbitMQEnvContext()()
            self.assertEqual(ctxt['settings'],
                             {'RABBITMQ_SERVER_ADDITIONAL_ERL_ARGS':
                              "'+A 3072'"})

            del config['erl-vm-io-thread-multiplier']
            mock_is_ctnr.return_value = False
            ctxt = rabbitmq_context.RabbitMQEnvContext()()
            self.assertEqual(ctxt['settings'],
                             {'RABBITMQ_SERVER_ADDITIONAL_ERL_ARGS':
                              "'+A 3072'"})
