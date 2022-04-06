import os
import tempfile

import mock

from . import utils

from hotsos.core import issues
from hotsos.core.config import setup_config, HotSOSConfig
from hotsos.core.plugins.rabbitmq import RabbitMQReport
from hotsos.core.ycheck.scenarios import YScenarioChecker
from hotsos.plugin_extensions.rabbitmq import summary

RABBITMQ_LOGS = """
Mirrored queue 'rmq-two-queue' in vhost '/': Stopping all nodes on master shutdown since no synchronised slave is available

Discarding message {'$gen_call',{<0.753.0>,#Ref<0.989368845.173015041.56949>},{info,[name,pid,slave_pids,synchronised_slave_pids]}} from <0.753.0> to <0.943.0> in an old incarnation (3) of this node (1)

2020-05-18 06:55:37.324 [error] <0.341.0> Mnesia(rabbit@warp10): ** ERROR ** mnesia_event got {inconsistent_database, running_partitioned_network, rabbit@hostname2}
"""  # noqa


class TestRabbitmqBase(utils.BaseTestCase):

    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)
        setup_config(PLUGIN_NAME='rabbitmq',
                     DATA_ROOT=os.path.join(utils.TESTS_DIR,
                                            'fake_data_root/rabbitmq'))


class TestRabbitMQReport(TestRabbitmqBase):

    def test_property_caching(self):
        report = RabbitMQReport()
        cached_props = ['connections_searchdef',
                        'memory_searchdef',
                        'cluster_partition_handling_searchdef',
                        'queues_searchdef']
        self.assertEqual(sorted(report._property_cache.keys()),
                         sorted(cached_props))

        vhosts = report.vhosts
        self.assertEqual([v.name for v in vhosts], ['/', 'openstack'])
        cached_props.append('vhosts')
        self.assertEqual(sorted(report._property_cache.keys()),
                         sorted(cached_props))

        report.memory_used
        cached_props.append('memory_used')
        self.assertEqual(sorted(report._property_cache.keys()),
                         sorted(cached_props))

        report.connections
        cached_props.append('connections')
        self.assertEqual(sorted(report._property_cache.keys()),
                         sorted(cached_props))

        with mock.patch.object(report.results, 'find_sequence_sections') as \
                mock_results:
            self.assertEqual(report.skewed_nodes,
                             {'rabbit@juju-04f1e3-1-lxd-5': 1})
            cached_props.append('skewed_nodes')
            self.assertEqual(sorted(report._property_cache.keys()),
                             sorted(cached_props))
            # we dont expect this to be called again
            self.assertFalse(mock_results.called)


