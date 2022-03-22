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
        return {'version': os.environ['VERSION'],
                'repo-info': os.environ['REPO_INFO']}


class HotSOSClient(object):

    def setup_env(self):
        log.debug("setting up env")
        setup_config(PLUGIN_TMP_DIR=tempfile.mkdtemp())

    def teardown_env(self):
        log.debug("tearing down env")
        if os.path.exists(HotSOSConfig.PLUGIN_TMP_DIR):
            log.debug("deleting plugin tmp dir")
            shutil.rmtree(HotSOSConfig.PLUGIN_TMP_DIR)

    def _run(self):
        log.debug("running plugin %s", HotSOSConfig.PLUGIN_NAME)
        plugin_parts = {}
        if HotSOSConfig.PLUGIN_NAME == 'hotsos':
            plugin_parts['summary'] = {
                'objects': [HotSOSSummary],
                'part_yaml_offset': 0}
        elif HotSOSConfig.PLUGIN_NAME == 'juju':
            plugin_parts['summary'] = {
                'objects': [JujuSummary],
                'part_yaml_offset': 0}
        elif HotSOSConfig.PLUGIN_NAME == 'openstack':
            plugin_parts['summary'] = {
                'objects': [ost_summary.OpenstackSummary],
                'part_yaml_offset': 0}
            plugin_parts['nova_external_events'] = {
                'objects': [nova_external_events.NovaExternalEventChecks],
                'part_yaml_offset': 1}
            plugin_parts['vm_info'] = {
                'objects': [vm_info.OpenstackInstanceChecks,
                            vm_info.NovaServerMigrationAnalysis],
                'part_yaml_offset': 2}
            plugin_parts['service_network_checks'] = {
                'objects': [service_network_checks.OpenstackNetworkChecks],
                'part_yaml_offset': 3}
            plugin_parts['service_features'] = {
                'objects': [service_features.ServiceFeatureChecks],
                'part_yaml_offset': 4}
            plugin_parts['agent_exceptions'] = {
                'objects': [agent_exceptions.AgentExceptionChecks],
                'part_yaml_offset': 5}
            plugin_parts['agent_event_checks'] = {
                'objects': [agent_event_checks.AgentEventChecks],
                'part_yaml_offset': 6}
        elif HotSOSConfig.PLUGIN_NAME == 'openvswitch':
            plugin_parts['summary'] = {
                'objects': [ovs_summary.OpenvSwitchSummary],
                'part_yaml_offset': 0}
            plugin_parts['event_checks'] = {
                'objects': [event_checks.OpenvSwitchDaemonEventChecks,
                            event_checks.OpenvSwitchFlowEventChecks],
                'part_yaml_offset': 1}
        elif HotSOSConfig.PLUGIN_NAME == 'system':
            plugin_parts['summary'] = {
                'objects': [SystemSummary],
                'part_yaml_offset': 0}
            plugin_parts['checks'] = {
                'objects': [SystemChecks],
                'part_yaml_offset': 1}
        elif HotSOSConfig.PLUGIN_NAME == 'maas':
            plugin_parts['summary'] = {
                'objects': [MAASSummary],
                'part_yaml_offset': 0}
        elif HotSOSConfig.PLUGIN_NAME == 'kernel':
            plugin_parts['summary'] = {
                'objects': [kern_summary.KernelSummary],
                'part_yaml_offset': 0}
            plugin_parts['memory'] = {
                'objects': [memory.KernelMemoryChecks],
                'part_yaml_offset': 1}
            plugin_parts['log_event_checks'] = {
                'objects': [log_event_checks.KernelLogEventChecks],
                'part_yaml_offset': 2}
        elif HotSOSConfig.PLUGIN_NAME == 'kubernetes':
            plugin_parts['summary'] = {
                'objects': [KubernetesSummary],
                'part_yaml_offset': 0}
        elif HotSOSConfig.PLUGIN_NAME == 'rabbitmq':
            plugin_parts['summary'] = {
                'objects': [RabbitMQSummary],
                'part_yaml_offset': 0}
        elif HotSOSConfig.PLUGIN_NAME == 'sosreport':
            plugin_parts['summary'] = {
                'objects': [SOSReportSummary],
                'part_yaml_offset': 0}
        elif HotSOSConfig.PLUGIN_NAME == 'storage':
            plugin_parts['ceph_summary'] = {
                'objects': [ceph_summary.CephSummary],
                'part_yaml_offset': 0}
            plugin_parts['ceph_event_checks'] = {
                'objects': [ceph_event_checks.CephDaemonLogChecks],
                'part_yaml_offset': 1}
            plugin_parts['bcache_summary'] = {
                'objects': [bcache_summary.BcacheSummary],
                'part_yaml_offset': 2}
        elif HotSOSConfig.PLUGIN_NAME == 'vault':
            plugin_parts['summary'] = {
                'objects': [VaultSummary],
                'part_yaml_offset': 0}
        else:
            raise Exception("unknown plugin {}".
                            format(HotSOSConfig.PLUGIN_NAME))

        return plugintools.PluginRunner().run_parts(plugin_parts)

    def run(self, plugin):
        """
        Run the selected plugin. This will run the automatic (defs) checks as
        well as any extensions.

        @param plugin: name of plugin to run
        """
        setup_config(PLUGIN_NAME=plugin)
        out = {}
        try:
            self.setup_env()
            out = self._run()
        finally:
            self.teardown_env()

        return out
