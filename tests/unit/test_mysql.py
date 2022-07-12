from unittest import mock

from . import utils

from hotsos.core.config import setup_config
from hotsos.core.host_helpers.systemd import SystemdService
from hotsos.core.issues import IssuesManager
from hotsos.plugin_extensions.mysql import summary
from hotsos.core.ycheck.scenarios import YScenarioChecker


SYSTEMD_UNITS = """
  jujud-unit-hacluster-mysql-1.service   loaded active     running   juju unit agent for hacluster-mysql/1
  jujud-unit-mysql-1.service             loaded active     running   juju unit agent for mysql/1
  mysql.service                          loaded active     running   Percona XtraDB Cluster daemon
"""  # noqa

SYSTEMD_UNIT_FILES = """
jujud-unit-hacluster-mysql-1.service   enabled
jujud-unit-mysql-1.service             enabled
mysql.service                          enabled
mysql@.service                         disabled
"""  # noqa

DPKG_L = """
ii  libdbd-mysql-perl                 4.046-1                                        amd64        Perl5 database interface to the MariaDB/MySQL database
ii  libmysqlclient20:amd64            5.7.36-0ubuntu0.18.04.1                        amd64        MySQL database client library
ii  mysql-client                      5.7.36-0ubuntu0.18.04.1                        all          MySQL database client (metapackage depending on the latest version)
ii  mysql-client-5.7                  5.7.36-0ubuntu0.18.04.1                        amd64        MySQL database client binaries
ii  mysql-client-core-5.7             5.7.36-0ubuntu0.18.04.1                        amd64        MySQL database core client binaries
ii  mysql-common                      5.8+1.0.4                                      all          MySQL database common files, e.g. /etc/mysql/my.cnf
ii  python3-mysqldb                   1.3.10-1build1                                 amd64        Python interface to MySQL
"""  # noqa

DPKG_L_ROUTER = """
ii  mysql-router                      8.0.29-0ubuntu0.21.10.1                        amd64        route connections from MySQL clients to MySQL servers
""" # noqa

FREE_BLOCKS_DIFFICULT = r"""
Aug  3 08:32:23 [Note] InnoDB: Starting a batch to recover 9962 pages from redo log.
Aug  3 08:32:23 [Warning] InnoDB: Difficult to find free blocks in the buffer pool (21 search iterations)! 21 failed attempts to flush a page! Consider increasing innodb_buffer_pool_size. Pending flushes (fsync) log: 0; buffer pool: 0. 582296 OS file reads, 504266 OS file writes, 2396 OS fsyncs.
"""  # noqa


class MySQLTestsBase(utils.BaseTestCase):

    def setUp(self):
        super().setUp()
        setup_config(PLUGIN_NAME='mysql')


class TestMySQLSummary(MySQLTestsBase):

    @utils.create_test_files({'sos_commands/systemd/systemctl_list-units':
                              SYSTEMD_UNITS,
                              'sos_commands/systemd/systemctl_list-unit-files':
                              SYSTEMD_UNIT_FILES,
                              'sos_commands/dpkg/dpkg_-l': DPKG_L})
    def test_summary(self):
        expected = {'dpkg': [
                        'mysql-client 5.7.36-0ubuntu0.18.04.1',
                        'mysql-common 5.8+1.0.4'],
                    'services': {
                        'ps': [],
                        'systemd': {
                            'enabled': ['mysql']}}}
        inst = summary.MySQLSummary()
        self.assertEqual(self.part_output_to_actual(inst.output),
                         expected)


