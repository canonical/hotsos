import os
import tempfile

from . import utils

from hotsos.core.config import setup_config
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


class MySQLTestsBase(utils.BaseTestCase):

    def setUp(self):
        super().setUp()
        setup_config(PLUGIN_NAME='mysql')


class TestMySQLSummary(MySQLTestsBase):

    def test_summary(self):
        with tempfile.TemporaryDirectory() as dtmp:
            setup_config(DATA_ROOT=dtmp)
            content = {'sos_commands/systemd/systemctl_list-units':
                       SYSTEMD_UNITS,
                       'sos_commands/systemd/systemctl_list-unit-files':
                       SYSTEMD_UNIT_FILES,
                       'sos_commands/dpkg/dpkg_-l': DPKG_L}
            for path, data in content.items():
                fpath = os.path.join(dtmp, path)
                os.makedirs(os.path.dirname(fpath), exist_ok=True)
                with open(fpath, 'w') as fd:
                    fd.write(data)

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

    def test_all(self):
        # This is a dummy test since there are no scenarios defined yet. Once
        # we add a scenario we should replace this test with a real test.
        YScenarioChecker()()
