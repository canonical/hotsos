#!/usr/bin/python3
import os
import shutil
import tempfile

from core.log import log
from core.config import setup_config, HotSOSConfig
from core import plugintools

from plugin_extensions.juju.summary import JujuSummary
from plugin_extensions.openstack import (
    summary as ost_summary,
    service_features,
    service_network_checks,
    agent_event_checks,
    vm_info,
    agent_exceptions,
    nova_external_events,
)
from plugin_extensions.openvswitch import (
    summary as ovs_summary,
    event_checks,
)
from plugin_extensions.system.summary import SystemSummary
from plugin_extensions.system.checks import SystemChecks
from plugin_extensions.maas.summary import MAASSummary
from plugin_extensions.kernel import (
     summary as kern_summary,
     memory,
     log_event_checks,
)
from plugin_extensions.kubernetes.summary import KubernetesSummary
from plugin_extensions.rabbitmq.summary import RabbitMQSummary
from plugin_extensions.sosreport.summary import SOSReportSummary
from plugin_extensions.storage import (
    ceph_summary,
    ceph_event_checks,
    bcache_summary,
)
from plugin_extensions.vault.summary import VaultSummary


class HotSOSSummary(plugintools.PluginPartBase):
    """
    This plugin will always be run and provides information specific to hotsos
    itself.
    """
    @property
    def plugin_runnable(self):
        return True

    @property
    def summary(self):
        return {'version': os.environ.get('HOTSOS_VERSION', 'unknown'),
                'repo-info': os.environ.get('REPO_INFO', 'unknown')}


# Ensure that plugins are always run in this order so as to get consistent
# output.
PLUGIN_RUN_ORDER = [
    'hotsos',
    'system',
    'sosreport',
    'openstack',
    'openvswitch',
    'rabbitmq',
    'kubernetes',
    'storage',
    'vault',
    'juju',
    'maas',
    'kernel',
]


PLUGIN_CATALOG = {'hotsos': {
                    'summary': {
                        'objects': [HotSOSSummary],
                        'part_yaml_offset': 0}},
                  'juju': {
                     'summary': {
                         'objects': [JujuSummary],
                         'part_yaml_offset': 0}},
                  'openstack': {
                     'summary': {
                         'objects': [ost_summary.OpenstackSummary],
                         'part_yaml_offset': 0},
                    'nova_external_events': {
                        'objects': [
                            nova_external_events.NovaExternalEventChecks],
                        'part_yaml_offset': 1},
                    'vm_info': {
                        'objects': [vm_info.OpenstackInstanceChecks,
                                    vm_info.NovaServerMigrationAnalysis],
                        'part_yaml_offset': 2},
                    'service_network_checks': {
                        'objects': [
                            service_network_checks.OpenstackNetworkChecks],
                        'part_yaml_offset': 3},
                    'service_features': {
                        'objects': [service_features.ServiceFeatureChecks],
                        'part_yaml_offset': 4},
                    'agent_exceptions': {
                        'objects': [agent_exceptions.AgentExceptionChecks],
                        'part_yaml_offset': 5},
                    'agent_event_checks': {
                        'objects': [agent_event_checks.AgentEventChecks],
                        'part_yaml_offset': 6}},
                  'openvswitch': {
                     'summary': {
                         'objects': [ovs_summary.OpenvSwitchSummary],
                         'part_yaml_offset': 0},
                     'event_checks': {
                         'objects': [event_checks.OpenvSwitchDaemonEventChecks,
                                     event_checks.OpenvSwitchFlowEventChecks],
                         'part_yaml_offset': 1}},
                  'system': {
                     'summary': {
                         'objects': [SystemSummary],
                         'part_yaml_offset': 0},
                     'checks': {
                         'objects': [SystemChecks],
                         'part_yaml_offset': 1}},
                  'maas': {
                     'summary': {
                         'objects': [MAASSummary],
                         'part_yaml_offset': 0}},
                  'kernel': {
                     'summary': {
                         'objects': [kern_summary.KernelSummary],
                         'part_yaml_offset': 0},
                     'memory': {
                         'objects': [memory.KernelMemoryChecks],
                         'part_yaml_offset': 1},
                     'log_event_checks': {
                         'objects': [log_event_checks.KernelLogEventChecks],
                         'part_yaml_offset': 2}},
                  'kubernetes': {
                     'summary': {
                         'objects': [KubernetesSummary],
                         'part_yaml_offset': 0}},
                  'rabbitmq': {
                     'summary': {
                         'objects': [RabbitMQSummary],
                         'part_yaml_offset': 0}},
                  'sosreport': {
                     'summary': {
                         'objects': [SOSReportSummary],
                         'part_yaml_offset': 0}},
                  'storage': {
                     'ceph_summary': {
                         'objects': [ceph_summary.CephSummary],
                         'part_yaml_offset': 0},
                     'ceph_event_checks': {
                         'objects': [ceph_event_checks.CephDaemonLogChecks],
                         'part_yaml_offset': 1},
                     'bcache_summary': {
                         'objects': [bcache_summary.BcacheSummary],
                         'part_yaml_offset': 2}},
                  'vault': {
                     'summary': {
                         'objects': [VaultSummary],
                         'part_yaml_offset': 0}}}


class HotSOSClient(object):

    def setup_env(self):
        log.debug("setting up env")
        setup_config(PLUGIN_TMP_DIR=tempfile.mkdtemp())

    def teardown_env(self):
        log.debug("tearing down env")
        if os.path.exists(HotSOSConfig.PLUGIN_TMP_DIR):
            log.debug("deleting plugin tmp dir")
            shutil.rmtree(HotSOSConfig.PLUGIN_TMP_DIR)

    def _run(self, plugin):
        log.debug("running plugin %s", plugin)
        if plugin not in PLUGIN_CATALOG:
            raise Exception("unknown plugin {}".format(plugin))

        setup_config(PLUGIN_NAME=plugin)
        parts = PLUGIN_CATALOG[plugin]
        return plugintools.PluginRunner().run_parts(parts)

    def run(self, plugins=None):
        """
        Run the selected plugins. This will run the automatic (defs) checks as
        well as any extensions.

        @param plugins: list of plugin names to run. If no plugins are provided
        all will be run.
        """
        out = {}
        if not plugins:
            plugins = list(PLUGIN_CATALOG.keys())

        for plugin in PLUGIN_RUN_ORDER:
            if plugin in plugins:
                try:
                    self.setup_env()
                    out.update(self._run(plugin) or {})
                finally:
                    self.teardown_env()

        return out