class TestMySQLScenarios(MySQLTestsBase):

    @mock.patch(
        'hotsos.core.host_helpers.systemd.ServiceChecksBase.services', {
            'mysql-router':
            SystemdService('mysql-router', 'enabled')
        })
    @mock.patch('hotsos.core.host_helpers.packaging.CLIHelper')
    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('mysql/bugs.yaml'))
    def test_1971565(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.dpkg_l.return_value = \
            DPKG_L_ROUTER.splitlines()

        YScenarioChecker()()
        expected = {
            'bugs-detected': [
                {'id': 'https://bugs.launchpad.net/bugs/1971565',
                 'desc': ("Installed package 'mysql-router' with "
                          "version 8.0.29-0ubuntu0.21.10.1 has a "
                          "known bug that prevents mysql-router from "
                          "starting. Please upgrade to the latest "
                          "version to fix this issue."),
                 'origin': 'mysql.01part'}
            ]
        }
        self.assertEqual(IssuesManager().load_bugs(), expected)

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('mysql/bugs.yaml'))
    @utils.create_test_files({'var/log/mysql/error.log':
                              FREE_BLOCKS_DIFFICULT})
    def test_372017_invoked(self):
        YScenarioChecker()()
        expected = {
            'bugs-detected': [
                {'id': 'https://bugs.launchpad.net/bugs/372017',
                 'desc': ("mariabackup ran out of innodb buffer pool. "
                          "See https://jira.mariadb.org/browse/MDEV-26784"),
                 'origin': 'mysql.01part'}
            ]
        }
        self.assertEqual(IssuesManager().load_bugs(), expected)

    @mock.patch('hotsos.core.host_helpers.packaging.CLIHelper')
    @mock.patch('hotsos.core.plugins.mysql.MySQLConfig')
    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('mysql/mysql_connections.yaml'))
    def test_mysql_connections_missing_nofile(self, mock_config, mock_cli):
        mock_cli.return_value = mock.MagicMock()
        mock_cli.return_value.dpkg_l.return_value = \
            ['ii percona-xtradb-cluster-server 5.7.20-29.24-0ubuntu2.1 all']

        def fake_get(key, **_kwargs):
            return {'max_connections': '4191'}.get(key)

        mock_config.return_value = mock.MagicMock()
        mock_config.return_value.get.side_effect = fake_get

        YScenarioChecker()()
        expected = {'potential-issues': {'MySQLWarnings': [
            'MySQL max_connections is higher than 4190 but there is no '
            'charm-nofile.conf which means that the higher value is not '
            'being honoured. See LP 1905366 for more information. '
            '(origin=mysql.01part)']}}
        self.assertEqual(IssuesManager().load_issues(), expected)

    @mock.patch('hotsos.core.host_helpers.packaging.CLIHelper')
    @mock.patch('hotsos.core.plugins.mysql.MySQLConfig')
    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('mysql/mysql_connections.yaml'))
    @utils.create_test_files(
        {'etc/systemd/system/mysql.service.d/charm-nofile.conf': ''})
    def test_mysql_connections_w_nofile(self, mock_config, mock_cli):
        mock_cli.return_value = mock.MagicMock()
        mock_cli.return_value.dpkg_l.return_value = \
            ['ii percona-xtradb-cluster-server 5.7.20-29.24-0ubuntu2.1 all']

        def fake_get(key, **_kwargs):
            return {'max_connections': '4191'}.get(key)

        mock_config.return_value = mock.MagicMock()
        mock_config.return_value.get.side_effect = fake_get

        YScenarioChecker()()
        expected = {}
        self.assertEqual(IssuesManager().load_issues(), expected)

    @mock.patch(
        'hotsos.core.host_helpers.systemd.ServiceChecksBase.services', {
            'mysql-router':
            SystemdService('mysql-router', 'enabled')
        })
    @mock.patch('hotsos.core.host_helpers.packaging.CLIHelper')
    @mock.patch('hotsos.core.plugins.mysql.MySQLRouterConfig')
    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('mysql/mysql_router.yaml'))
    def test_mysql_router(self, mock_config, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.dpkg_l.return_value = \
            DPKG_L_ROUTER.splitlines()

        def fake_get(key, **_kwargs):
            return {'client_ssl_mode': 'PREFERRED'}.get(key)

        mock_config.return_value = mock.MagicMock()
        mock_config.return_value.get.side_effect = fake_get

        YScenarioChecker()()
        expected = {
            'bugs-detected': [
                {'id': 'https://bugs.launchpad.net/bugs/1959861',
                 'desc': (
                     'This host is running MySQL Router '
                     'and has client_ssl_mode configured '
                     'but client_ssl_cert is not set. '
                     'This will cause mysql-router to error '
                     'when restarted.'),
                 'origin': 'mysql.01part'}
            ]
        }

        self.assertEqual(IssuesManager().load_bugs(), expected)

    @mock.patch(
        'hotsos.core.host_helpers.systemd.ServiceChecksBase.services', {
            'mysql-router':
            SystemdService('mysql-router', 'enabled')
        })
    @mock.patch('hotsos.core.host_helpers.packaging.CLIHelper')
    @mock.patch('hotsos.core.plugins.mysql.MySQLRouterConfig')
    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('mysql/mysql_router.yaml'))
    def test_mysql_router_not_affected(self, mock_config, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.dpkg_l.return_value = \
            DPKG_L_ROUTER.splitlines()

        def fake_get(key, **_kwargs):
            return {
                'client_ssl_mode': 'PREFERRED',
                'client_ssl_cert': 'exist'
            }.get(key)

        mock_config.return_value = mock.MagicMock()
        mock_config.return_value.get.side_effect = fake_get

        YScenarioChecker()()
        expected = {}

        self.assertEqual(IssuesManager().load_bugs(), expected)
