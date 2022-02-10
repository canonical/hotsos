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

from collections import OrderedDict
import copy
import unittest

from unittest.mock import patch, MagicMock, call

import charmhelpers.contrib.storage.linux.ceph as ceph

with patch('charmhelpers.contrib.hardening.harden.harden') as mock_dec:
    mock_dec.side_effect = (lambda *dargs, **dkwargs: lambda f:
                            lambda *args, **kwargs: f(*args, **kwargs))
    import ceph_hooks

CHARM_CONFIG = {'config-flags': '',
                'loglevel': 1,
                'use-syslog': True,
                'osd-journal-size': 1024,
                'osd-max-backfills': 1,
                'osd-recovery-max-active': 2,
                'use-direct-io': True,
                'osd-format': 'ext4',
                'prefer-ipv6': False,
                'customize-failure-domain': False,
                'bluestore': False,
                'crush-initial-weight': '0',
                'bdev-enable-discard': 'enable',
                'osd-devices': '/dev/vdb',
                'bluestore': False,
                'bluestore-block-wal-size': 0,
                'bluestore-block-db-size': 0,
                'bluestore-wal': None,
                'bluestore-db': None}


BLUESTORE_WAL_TEST_SIZE = 128 * 2 ** 20
BLUESTORE_DB_TEST_SIZE = 2 * 2 ** 30


