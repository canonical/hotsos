import datetime
from unittest import mock

import pytz
from hotsos.core.host_helpers import systemd as host_systemd
from hotsos.core.plugins.storage.ceph.common import CEPH_SERVICES_EXPRS

from .. import utils

MICROCEPH_UNITS = """
  run-snapd-ns-microceph.mnt.mount                                                                                loaded active mounted   /run/snapd/ns/microceph.mnt
  snap-microceph-1271.mount                                                                                       loaded active mounted   Mount unit for microceph, revision 1271
  snap-microceph-1293.mount                                                                                       loaded active mounted   Mount unit for microceph, revision 1293
  snap.microceph.daemon.service                                                                                   loaded active running   Service for snap application microceph.daemon
  snap.microceph.mds.service                                                                                      loaded active running   Service for snap application microceph.mds
  snap.microceph.mgr.service                                                                                      loaded active running   Service for snap application microceph.mgr
● snap.microceph.mon.service                                                                                      loaded failed failed    Service for snap application microceph.mon
  snap.microceph.osd.service                                                                                      loaded active running   Service for snap application microceph.osd
"""  # noqa

MICROCEPH_UNIT_FILES = """
snap-microceph-1271.mount                     enabled         enabled
snap-microceph-1293.mount                     enabled         enabled
snap.microceph.daemon.service                 enabled         enabled
snap.microceph.mds.service                    enabled         enabled
snap.microceph.mgr.service                    enabled         enabled
snap.microceph.mon.service                    enabled         enabled
snap.microceph.osd.service                    enabled         enabled
snap.microceph.rbd-mirror.service             disabled        enabled
snap.microceph.rgw.service                    disabled        enabled
"""  # noqa


# Europe/London falls back from BST to GMT at 01:00 UTC on this day so this
# naive time is ambiguous there.
DST_FALL_BACK_NOW = datetime.datetime(2026, 10, 25, 1, 30,
                                      tzinfo=datetime.timezone.utc)


