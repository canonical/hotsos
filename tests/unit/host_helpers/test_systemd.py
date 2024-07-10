
from hotsos.core.host_helpers import systemd as host_systemd

from .. import utils


class TestSystemdHelper(utils.BaseTestCase):
    rsyslog_systemctl_status_template = r"""
* rsyslog.service - System Logging Service
     Loaded: loaded (/lib/systemd/system/rsyslog.service; enabled;)
     Active: active (running) since Wed 2022-02-09 22:38:17 {}; 17h ago

Feb 09 22:38:17 compute4 systemd[1]: Starting System Logging Service...

* secureboot-db.service - Secure Boot updates for DB and DBX"""

    def test_service_factory(self):
        svc = host_systemd.ServiceFactory().rsyslog
        self.assertEqual(svc.start_time_secs, 1644446297.0)

        self.assertIsNone(host_systemd.ServiceFactory().noexist)

    @utils.create_data_root(
        {},
        copy_from_original=['sos_commands/systemd/systemctl_list-units',
                            'sos_commands/systemd/systemctl_list-unit-files',
                            'sys/fs/cgroup/memory/system.slice',
                            'sos_commands/systemd/systemctl_status_--all'])
    def test_service_factory_no_journal(self):
        svc = host_systemd.ServiceFactory().rsyslog
        self.assertEqual(svc.start_time_secs, 1644446297.0)

        self.assertIsNone(host_systemd.ServiceFactory().noexist)

    @utils.create_data_root(
        {'sos_commands/systemd/systemctl_status_--all':
         rsyslog_systemctl_status_template.format("+08")},
        copy_from_original=['sos_commands/systemd/systemctl_list-units',
                            'sos_commands/systemd/systemctl_list-unit-files',
                            'sys/fs/cgroup/memory/system.slice'])
    def test_service_factory_no_journal_non_utc_plus8(self):
        svc = host_systemd.ServiceFactory().rsyslog
        # 2022-02-09 22:38:17 UTC+08 is 2022-02-09 14:38:17 UTC
        self.assertEqual(svc.start_time_secs, 1644417497.0)
        self.assertIsNone(host_systemd.ServiceFactory().noexist)

    @utils.create_data_root(
        {'sos_commands/systemd/systemctl_status_--all':
         rsyslog_systemctl_status_template.format("+0530")},
        copy_from_original=['sos_commands/systemd/systemctl_list-units',
                            'sos_commands/systemd/systemctl_list-unit-files',
                            'sys/fs/cgroup/memory/system.slice'])
    def test_service_factory_no_journal_non_utc_plus0530(self):
        svc = host_systemd.ServiceFactory().rsyslog
        # 2022-02-09 22:38:17 UTC+0530 is 2022-02-09 17:08:17 UTC
        self.assertEqual(svc.start_time_secs, 1644426497.0)
        self.assertIsNone(host_systemd.ServiceFactory().noexist)

    @utils.create_data_root(
        {'sos_commands/systemd/systemctl_status_--all':
         rsyslog_systemctl_status_template.format("-0730")},
        copy_from_original=['sos_commands/systemd/systemctl_list-units',
                            'sos_commands/systemd/systemctl_list-unit-files',
                            'sys/fs/cgroup/memory/system.slice'])
    def test_service_factory_no_journal_non_utc_minus0730(self):
        svc = host_systemd.ServiceFactory().rsyslog
        # 2022-02-09 22:38:17 UTC-0730 is 2022-02-09 17:08:17 UTC
        self.assertEqual(svc.start_time_secs, 1644473297.0)
        self.assertIsNone(host_systemd.ServiceFactory().noexist)

    @utils.create_data_root(
        {'sos_commands/systemd/systemctl_status_--all':
         rsyslog_systemctl_status_template.format("HKT")},
        copy_from_original=['sos_commands/systemd/systemctl_list-units',
                            'sos_commands/systemd/systemctl_list-unit-files',
                            'sys/fs/cgroup/memory/system.slice'])
    def test_service_factory_no_journal_non_utc_hkt(self):
        # Hong Kong Time (UTC+08)
        # 2022-02-09 22:38:17 HKT is 2022-02-09 14:38:17 UTC
        svc = host_systemd.ServiceFactory().rsyslog
        self.assertEqual(svc.start_time_secs, 1644417497.0)
        self.assertIsNone(host_systemd.ServiceFactory().noexist)

    @utils.create_data_root(
        {'sos_commands/systemd/systemctl_status_--all':
         rsyslog_systemctl_status_template.format("HST")},
        copy_from_original=['sos_commands/systemd/systemctl_list-units',
                            'sos_commands/systemd/systemctl_list-unit-files',
                            'sys/fs/cgroup/memory/system.slice'])
    def test_service_factory_no_journal_non_utc_hst(self):
        # Hawaii-Aleutian Standard Time (UTC-10)
        # 2022-02-09 22:38:17 UTC-10 is 2022-02-10 08:38:17 UTC
        svc = host_systemd.ServiceFactory().rsyslog
        self.assertEqual(svc.start_time_secs, 1644482297.0)
        self.assertIsNone(host_systemd.ServiceFactory().noexist)

    @utils.create_data_root(
        {'sos_commands/systemd/systemctl_status_--all':
         rsyslog_systemctl_status_template.format("ACST")},
        copy_from_original=['sos_commands/systemd/systemctl_list-units',
                            'sos_commands/systemd/systemctl_list-unit-files',
                            'sys/fs/cgroup/memory/system.slice'])
    def test_service_factory_no_journal_non_utc_acst(self):
        # Australian Central Standard Time (UTC+09:30)
        # 2022-02-09 22:38:17 ACST is 2022-02-09 13:08:17 UTC
        svc = host_systemd.ServiceFactory().rsyslog
        self.assertEqual(svc.start_time_secs, 1644412097.0)
        self.assertIsNone(host_systemd.ServiceFactory().noexist)

    def test_systemd_helper(self):
        expected = {'ps': ['nova-api-metadata (5)', 'nova-compute (1)'],
                    'systemd': {'enabled':
                                ['nova-api-metadata', 'nova-compute']}}
        s = host_systemd.SystemdHelper([r'nova\S+'])
        self.assertEqual(s.summary, expected)

    @utils.create_data_root(
        {},
        copy_from_original=['sos_commands/systemd/systemctl_list-units',
                            'sos_commands/systemd/systemctl_list-unit-files',
                            'sys/fs/cgroup/memory/system.slice'])
    def test_systemd_service_focal(self):
        s = host_systemd.SystemdHelper([r'nova\S+'])
        svc = s.services['nova-compute']
        self.assertEqual(svc.memory_current_kb, int(1517744128 / 1024))

    @utils.create_data_root(
        {'sys/fs/cgroup/system.slice/nova-compute.service/memory.current':
         '7168'},
        copy_from_original=['sos_commands/systemd/systemctl_list-units',
                            'sos_commands/systemd/systemctl_list-unit-files'])
    def test_systemd_service_jammy(self):
        s = host_systemd.SystemdHelper([r'nova\S+'])
        svc = s.services['nova-compute']
        self.assertEqual(svc.memory_current_kb, 7)

    @utils.create_data_root(
        {'sos_commands/systemd/systemctl_status_--all':
         """
         ● neutron-ovs-cleanup.service
          Loaded: masked (Reason: Unit neutron-ovs-cleanup.service is masked.)
          Active: inactive (dead)
         """},
        copy_from_original=['sos_commands/systemd/systemctl_list-units',
                            'sos_commands/systemd/systemctl_list-unit-files'])
    def test_start_time_svc_not_active(self):
        with self.assertLogs(logger='hotsos', level='WARNING') as log:
            svc = getattr(host_systemd.ServiceFactory(),
                          'neutron-ovs-cleanup')
            self.assertEqual(svc.start_time_secs, 0)
            # If not active, log.warning() will have been called
            self.assertEqual(len(log.output), 1)
            self.assertIn('no active status found for neutron-ovs-cleanup',
                          log.output[0])