class CephHooksTestCase(unittest.TestCase):
    def setUp(self):
        super(CephHooksTestCase, self).setUp()

    @patch.object(ceph_hooks.ch_context, 'CephBlueStoreCompressionContext',
                  lambda: lambda: {})
    @patch.object(ceph_hooks.ch_ceph, 'get_osd_settings', lambda *args: {})
    @patch.object(ceph_hooks, 'get_fsid', lambda *args: '1234')
    @patch.object(ceph_hooks, 'get_auth', lambda *args: False)
    @patch.object(ceph_hooks, 'get_public_addr', lambda *args: "10.0.0.1")
    @patch.object(ceph_hooks, 'get_cluster_addr', lambda *args: "10.1.0.1")
    @patch.object(ceph_hooks, 'cmp_pkgrevno', lambda *args: 1)
    @patch.object(ceph_hooks, 'get_mon_hosts', lambda *args: ['10.0.0.1',
                                                              '10.0.0.2'])
    @patch.object(ceph_hooks, 'get_networks', lambda *args: "")
    @patch.object(ceph, 'config')
    @patch.object(ceph_hooks, 'config')
    def test_get_ceph_context(self, mock_config, mock_config2):
        config = copy.deepcopy(CHARM_CONFIG)
        mock_config.side_effect = lambda key: config[key]
        mock_config2.side_effect = lambda key: config[key]
        ctxt = ceph_hooks.get_ceph_context()
        expected = {'auth_supported': False,
                    'ceph_cluster_network': '',
                    'ceph_public_network': '',
                    'cluster_addr': '10.1.0.1',
                    'dio': 'true',
                    'fsid': '1234',
                    'loglevel': 1,
                    'mon_hosts': '10.0.0.1 10.0.0.2',
                    'old_auth': False,
                    'crush_initial_weight': '0',
                    'osd_journal_size': 1024,
                    'osd_max_backfills': 1,
                    'osd_recovery_max_active': 2,
                    'osd_from_client': OrderedDict(),
                    'osd_from_client_conflict': OrderedDict(),
                    'public_addr': '10.0.0.1',
                    'short_object_len': True,
                    'upgrade_in_progress': False,
                    'use_syslog': 'true',
                    'bdev_discard': True,
                    'bluestore': False,
                    'bluestore_experimental': False,
                    'bluestore_block_wal_size': 0,
                    'bluestore_block_db_size': 0}
        self.assertEqual(ctxt, expected)

    @patch.object(ceph_hooks.ch_context, 'CephBlueStoreCompressionContext',
                  lambda: lambda: {})
    @patch.object(ceph_hooks.ch_ceph, 'get_osd_settings', lambda *args: {})
    @patch.object(ceph_hooks, 'get_fsid', lambda *args: '1234')
    @patch.object(ceph_hooks, 'get_auth', lambda *args: False)
    @patch.object(ceph_hooks, 'get_public_addr', lambda *args: "10.0.0.1")
    @patch.object(ceph_hooks, 'get_cluster_addr', lambda *args: "10.1.0.1")
    @patch.object(ceph_hooks, 'cmp_pkgrevno', lambda *args: 1)
    @patch.object(ceph_hooks, 'get_mon_hosts', lambda *args: ['10.0.0.1',
                                                              '10.0.0.2'])
    @patch.object(ceph_hooks, 'get_networks', lambda *args: "")
    @patch.object(ceph, 'config')
    @patch.object(ceph_hooks, 'config')
    def test_get_ceph_context_invalid_bdev_enable_discard(self, mock_config,
                                                          mock_config2):
        config = copy.deepcopy(CHARM_CONFIG)
        config['bdev-enable-discard'] = 'some-invalid-value'
        mock_config.side_effect = lambda key: config[key]
        mock_config2.side_effect = lambda key: config[key]
        ctxt = ceph_hooks.get_ceph_context()
        expected = {'auth_supported': False,
                    'ceph_cluster_network': '',
                    'ceph_public_network': '',
                    'cluster_addr': '10.1.0.1',
                    'dio': 'true',
                    'fsid': '1234',
                    'loglevel': 1,
                    'mon_hosts': '10.0.0.1 10.0.0.2',
                    'old_auth': False,
                    'crush_initial_weight': '0',
                    'osd_journal_size': 1024,
                    'osd_max_backfills': 1,
                    'osd_recovery_max_active': 2,
                    'osd_from_client': OrderedDict(),
                    'osd_from_client_conflict': OrderedDict(),
                    'public_addr': '10.0.0.1',
                    'short_object_len': True,
                    'upgrade_in_progress': False,
                    'use_syslog': 'true',
                    'bdev_discard': False,
                    'bluestore': False,
                    'bluestore_experimental': False,
                    'bluestore_block_wal_size': 0,
                    'bluestore_block_db_size': 0}
        self.assertEqual(ctxt, expected)

    @patch.object(ceph_hooks.ch_context, 'CephBlueStoreCompressionContext',
                  lambda: lambda: {})
    @patch.object(ceph_hooks.ch_ceph, 'get_osd_settings', lambda *args: {})
    @patch.object(ceph_hooks, 'get_fsid', lambda *args: '1234')
    @patch.object(ceph_hooks, 'get_auth', lambda *args: False)
    @patch.object(ceph_hooks, 'get_public_addr', lambda *args: "10.0.0.1")
    @patch.object(ceph_hooks, 'get_cluster_addr', lambda *args: "10.1.0.1")
    @patch.object(ceph_hooks, 'cmp_pkgrevno',
                  lambda pkg, ver: -1 if ver == '12.1.0' else 1)
    @patch.object(ceph_hooks, 'get_mon_hosts', lambda *args: ['10.0.0.1',
                                                              '10.0.0.2'])
    @patch.object(ceph_hooks, 'get_networks', lambda *args: "")
    @patch.object(ceph, 'config')
    @patch.object(ceph_hooks, 'config')
    def test_get_ceph_context_filestore_old(self, mock_config, mock_config2):
        config = copy.deepcopy(CHARM_CONFIG)
        mock_config.side_effect = lambda key: config[key]
        mock_config2.side_effect = lambda key: config[key]
        ctxt = ceph_hooks.get_ceph_context()
        expected = {'auth_supported': False,
                    'ceph_cluster_network': '',
                    'ceph_public_network': '',
                    'cluster_addr': '10.1.0.1',
                    'dio': 'true',
                    'fsid': '1234',
                    'loglevel': 1,
                    'mon_hosts': '10.0.0.1 10.0.0.2',
                    'old_auth': False,
                    'crush_initial_weight': '0',
                    'osd_journal_size': 1024,
                    'osd_max_backfills': 1,
                    'osd_recovery_max_active': 2,
                    'osd_from_client': OrderedDict(),
                    'osd_from_client_conflict': OrderedDict(),
                    'public_addr': '10.0.0.1',
                    'short_object_len': True,
                    'upgrade_in_progress': False,
                    'use_syslog': 'true',
                    'bdev_discard': True,
                    'bluestore': False,
                    'bluestore_experimental': True,
                    'bluestore_block_wal_size': 0,
                    'bluestore_block_db_size': 0}
        self.assertEqual(ctxt, expected)

    @patch.object(ceph_hooks.ch_context, 'CephBlueStoreCompressionContext',
                  lambda: lambda: {})
    @patch.object(ceph_hooks.ch_ceph, 'get_osd_settings', lambda *args: {})
    @patch.object(ceph_hooks, 'get_fsid', lambda *args: '1234')
    @patch.object(ceph_hooks, 'get_auth', lambda *args: False)
    @patch.object(ceph_hooks, 'get_public_addr', lambda *args: "10.0.0.1")
    @patch.object(ceph_hooks, 'get_cluster_addr', lambda *args: "10.1.0.1")
    @patch.object(ceph_hooks, 'cmp_pkgrevno', lambda *args: 1)
    @patch.object(ceph_hooks, 'get_mon_hosts', lambda *args: ['10.0.0.1',
                                                              '10.0.0.2'])
    @patch.object(ceph_hooks, 'get_networks', lambda *args: "")
    @patch.object(ceph, 'config')
    @patch.object(ceph_hooks, 'config')
    def test_get_ceph_context_bluestore(self, mock_config, mock_config2):
        config = copy.deepcopy(CHARM_CONFIG)
        config['bluestore'] = True
        BLUESTORE_WAL = '/dev/sdb /dev/sdc'
        BLUESTORE_DB = '/dev/sdb /dev/sdc'
        config['bluestore-block-wal-size'] = BLUESTORE_WAL_TEST_SIZE
        config['bluestore-block-db-size'] = BLUESTORE_DB_TEST_SIZE
        config['bluestore-wal'] = BLUESTORE_WAL
        config['bluestore-db'] = BLUESTORE_DB
        mock_config.side_effect = lambda key: config[key]
        mock_config2.side_effect = lambda key: config[key]
        ctxt = ceph_hooks.get_ceph_context()
        expected = {'auth_supported': False,
                    'ceph_cluster_network': '',
                    'ceph_public_network': '',
                    'cluster_addr': '10.1.0.1',
                    'dio': 'true',
                    'fsid': '1234',
                    'loglevel': 1,
                    'mon_hosts': '10.0.0.1 10.0.0.2',
                    'old_auth': False,
                    'crush_initial_weight': '0',
                    'osd_journal_size': 1024,
                    'osd_max_backfills': 1,
                    'osd_recovery_max_active': 2,
                    'osd_from_client': OrderedDict(),
                    'osd_from_client_conflict': OrderedDict(),
                    'public_addr': '10.0.0.1',
                    'short_object_len': True,
                    'upgrade_in_progress': False,
                    'use_syslog': 'true',
                    'bdev_discard': True,
                    'bluestore': True,
                    'bluestore_experimental': False,
                    'bluestore_block_wal_size': BLUESTORE_WAL_TEST_SIZE,
                    'bluestore_block_db_size': BLUESTORE_DB_TEST_SIZE}
        self.assertEqual(ctxt, expected)

    @patch.object(ceph_hooks.ch_context, 'CephBlueStoreCompressionContext',
                  lambda: lambda: {})
    @patch.object(ceph_hooks.ch_ceph, 'get_osd_settings', lambda *args: {})
    @patch.object(ceph_hooks, 'get_fsid', lambda *args: '1234')
    @patch.object(ceph_hooks, 'get_auth', lambda *args: False)
    @patch.object(ceph_hooks, 'get_public_addr', lambda *args: "10.0.0.1")
    @patch.object(ceph_hooks, 'get_cluster_addr', lambda *args: "10.1.0.1")
    @patch.object(ceph_hooks, 'cmp_pkgrevno',
                  lambda pkg, ver: -1 if ver == '12.1.0' else 1)
    @patch.object(ceph_hooks, 'get_mon_hosts', lambda *args: ['10.0.0.1',
                                                              '10.0.0.2'])
    @patch.object(ceph_hooks, 'get_networks', lambda *args: "")
    @patch.object(ceph, 'config')
    @patch.object(ceph_hooks, 'config')
    def test_get_ceph_context_bluestore_old(self, mock_config, mock_config2):
        self.maxDiff = None
        config = copy.deepcopy(CHARM_CONFIG)
        config['bluestore'] = True
        config['bluestore-block-wal-size'] = BLUESTORE_WAL_TEST_SIZE
        config['bluestore-block-db-size'] = BLUESTORE_DB_TEST_SIZE
        mock_config.side_effect = lambda key: config[key]
        mock_config2.side_effect = lambda key: config[key]
        ctxt = ceph_hooks.get_ceph_context()
        expected = {'auth_supported': False,
                    'ceph_cluster_network': '',
                    'ceph_public_network': '',
                    'cluster_addr': '10.1.0.1',
                    'dio': 'true',
                    'fsid': '1234',
                    'loglevel': 1,
                    'mon_hosts': '10.0.0.1 10.0.0.2',
                    'old_auth': False,
                    'crush_initial_weight': '0',
                    'osd_journal_size': 1024,
                    'osd_max_backfills': 1,
                    'osd_recovery_max_active': 2,
                    'osd_from_client': OrderedDict(),
                    'osd_from_client_conflict': OrderedDict(),
                    'public_addr': '10.0.0.1',
                    'short_object_len': True,
                    'upgrade_in_progress': False,
                    'use_syslog': 'true',
                    'bdev_discard': True,
                    'bluestore': True,
                    'bluestore_experimental': True,
                    'bluestore_block_wal_size': BLUESTORE_WAL_TEST_SIZE,
                    'bluestore_block_db_size': BLUESTORE_DB_TEST_SIZE}
        self.assertEqual(ctxt, expected)

    @patch.object(ceph_hooks.ch_context, 'CephBlueStoreCompressionContext',
                  lambda: lambda: {})
    @patch.object(ceph_hooks.ch_ceph, 'get_osd_settings', lambda *args: {})
    @patch.object(ceph_hooks, 'get_fsid', lambda *args: '1234')
    @patch.object(ceph_hooks, 'get_auth', lambda *args: False)
    @patch.object(ceph_hooks, 'get_public_addr', lambda *args: "10.0.0.1")
    @patch.object(ceph_hooks, 'get_cluster_addr', lambda *args: "10.1.0.1")
    @patch.object(ceph_hooks, 'cmp_pkgrevno', lambda *args: 1)
    @patch.object(ceph_hooks, 'get_mon_hosts', lambda *args: ['10.0.0.1',
                                                              '10.0.0.2'])
    @patch.object(ceph_hooks, 'get_networks', lambda *args: "")
    @patch.object(ceph, 'config')
    @patch.object(ceph_hooks, 'config')
    def test_get_ceph_context_w_config_flags(self, mock_config, mock_config2):
        config = copy.deepcopy(CHARM_CONFIG)
        config['config-flags'] = '{"osd": {"osd max write size": 1024}}'
        mock_config.side_effect = lambda key: config[key]
        mock_config2.side_effect = lambda key: config[key]
        ctxt = ceph_hooks.get_ceph_context()
        expected = {'auth_supported': False,
                    'ceph_cluster_network': '',
                    'ceph_public_network': '',
                    'cluster_addr': '10.1.0.1',
                    'dio': 'true',
                    'fsid': '1234',
                    'loglevel': 1,
                    'mon_hosts': '10.0.0.1 10.0.0.2',
                    'old_auth': False,
                    'osd': OrderedDict([('osd max write size', 1024)]),
                    'crush_initial_weight': '0',
                    'osd_journal_size': 1024,
                    'osd_max_backfills': 1,
                    'osd_recovery_max_active': 2,
                    'osd_from_client': OrderedDict(),
                    'osd_from_client_conflict': OrderedDict(),
                    'public_addr': '10.0.0.1',
                    'short_object_len': True,
                    'upgrade_in_progress': False,
                    'use_syslog': 'true',
                    'bdev_discard': True,
                    'bluestore': False,
                    'bluestore_experimental': False,
                    'bluestore_block_wal_size': 0,
                    'bluestore_block_db_size': 0}
        self.assertEqual(ctxt, expected)

    @patch.object(ceph_hooks.ch_context, 'CephBlueStoreCompressionContext',
                  lambda: lambda: {})
    @patch.object(ceph_hooks.ch_ceph, 'get_osd_settings', lambda *args: {})
    @patch.object(ceph_hooks, 'get_fsid', lambda *args: '1234')
    @patch.object(ceph_hooks, 'get_auth', lambda *args: False)
    @patch.object(ceph_hooks, 'get_public_addr', lambda *args: "10.0.0.1")
    @patch.object(ceph_hooks, 'get_cluster_addr', lambda *args: "10.1.0.1")
    @patch.object(ceph_hooks, 'cmp_pkgrevno', lambda *args: 1)
    @patch.object(ceph_hooks, 'get_mon_hosts', lambda *args: ['10.0.0.1',
                                                              '10.0.0.2'])
    @patch.object(ceph_hooks, 'get_networks', lambda *args: "")
    @patch.object(ceph, 'config')
    @patch.object(ceph_hooks, 'config')
    def test_get_ceph_context_w_config_flags_invalid(self, mock_config,
                                                     mock_config2):
        config = copy.deepcopy(CHARM_CONFIG)
        config['config-flags'] = ('{"osd": {"osd max write size": 1024},'
                                  '"foo": "bar"}')
        mock_config.side_effect = lambda key: config[key]
        mock_config2.side_effect = lambda key: config[key]
        ctxt = ceph_hooks.get_ceph_context()
        expected = {'auth_supported': False,
                    'ceph_cluster_network': '',
                    'ceph_public_network': '',
                    'cluster_addr': '10.1.0.1',
                    'dio': 'true',
                    'fsid': '1234',
                    'loglevel': 1,
                    'mon_hosts': '10.0.0.1 10.0.0.2',
                    'old_auth': False,
                    'osd': OrderedDict([('osd max write size', 1024)]),
                    'crush_initial_weight': '0',
                    'osd_journal_size': 1024,
                    'osd_max_backfills': 1,
                    'osd_recovery_max_active': 2,
                    'osd_from_client': OrderedDict(),
                    'osd_from_client_conflict': OrderedDict(),
                    'public_addr': '10.0.0.1',
                    'short_object_len': True,
                    'upgrade_in_progress': False,
                    'use_syslog': 'true',
                    'bdev_discard': True,
                    'bluestore': False,
                    'bluestore_experimental': False,
                    'bluestore_block_wal_size': 0,
                    'bluestore_block_db_size': 0}
        self.assertEqual(ctxt, expected)

    @patch.object(ceph_hooks.ch_context, 'CephBlueStoreCompressionContext')
    @patch.object(ceph_hooks.ch_ceph, 'get_osd_settings', lambda *args: {})
    @patch.object(ceph_hooks, 'get_fsid', lambda *args: '1234')
    @patch.object(ceph_hooks, 'get_auth', lambda *args: False)
    @patch.object(ceph_hooks, 'get_public_addr', lambda *args: "10.0.0.1")
    @patch.object(ceph_hooks, 'get_cluster_addr', lambda *args: "10.1.0.1")
    @patch.object(ceph_hooks, 'cmp_pkgrevno', lambda *args: 1)
    @patch.object(ceph_hooks, 'get_mon_hosts', lambda *args: ['10.0.0.1',
                                                              '10.0.0.2'])
    @patch.object(ceph_hooks, 'get_networks', lambda *args: "")
    @patch.object(ceph, 'config')
    @patch.object(ceph_hooks, 'config')
    def test_get_ceph_context_bluestore_compression(
            self, mock_config, mock_config2, mock_bluestore_compression):
        config = copy.deepcopy(CHARM_CONFIG)
        mock_config.side_effect = lambda key: config[key]
        mock_config2.side_effect = lambda key: config[key]
        mock_bluestore_compression().return_value = {
            'fake-bluestore-compression-key': 'fake-value'}
        ctxt = ceph_hooks.get_ceph_context()
        expected = {'auth_supported': False,
                    'ceph_cluster_network': '',
                    'ceph_public_network': '',
                    'cluster_addr': '10.1.0.1',
                    'dio': 'true',
                    'fsid': '1234',
                    'loglevel': 1,
                    'mon_hosts': '10.0.0.1 10.0.0.2',
                    'old_auth': False,
                    'crush_initial_weight': '0',
                    'osd_journal_size': 1024,
                    'osd_max_backfills': 1,
                    'osd_recovery_max_active': 2,
                    'osd_from_client': OrderedDict(),
                    'osd_from_client_conflict': OrderedDict(),
                    'public_addr': '10.0.0.1',
                    'short_object_len': True,
                    'upgrade_in_progress': False,
                    'use_syslog': 'true',
                    'bdev_discard': True,
                    'bluestore': False,
                    'bluestore_experimental': False,
                    'bluestore_block_wal_size': 0,
                    'bluestore_block_db_size': 0,
                    'fake-bluestore-compression-key': 'fake-value'}
        self.assertEqual(ctxt, expected)

    @patch.object(ceph_hooks, 'ceph')
    @patch.object(ceph_hooks, 'service_restart')
    @patch.object(ceph_hooks, 'service_reload')
    @patch.object(ceph_hooks, 'copy_profile_into_place')
    @patch.object(ceph_hooks, 'CephOsdAppArmorContext')
    @patch.object(ceph_hooks, 'config')
    def test_install_apparmor_profile(self, mock_config,
                                      mock_apparmor_context,
                                      mock_copy_profile_into_place,
                                      mock_service_reload,
                                      mock_service_restart,
                                      mock_ceph):
        '''Apparmor profile reloaded when config changes (upstart)'''
        m_config = MagicMock()
        m_config.changed.return_value = True
        mock_config.return_value = m_config
        m_aa_context = MagicMock()
        mock_apparmor_context.return_value = m_aa_context
        mock_ceph.systemd.return_value = False
        mock_copy_profile_into_place.return_value = False

        ceph_hooks.install_apparmor_profile()

        m_aa_context.setup_aa_profile.assert_called()
        mock_copy_profile_into_place.assert_called()
        mock_service_restart.assert_called_with('ceph-osd-all')
        m_config.changed.assert_called_with('aa-profile-mode')
        mock_service_reload.assert_called_with('apparmor')

    @patch.object(ceph_hooks, 'ceph')
    @patch.object(ceph_hooks, 'service_restart')
    @patch.object(ceph_hooks, 'service_reload')
    @patch.object(ceph_hooks, 'copy_profile_into_place')
    @patch.object(ceph_hooks, 'CephOsdAppArmorContext')
    @patch.object(ceph_hooks, 'config')
    def test_install_apparmor_profile_systemd(self, mock_config,
                                              mock_apparmor_context,
                                              mock_copy_profile_into_place,
                                              mock_service_reload,
                                              mock_service_restart,
                                              mock_ceph):
        '''Apparmor profile reloaded when config changes (systemd)'''
        m_config = MagicMock()
        m_config.changed.return_value = True
        mock_config.return_value = m_config
        m_aa_context = MagicMock()
        mock_apparmor_context.return_value = m_aa_context
        mock_ceph.systemd.return_value = True
        mock_ceph.get_local_osd_ids.return_value = [0, 1, 2]
        mock_copy_profile_into_place.return_value = False

        ceph_hooks.install_apparmor_profile()

        m_aa_context.setup_aa_profile.assert_called()
        mock_copy_profile_into_place.assert_called()
        m_config.changed.assert_called_with('aa-profile-mode')
        mock_service_reload.assert_called_with('apparmor')
        mock_service_restart.assert_has_calls([
            call('ceph-osd@0'),
            call('ceph-osd@1'),
            call('ceph-osd@2'),
        ])

    @patch.object(ceph_hooks, 'ceph')
    @patch.object(ceph_hooks, 'service_restart')
    @patch.object(ceph_hooks, 'service_reload')
    @patch.object(ceph_hooks, 'copy_profile_into_place')
    @patch.object(ceph_hooks, 'CephOsdAppArmorContext')
    @patch.object(ceph_hooks, 'config')
    def test_install_apparmor_profile_new_install(self, mock_config,
                                                  mock_apparmor_context,
                                                  mock_copy_profile_into_place,
                                                  mock_service_reload,
                                                  mock_service_restart,
                                                  mock_ceph):
        '''Apparmor profile always reloaded on fresh install'''
        m_config = MagicMock()
        m_config.changed.return_value = True
        mock_config.return_value = m_config
        m_aa_context = MagicMock()
        mock_apparmor_context.return_value = m_aa_context
        mock_ceph.systemd.return_value = True
        mock_ceph.get_local_osd_ids.return_value = [0, 1, 2]
        mock_copy_profile_into_place.return_value = True

        ceph_hooks.install_apparmor_profile()

        m_aa_context.setup_aa_profile.assert_called()
        mock_copy_profile_into_place.assert_called()
        m_config.changed.assert_not_called()
        mock_service_reload.assert_called_with('apparmor')
        mock_service_restart.assert_has_calls([
            call('ceph-osd@0'),
            call('ceph-osd@1'),
            call('ceph-osd@2'),
        ])

    @patch.object(ceph_hooks, 'is_block_device')
    @patch.object(ceph_hooks, 'storage_list')
    @patch.object(ceph_hooks, 'config')
    def test_get_devices(self, mock_config, mock_storage_list,
                         mock_is_block_device):
        '''Devices returned as expected'''
        config = {'osd-devices': '/dev/vda /dev/vdb'}
        mock_config.side_effect = lambda key: config[key]
        mock_storage_list.return_value = []
        mock_is_block_device.return_value = True
        devices = ceph_hooks.get_devices()
        self.assertEqual(devices, ['/dev/vda', '/dev/vdb'])

    @patch.object(ceph_hooks, 'is_block_device')
    @patch.object(ceph_hooks, 'get_blacklist')
    @patch.object(ceph_hooks, 'storage_list')
    @patch.object(ceph_hooks, 'config')
    def test_get_devices_blacklist(self, mock_config, mock_storage_list,
                                   mock_get_blacklist, mock_is_block_device):
        '''Devices returned as expected when blacklist in effect'''
        config = {'osd-devices': '/dev/vda /dev/vdb'}
        mock_config.side_effect = lambda key: config[key]
        mock_storage_list.return_value = []
        mock_get_blacklist.return_value = ['/dev/vda']
        mock_is_block_device.return_value = True
        devices = ceph_hooks.get_devices()
        mock_storage_list.assert_called()
        mock_get_blacklist.assert_called()
        self.assertEqual(devices, ['/dev/vdb'])

    @patch.object(ceph_hooks, 'log')
    @patch.object(ceph_hooks, 'config')
    @patch('os.environ')
    def test_az_info_unset(self, environ, config, log):
        config.return_value = None
        environ.get.return_value = None

        self.assertEqual(ceph_hooks.az_info(), None)

        config.assert_called_with('availability_zone')
        environ.get.assert_called_with('JUJU_AVAILABILITY_ZONE')

    @patch.object(ceph_hooks, 'log')
    @patch.object(ceph_hooks, 'config')
    @patch('os.environ')
    def test_az_info_config(self, environ, config, log):
        config.return_value = 'dc-01'
        environ.get.return_value = None

        self.assertEqual(ceph_hooks.az_info(),
                         ' row=dc-01')

        config.assert_called_with('availability_zone')
        environ.get.assert_called_with('JUJU_AVAILABILITY_ZONE')

    @patch.object(ceph_hooks, 'log')
    @patch.object(ceph_hooks, 'config')
    @patch('os.environ')
    def test_az_info_juju_az(self, environ, config, log):
        config.return_value = 'dc-01'
        environ.get.return_value = 'zone1'

        self.assertEqual(ceph_hooks.az_info(),
                         ' rack=zone1 row=dc-01')

        config.assert_called_with('availability_zone')
        environ.get.assert_called_with('JUJU_AVAILABILITY_ZONE')

    @patch.object(ceph_hooks, 'log')
    @patch.object(ceph_hooks, 'config')
    @patch('os.environ')
    def test_az_info_default_remap(self, environ, config, log):
        config.return_value = 'default'
        environ.get.return_value = 'default'

        self.assertEqual(ceph_hooks.az_info(),
                         ' rack=default-rack row=default-row')

        config.assert_called_with('availability_zone')
        environ.get.assert_called_with('JUJU_AVAILABILITY_ZONE')

    @patch.object(ceph_hooks, 'is_container')
    @patch.object(ceph_hooks, 'subprocess')
    @patch.object(ceph_hooks, 'shutil')
    def test_install_udev_rules(self, shutil, subprocess, is_container):
        is_container.return_value = False
        ceph_hooks.install_udev_rules()
        shutil.copy.assert_called_once_with(
            'files/udev/95-charm-ceph-osd.rules',
            '/lib/udev/rules.d'
        )
        subprocess.check_call.assert_called_once_with(
            ['udevadm', 'control', '--reload-rules']
        )

    @patch.object(ceph_hooks, 'is_container')
    @patch.object(ceph_hooks, 'subprocess')
    @patch.object(ceph_hooks, 'shutil')
    def test_install_udev_rules_container(self, shutil, subprocess,
                                          is_container):
        is_container.return_value = True
        ceph_hooks.install_udev_rules()
        shutil.copy.assert_not_called()
        subprocess.check_call.assert_not_called()

    @patch.object(ceph_hooks, 'config')
    @patch.object(ceph_hooks, 'cmp_pkgrevno')
    def test_use_short_objects(self, mock_cmp_pkgrevno, mock_config):

        def fake_config(key):
            return config.get(key, None)

        mock_config.side_effect = fake_config
        mock_cmp_pkgrevno.return_value = True

        config = {'osd-devices': '/dev/sdb /dev/sdc', 'osd-format': 'ext4'}
        self.assertTrue(ceph_hooks.use_short_objects())

        config = {'osd-devices': '/dev/sdb /dev/sdc', 'osd-format': 'xfs'}
        self.assertFalse(ceph_hooks.use_short_objects())

        config = {'osd-devices': '/srv/osd', 'osd-format': 'xfs'}
        self.assertTrue(ceph_hooks.use_short_objects())

        config = {'osd-devices': '/srv/osd', 'osd-format': 'ext4'}
        self.assertTrue(ceph_hooks.use_short_objects())

    @patch.object(ceph_hooks, 'write_file')
    @patch.object(ceph_hooks.ceph, 'ceph_user')
    @patch.object(ceph_hooks, 'install_alternative')
    @patch.object(ceph_hooks, 'render_template')
    @patch.object(ceph_hooks, 'get_ceph_context')
    @patch.object(ceph_hooks, 'service_name')
    @patch.object(ceph_hooks, 'mkdir')
    def test_emit_ceph_conf(self, mock_mkdir, mock_service_name,
                            mock_get_ceph_context, mock_render_template,
                            mock_install_alternative, mock_ceph_user,
                            mock_write_file):
        mock_service_name.return_value = 'testsvc'
        mock_ceph_user.return_value = 'ceph'
        mock_get_ceph_context.return_value = {}
        mock_render_template.return_value = "awesome ceph config"

        ceph_hooks.emit_cephconf()

        self.assertTrue(mock_write_file.called)
        self.assertTrue(mock_install_alternative.called)

    @patch.object(ceph_hooks, 'should_enable_discard')
    @patch.object(ceph_hooks, 'config')
    def test_get_bdev_enable_discard(self, mock_config,
                                     mock_should_enable_discard):
        mock_should_enable_discard.return_value = True
        config = {'bdev-enable-discard': 'xxx',
                  'osd-devices': '/dev/vdb'}
        mock_config.side_effect = lambda key: config[key]
        self.assertRaises(ValueError, ceph_hooks.get_bdev_enable_discard)

        for value, expected in [('enable', True),
                                ('enabled', True),
                                ('disable', False),
                                ('disabled', False),
                                ('auto', True)]:
            config['bdev-enable-discard'] = value
            self.assertEqual(ceph_hooks.get_bdev_enable_discard(), expected)