class TestSystemdHelper(utils.BaseTestCase):
    """ Unit tests for systemd helper """
    rsyslog_systemctl_status_template = r"""
* rsyslog.service - System Logging Service
     Loaded: loaded (/lib/systemd/system/rsyslog.service; enabled;)
     Active: active (running) since Wed 2022-02-09 22:38:17 {}; 17h ago

Feb 09 22:38:17 compute4 systemd[1]: Starting System Logging Service...

* secureboot-db.service - Secure Boot updates for DB and DBX"""

    def test_service_factory(self):
        """Test service start time and missing service."""
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
        """Test service start time without journal data."""
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
        """Test start time conversion with UTC+08 timezone."""
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
        """Test start time conversion with UTC+0530 timezone."""
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
        """Test start time conversion with UTC-0730 timezone."""
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
        """Test start time conversion with HKT timezone."""
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
        """Test start time conversion with HST timezone."""
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
        """Test start time conversion with ACST timezone."""
        # Australian Central Standard Time (UTC+09:30)
        # 2022-02-09 22:38:17 ACST is 2022-02-09 13:08:17 UTC
        svc = host_systemd.ServiceFactory().rsyslog
        self.assertEqual(svc.start_time_secs, 1644412097.0)
        self.assertIsNone(host_systemd.ServiceFactory().noexist)

    def test_get_tz_abbreviations_dst_fall_back(self):
        """Test tz abbreviations when now is a fall-back hour in a zone."""
        naive_now = DST_FALL_BACK_NOW.replace(tzinfo=None)
        with self.assertRaises(pytz.AmbiguousTimeError):
            pytz.timezone('Europe/London').localize(naive_now, is_dst=None)

        tzinfos = host_systemd.get_tz_abbreviations(DST_FALL_BACK_NOW)
        for abbrev in ['UTC', 'GMT', 'BST', 'CET', 'CEST']:
            self.assertIn(abbrev, tzinfos)

        summer = datetime.datetime(2026, 7, 1, 12, 0, tzinfo=tzinfos['BST'])
        self.assertEqual(summer.utcoffset(), datetime.timedelta(hours=1))

    def test_get_tz_abbreviations_dst_and_standard(self):
        """Test both standard and DST tz abbreviations are found."""
        cases = {
            # Europe/London springs forward, no other zone uses BST.
            datetime.datetime(2026, 3, 29, 1, 30): ['GMT', 'BST'],
            # New Zealand and Alaska have just changed to DST.
            datetime.datetime(2026, 10, 1, 12, 0): ['NZST', 'NZDT'],
            datetime.datetime(2026, 3, 20, 12, 0): ['AKST', 'AKDT'],
            # New Zealand has just changed back to standard time.
            datetime.datetime(2026, 4, 6, 12, 0): ['NZST', 'NZDT'],
        }
        for now, abbrevs in cases.items():
            now = now.replace(tzinfo=datetime.timezone.utc)
            with self.subTest(now=now):
                tzinfos = host_systemd.get_tz_abbreviations(now)
                for abbrev in abbrevs:
                    self.assertIn(abbrev, tzinfos)

    @utils.create_data_root(
        {'sos_commands/systemd/systemctl_status_--all':
         rsyslog_systemctl_status_template.format("GMT")},
        copy_from_original=['sos_commands/systemd/systemctl_list-units',
                            'sos_commands/systemd/systemctl_list-unit-files',
                            'sys/fs/cgroup/memory/system.slice'])
    @mock.patch.object(host_systemd, 'datetime')
    def test_service_factory_no_journal_dst_fall_back_now(self,
                                                          mock_datetime):
        """Test start time when now is a fall-back hour in a zone."""
        mock_datetime.now.return_value = DST_FALL_BACK_NOW
        svc = host_systemd.ServiceFactory().rsyslog
        # 2022-02-09 22:38:17 GMT is 2022-02-09 22:38:17 UTC
        self.assertEqual(svc.start_time_secs, 1644446297.0)

    @utils.create_data_root(
        {'sos_commands/systemd/systemctl_status_--all':
         rsyslog_systemctl_status_template.format("NZDT")},
        copy_from_original=['sos_commands/systemd/systemctl_list-units',
                            'sos_commands/systemd/systemctl_list-unit-files',
                            'sys/fs/cgroup/memory/system.slice'])
    @mock.patch.object(host_systemd, 'datetime')
    def test_service_factory_no_journal_previous_dst_abbrev(self,
                                                            mock_datetime):
        """Test start time logged with an abbreviation no longer in use."""
        # Started in New Zealand summer, sosreport taken in winter (NZST).
        mock_datetime.now.return_value = datetime.datetime(
            2022, 7, 1, 12, 0, tzinfo=datetime.timezone.utc)
        svc = host_systemd.ServiceFactory().rsyslog
        # 2022-02-09 22:38:17 NZDT (UTC+13) is 2022-02-09 09:38:17 UTC
        self.assertEqual(svc.start_time_secs, 1644399497.0)

    def test_systemd_helper(self):
        """Test systemd helper summary with service exprs."""
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
        """Test memory usage from focal cgroup layout."""
        s = host_systemd.SystemdHelper([r'nova\S+'])
        svc = s.services['nova-compute']
        self.assertEqual(svc.memory_current_kb, int(1517744128 / 1024))

    @utils.create_data_root(
        {'sys/fs/cgroup/system.slice/nova-compute.service/memory.current':
         '7168'},
        copy_from_original=['sos_commands/systemd/systemctl_list-units',
                            'sos_commands/systemd/systemctl_list-unit-files'])
    def test_systemd_service_jammy(self):
        """Test memory usage from jammy cgroup layout."""
        s = host_systemd.SystemdHelper([r'nova\S+'])
        svc = s.services['nova-compute']
        self.assertEqual(svc.memory_current_kb, 7)

    @utils.create_data_root(
        {'sos_commands/systemd/systemctl_list-units':
            MICROCEPH_UNITS,
         'sos_commands/systemd/systemctl_list-unit-files':
            MICROCEPH_UNIT_FILES})
    def test_systemd_service_snap_aliased(self):
        """Test snap-based service detection for microceph."""
        s = host_systemd.SystemdHelper(CEPH_SERVICES_EXPRS)
        self.assertEqual(s.summary, {'systemd': {
                                        'enabled': [
                                            'snap.microceph.mds',
                                            'snap.microceph.mgr',
                                            'snap.microceph.mon',
                                            'snap.microceph.osd'],
                                        'disabled': [
                                            'snap.microceph.rbd-mirror',
                                            'snap.microceph.rgw']},
                                     'ps': []})

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
        """Test inactive service returns zero start time."""
        with self.assertLogs(logger='hotsos', level='WARNING') as log:
            svc = getattr(host_systemd.ServiceFactory(),
                          'neutron-ovs-cleanup')
            self.assertEqual(svc.start_time_secs, 0)
            # If not active, log.warning() will have been called
            self.assertEqual(len(log.output), 1)
            self.assertIn('no active status found for neutron-ovs-cleanup',
                          log.output[0])
