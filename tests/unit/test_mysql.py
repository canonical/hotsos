import os
from . import utils

from hotsos.core.config import HotSOSConfig
from hotsos.plugin_extensions.mysql import summary


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


class MySQLTestsBase(utils.BaseTestCase):

    def setUp(self):
        super().setUp()
        HotSOSConfig.plugin_name = 'mysql'
        HotSOSConfig.data_root = os.path.join(utils.TESTS_DIR,
                                              'fake_data_root/vault')


class TestMySQLSummary(MySQLTestsBase):

    @utils.create_data_root({'sos_commands/systemd/systemctl_list-units':
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


@utils.load_templated_tests('scenarios/mysql')
class TestMySQLScenarios(MySQLTestsBase):
    """
    Scenario tests can be written using YAML templates that are auto-loaded
    into this test runner. This is the recommended way to write tests for
    scenarios. It is however still possible to write the tests in Python if
    required. See defs/tests/README.md for more info.
    """