@patch.object(ceph_hooks, 'local_unit')
@patch.object(ceph_hooks, 'relation_get')
@patch.object(ceph_hooks, 'relation_set')
@patch.object(ceph_hooks, 'prepare_disks_and_activate')
@patch.object(ceph_hooks, 'get_relation_ip')
@patch.object(ceph_hooks, 'socket')
class SecretsStorageTestCase(unittest.TestCase):

    def test_secrets_storage_relation_joined(self,
                                             _socket,
                                             _get_relation_ip,
                                             _prepare_disks_and_activate,
                                             _relation_set,
                                             _relation_get,
                                             _local_unit):
        _local_unit.return_value = 'ceph-osd/0'
        _get_relation_ip.return_value = '10.23.1.2'
        _socket.gethostname.return_value = 'testhost'
        ceph_hooks.secrets_storage_joined()
        _get_relation_ip.assert_called_with('secrets-storage')
        _relation_set.assert_called_with(
            relation_id=None,
            secret_backend='charm-vaultlocker',
            isolated=True,
            access_address='10.23.1.2',
            unit_name='ceph-osd/0',
            hostname='testhost'
        )
        _socket.gethostname.assert_called_once_with()

    def test_secrets_storage_relation_changed(self,
                                              _socket,
                                              _get_relation_ip,
                                              _prepare_disks_and_activate,
                                              _relation_set,
                                              _relation_get,
                                              _local_unit):
        _local_unit.return_value = 'ceph-osd/0'
        _relation_get.return_value = None
        ceph_hooks.secrets_storage_changed()
        _prepare_disks_and_activate.assert_called_once_with()


