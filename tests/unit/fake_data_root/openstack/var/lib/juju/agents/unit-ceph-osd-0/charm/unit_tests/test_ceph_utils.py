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

import unittest

from unittest.mock import patch

with patch('charmhelpers.contrib.hardening.harden.harden') as mock_dec:
    mock_dec.side_effect = (lambda *dargs, **dkwargs: lambda f:
                            lambda *args, **kwargs: f(*args, **kwargs))
    import utils


class CephUtilsTestCase(unittest.TestCase):
    def setUp(self):
        super(CephUtilsTestCase, self).setUp()

    @patch('os.path.exists')
    @patch.object(utils, 'storage_list')
    @patch.object(utils, 'config')
    def test_get_journal_devices(self, mock_config, mock_storage_list,
                                 mock_os_path_exists):
        '''Devices returned as expected'''
        config = {'osd-journal': '/dev/vda /dev/vdb'}
        mock_config.side_effect = lambda key: config[key]
        mock_storage_list.return_value = []
        mock_os_path_exists.return_value = True
        devices = utils.get_journal_devices()
        mock_storage_list.assert_called()
        mock_os_path_exists.assert_called()
        self.assertEqual(devices, set(['/dev/vda', '/dev/vdb']))

    @patch('os.path.exists')
    @patch.object(utils, 'get_blacklist')
    @patch.object(utils, 'storage_list')
    @patch.object(utils, 'config')
    def test_get_journal_devices_blacklist(self, mock_config,
                                           mock_storage_list,
                                           mock_get_blacklist,
                                           mock_os_path_exists):
        '''Devices returned as expected when blacklist in effect'''
        config = {'osd-journal': '/dev/vda /dev/vdb'}
        mock_config.side_effect = lambda key: config[key]
        mock_storage_list.return_value = []
        mock_get_blacklist.return_value = ['/dev/vda']
        mock_os_path_exists.return_value = True
        devices = utils.get_journal_devices()
        mock_storage_list.assert_called()
        mock_os_path_exists.assert_called()
        mock_get_blacklist.assert_called()
        self.assertEqual(devices, set(['/dev/vdb']))

    @patch('os.path.exists')
    @patch.object(utils, 'is_sata30orless')
    def test_should_enable_discard_yes(self, mock_is_sata30orless,
                                       mock_os_path_exists):
        devices = ['/dev/sda', '/dev/vda', '/dev/nvme0n1']
        mock_os_path_exists.return_value = True
        mock_is_sata30orless.return_value = False
        ret = utils.should_enable_discard(devices)
        mock_os_path_exists.assert_called()
        mock_is_sata30orless.assert_called()
        self.assertEqual(ret, True)

    @patch('os.path.exists')
    @patch.object(utils, 'is_sata30orless')
    def test_should_enable_discard_no(self, mock_is_sata30orless,
                                      mock_os_path_exists):
        devices = ['/dev/sda', '/dev/vda', '/dev/nvme0n1']
        mock_os_path_exists.return_value = True
        mock_is_sata30orless.return_value = True
        ret = utils.should_enable_discard(devices)
        mock_os_path_exists.assert_called()
        mock_is_sata30orless.assert_called()
        self.assertEqual(ret, False)

    @patch('subprocess.check_output')
    def test_is_sata30orless_sata31(self, mock_subprocess_check_output):
        extcmd_output = (b'supressed text\nSATA Version is:  '
                         b'SATA 3.1, 6.0 Gb/s (current: 6.0 Gb/s)\n'
                         b'supressed text\n\n')
        mock_subprocess_check_output.return_value = extcmd_output
        ret = utils.is_sata30orless('/dev/sda')
        mock_subprocess_check_output.assert_called()
        self.assertEqual(ret, False)

    @patch('subprocess.check_output')
    def test_is_sata30orless_sata30(self, mock_subprocess_check_output):
        extcmd_output = (b'supressed text\nSATA Version is:  '
                         b'SATA 3.0, 6.0 Gb/s (current: 6.0 Gb/s)\n'
                         b'supressed text\n\n')
        mock_subprocess_check_output.return_value = extcmd_output
        ret = utils.is_sata30orless('/dev/sda')
        mock_subprocess_check_output.assert_called()
        self.assertEqual(ret, True)

    @patch('subprocess.check_output')
    def test_is_sata30orless_sata26(self, mock_subprocess_check_output):
        extcmd_output = (b'supressed text\nSATA Version is:  '
                         b'SATA 2.6, 3.0 Gb/s (current: 3.0 Gb/s)\n'
                         b'supressed text\n\n')
        mock_subprocess_check_output.return_value = extcmd_output
        ret = utils.is_sata30orless('/dev/sda')
        mock_subprocess_check_output.assert_called()
        self.assertEqual(ret, True)

    @patch.object(utils, "function_get")
    def test_raise_on_missing_arguments(self, mock_function_get):
        mock_function_get.return_value = None
        err_msg = "Action argument \"osds\" is missing"
        with self.assertRaises(RuntimeError, msg=err_msg):
            utils.parse_osds_arguments()

    @patch.object(utils, "function_get")
    def test_parse_service_ids(self, mock_function_get):
        mock_function_get.return_value = "1,2,3"
        expected_ids = {"1", "2", "3"}

        parsed = utils.parse_osds_arguments()
        self.assertEqual(parsed, expected_ids)

    @patch.object(utils, "function_get")
    def test_parse_service_ids_with_all(self, mock_function_get):
        mock_function_get.return_value = "1,2,all"
        expected_id = {utils.ALL}

        parsed = utils.parse_osds_arguments()
        self.assertEqual(parsed, expected_id)