class TestRabbitmqSummary(TestRabbitmqBase):

    def test_get_summary(self):
        inst = summary.RabbitMQSummary()
        self.assertTrue(inst.plugin_runnable)
        self.assertEqual(list(inst.output.keys()),
                         ['config',
                          'dpkg',
                          'resources',
                          'services'])
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual['dpkg'], ['rabbitmq-server 3.8.2-0ubuntu1.3'])
        self.assertEqual(actual['services'],
                         {'systemd': {
                              'enabled': ['epmd', 'rabbitmq-server']},
                          'ps': ['beam.smp (1)', 'epmd (1)',
                                 'rabbitmq-server (1)']})
        self.assertEqual(actual['config'],
                         {'cluster-partition-handling': 'ignore'})

    @mock.patch('hotsos.core.plugins.rabbitmq.CLIHelper')
    def test_summary_bionic(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()

        def fake_get_rabbitmqctl_report():
            path = os.path.join(HotSOSConfig.DATA_ROOT,
                                "sos_commands/rabbitmq/rabbitmqctl_report."
                                "bionic")
            return open(path, 'r').readlines()

        mock_helper.return_value.rabbitmqctl_report.side_effect = \
            fake_get_rabbitmqctl_report

        expected = {
            'vhosts': [
                "/",
                "openstack",
                "telegraf-telegraf-12",
                "telegraf-telegraf-13",
                "telegraf-telegraf-14",
                ],
            'vhost-queue-distributions': {
                'openstack': {
                    'rabbit@juju-52088b-0-lxd-11': '1137 (86.14%)',
                    'rabbit@juju-52088b-1-lxd-11': '108 (8.18%)',
                    'rabbit@juju-52088b-2-lxd-10': '75 (5.68%)',
                },
            },
            'connections-per-host': {
                'rabbit@juju-52088b-0-lxd-11': 1316,
                'rabbit@juju-52088b-1-lxd-11': 521,
                'rabbit@juju-52088b-2-lxd-10': 454
            },
            'client-connections': {
                'cinder': {'cinder-scheduler': 9,
                           'cinder-volume': 24,
                           'mod_wsgi': 36},
                'neutron': {'neutron-dhcp-agent': 90,
                            'neutron-l3-agent': 21,
                            'neutron-lbaasv2-agent': 12,
                            'neutron-metadata-agent': 424,
                            'neutron-metering-agent': 12,
                            'neutron-openvswitch-agent': 296,
                            'neutron-server': 456},
                'nova': {'mod_wsgi': 34,
                         'nova-api-metadata': 339,
                         'nova-compute': 187,
                         'nova-conductor': 129,
                         'nova-consoleauth': 3,
                         'nova-scheduler': 216},
                'octavia': {'octavia-worker': 3},
            },
            'memory-used-mib': {
                'rabbit@juju-52088b-2-lxd-10': '558.877',
                'rabbit@juju-52088b-1-lxd-11': '605.539',
                'rabbit@juju-52088b-0-lxd-11': '1195.559',
            },
        }

        inst = summary.RabbitMQSummary()
        self.assertEqual(self.part_output_to_actual(inst.output)['resources'],
                         expected)

    def test_summary_focal(self):
        expected = {
            'vhosts': [
                '/',
                'openstack'],
            'vhost-queue-distributions': {
                'openstack': {
                    'rabbit@juju-04f1e3-1-lxd-5': '194 (100.00%)'
                    }},
            'connections-per-host': {
                'rabbit@juju-04f1e3-1-lxd-5': 159},
            'client-connections': {
                'neutron': {
                    'neutron-openvswitch-agent': 39,
                    'neutron-server': 37,
                    'neutron-l3-agent': 15,
                    'neutron-dhcp-agent': 12,
                    'neutron-metadata-agent': 6},
                'nova': {'nova-api-metadata': 24,
                         'nova-compute': 11,
                         'nova-conductor': 11,
                         'nova-scheduler': 4}}}

        inst = summary.RabbitMQSummary()
        self.assertEqual(self.part_output_to_actual(inst.output)['resources'],
                         expected)

    @mock.patch('hotsos.core.plugins.rabbitmq.CLIHelper')
    def test_get_summary_no_report(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.rabbitmqctl_report.return_value = []
        inst = summary.RabbitMQSummary()
        self.assertTrue('resources' not in
                        self.part_output_to_actual(inst.output))


class TestRabbitmqScenarioChecks(TestRabbitmqBase):

    @mock.patch('hotsos.core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter('rabbitmq_bugs.yaml'))
    def test_1943937(self):
        with tempfile.TemporaryDirectory() as dtmp:
            setup_config(DATA_ROOT=dtmp)
            logfile = os.path.join(dtmp, 'var/log/rabbitmq/rabbit@test.log')
            os.makedirs(os.path.dirname(logfile))
            with open(logfile, 'w') as fd:
                fd.write("operation queue.declare caused a channel exception "
                         "not_found: failed to perform operation on queue "
                         "'test_exchange_queue' in vhost "
                         "'nagios-rabbitmq-server-0' due to timeout")

            YScenarioChecker()()
            msg = ('Known RabbitMQ issue where queues get stuck and clients '
                   'trying to use them will just keep timing out. This stops '
                   'many services in the cloud from working correctly. '
                   'Resolution requires you to stop all RabbitMQ servers '
                   'before starting them all again at the same time. A '
                   'rolling restart or restarting them simultaneously will '
                   'not work. See bug for more detail.')

            expected = {'bugs-detected':
                        [{'id': 'https://bugs.launchpad.net/bugs/1943937',
                          'desc': msg,
                          'origin': 'rabbitmq.01part'}]}
            self.assertEqual(issues.IssuesManager().load_bugs(),
                             expected)

    @mock.patch('hotsos.core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter('cluster_config.yaml'))
    @mock.patch('hotsos.core.issues.IssuesManager.add')
    def test_scenarios_cluster_config(self, mock_add_issue):
        raised_issues = {}

        def fake_add_issue(issue, **_kwargs):
            if type(issue) in raised_issues:
                raised_issues[type(issue)].append(issue.msg)
            else:
                raised_issues[type(issue)] = [issue.msg]

        mock_add_issue.side_effect = fake_add_issue
        YScenarioChecker()()
        self.assertEqual(sum([len(msgs) for msgs in raised_issues.values()]),
                         1)
        self.assertTrue(issues.RabbitMQWarning in raised_issues)
        msg = ('Cluster partition handling is currently set to "ignore". This '
               'is potentially dangerous and a setting of '
               '"pause_minority" is recommended.')

        self.assertEqual(msg, raised_issues[issues.RabbitMQWarning][0])

    @mock.patch('hotsos.core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter('cluster_resources.yaml'))
    @mock.patch('hotsos.core.issues.IssuesManager.add')
    def test_scenarios_cluster_resources(self, mock_add_issue):
        raised_issues = {}

        def fake_add_issue(issue, **_kwargs):
            if type(issue) in raised_issues:
                raised_issues[type(issue)].append(issue.msg)
            else:
                raised_issues[type(issue)] = [issue.msg]

        mock_add_issue.side_effect = fake_add_issue
        YScenarioChecker()()
        self.assertEqual(sum([len(msgs) for msgs in raised_issues.values()]),
                         1)
        self.assertTrue(issues.RabbitMQWarning in raised_issues)
        msg = ('RabbitMQ node(s) "rabbit@juju-04f1e3-1-lxd-5" are holding '
               'more than 2/3 of queues for one or more vhosts.')

        self.assertEqual(msg, raised_issues[issues.RabbitMQWarning][0])

    @mock.patch('hotsos.core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter('cluster_logchecks.yaml'))
    @mock.patch('hotsos.core.issues.IssuesManager.add')
    def test_scenarios_cluster_logchecks(self, mock_add_issue):
        raised_issues = {}

        def fake_add_issue(issue, **_kwargs):
            if type(issue) in raised_issues:
                raised_issues[type(issue)].append(issue.msg)
            else:
                raised_issues[type(issue)] = [issue.msg]

        mock_add_issue.side_effect = fake_add_issue
        with tempfile.TemporaryDirectory() as dtmp:
            setup_config(DATA_ROOT=dtmp)
            logfile = os.path.join(dtmp, 'var/log/rabbitmq/rabbit@test.log')
            os.makedirs(os.path.dirname(logfile))
            with open(logfile, 'w') as fd:
                fd.write(RABBITMQ_LOGS)

            YScenarioChecker()()
            self.assertEqual(sum([len(msgs)
                                  for msgs in raised_issues.values()]), 3)
            self.assertTrue(issues.RabbitMQWarning in raised_issues)
            msg1 = ('Messages were discarded because transient mirrored '
                    'classic queues are not syncronized. Please stop all '
                    'rabbitmq-server units and restart the cluster. '
                    'Note that a rolling restart will not work.')
            msg2 = ('This rabbitmq cluster either has or has had partitions - '
                    'please check rabbtimqctl cluster_status.')
            msg3 = ('Transient mirrored classic queues are not deleted when '
                    'there are no replicas available for promotion. Please '
                    'stop all rabbitmq-server units and restart the cluster. '
                    'Note that a rolling restart will not work.')
            expected = sorted([msg1, msg2, msg3])
            actual = sorted(raised_issues[issues.RabbitMQWarning])
            self.assertEqual(actual, expected)