@patch.object(ceph_hooks, 'cmp_pkgrevno')
@patch.object(ceph_hooks, 'config')
class VaultLockerTestCase(unittest.TestCase):

    def test_use_vaultlocker(self, _config, _cmp_pkgrevno):
        _test_data = {
            'osd-encrypt': True,
            'osd-encrypt-keymanager': 'vault',
        }
        _config.side_effect = lambda x: _test_data.get(x)
        _cmp_pkgrevno.return_value = 1
        self.assertTrue(ceph_hooks.use_vaultlocker())

    def test_use_vaultlocker_no_encryption(self, _config, _cmp_pkgrevno):
        _test_data = {
            'osd-encrypt': False,
            'osd-encrypt-keymanager': 'vault',
        }
        _config.side_effect = lambda x: _test_data.get(x)
        _cmp_pkgrevno.return_value = 1
        self.assertFalse(ceph_hooks.use_vaultlocker())

    def test_use_vaultlocker_not_vault(self, _config, _cmp_pkgrevno):
        _test_data = {
            'osd-encrypt': True,
            'osd-encrypt-keymanager': 'ceph',
        }
        _config.side_effect = lambda x: _test_data.get(x)
        _cmp_pkgrevno.return_value = 1
        self.assertFalse(ceph_hooks.use_vaultlocker())

    def test_use_vaultlocker_old_version(self, _config, _cmp_pkgrevno):
        _test_data = {
            'osd-encrypt': True,
            'osd-encrypt-keymanager': 'vault',
        }
        _config.side_effect = lambda x: _test_data.get(x)
        _cmp_pkgrevno.return_value = -1
        self.assertRaises(ValueError,
                          ceph_hooks.use_vaultlocker)
