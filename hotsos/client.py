#!/usr/bin/python3
import html
import json
import logging
import os
import shutil
import tempfile

from hotsos.core.log import log
from hotsos.core.issues import IssuesManager
from hotsos.core.host_helpers.cli import CLIHelper
from hotsos.core.config import HotSOSConfig
from hotsos.core import plugintools

from hotsos.plugin_extensions.lxd.summary import LXDSummary
from hotsos.plugin_extensions.mysql.summary import MySQLSummary
from hotsos.plugin_extensions.juju.summary import JujuSummary
from hotsos.plugin_extensions.openstack import (
    summary as ost_summary,
    service_features,
    service_network_checks,
    vm_info,
    nova_external_events,
)
from hotsos.plugin_extensions.openstack.agent import (
    events as agent_events,
    exceptions as agent_exceptions,
)

from hotsos.plugin_extensions.openvswitch import (
    summary as ovs_summary,
    event_checks,
)
from hotsos.plugin_extensions.system.summary import SystemSummary
from hotsos.plugin_extensions.system.checks import SYSCtlChecks
from hotsos.plugin_extensions.maas.summary import MAASSummary
from hotsos.plugin_extensions.kernel import summary as kern_summary
from hotsos.plugin_extensions.kubernetes.summary import KubernetesSummary
from hotsos.plugin_extensions.rabbitmq.summary import RabbitMQSummary
from hotsos.plugin_extensions.sosreport.summary import SOSReportSummary
from hotsos.plugin_extensions.storage import (
    ceph_summary,
    ceph_event_checks,
    bcache_summary,
)
from hotsos.plugin_extensions.vault.summary import VaultSummary
from hotsos.plugin_extensions.pacemaker.summary import PacemakerSummary


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
        out = {'version': HotSOSConfig.hotsos_version,
               'repo-info': HotSOSConfig.repo_info}
        if HotSOSConfig.force_mode:
            out['force'] = True

        return out


# Ensure that plugins are always run in this order so as to get consistent
# output.
PLUGIN_RUN_ORDER = [
    'hotsos',
    'system',
    'sosreport',
    'mysql',
    'openstack',
    'pacemaker',
    'openvswitch',
    'rabbitmq',
    'kubernetes',
    'storage',
    'vault',
    'lxd',
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
                  'lxd': {
                     'summary': {
                         'objects': [LXDSummary],
                         'part_yaml_offset': 0}},
                  'mysql': {
                     'summary': {
                         'objects': [MySQLSummary],
                         'part_yaml_offset': 0},
                      },
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
                        'objects': [agent_events.AgentEventChecks],
                        'part_yaml_offset': 6}},
                  'openvswitch': {
                     'summary': {
                         'objects': [ovs_summary.OpenvSwitchSummary],
                         'part_yaml_offset': 0},
                     'event_checks': {
                         'objects': [event_checks.OVSEventChecks,
                                     event_checks.OVNEventChecks],
                         'part_yaml_offset': 1}},
                  'system': {
                     'summary': {
                         'objects': [SystemSummary],
                         'part_yaml_offset': 0},
                     'checks': {
                         'objects': [SYSCtlChecks],
                         'part_yaml_offset': 1}},
                  'maas': {
                     'summary': {
                         'objects': [MAASSummary],
                         'part_yaml_offset': 0}},
                  'kernel': {
                     'summary': {
                         'objects': [kern_summary.KernelSummary],
                         'part_yaml_offset': 0}},
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
                         'part_yaml_offset': 0}},
                  'pacemaker': {
                     'summary': {
                         'objects': [PacemakerSummary],
                         'part_yaml_offset': 0}}}


class OutputManager(object):
    FILTER_SCHEMA = [IssuesManager.SUMMARY_OUT_ISSUES_ROOT,
                     IssuesManager.SUMMARY_OUT_BUGS_ROOT]
    SUMMARY_FORMATS = ['yaml', 'json', 'markdown', 'html']

    def __init__(self, initial=None):
        self._summary = initial or {}

    def _get_short_format(self, summary):
        filtered = {}
        for plugin in summary:
            for key in self.FILTER_SCHEMA:
                if key in summary[plugin]:
                    if key not in filtered:
                        filtered[key] = {}

                    items = summary[plugin][key]
                    filtered[key][plugin] = items

        return filtered

    def _get_very_short_format(self, summary):
        filtered = {}
        for plugin in summary:
            for key in self.FILTER_SCHEMA:
                if key in summary[plugin]:
                    if key not in filtered:
                        filtered[key] = {}

                    items = summary[plugin][key]
                    if type(items) == dict:
                        filtered[key][plugin] = {key: len(val)
                                                 for key, val in items.items()}
                    else:
                        # support old format summaries
                        if key == IssuesManager.SUMMARY_OUT_ISSUES_ROOT:
                            aggr_info = {}
                        else:
                            aggr_info = []

                        for item in items:
                            if key == IssuesManager.SUMMARY_OUT_ISSUES_ROOT:
                                item_key = item['type']
                                if item_key not in aggr_info:
                                    aggr_info[item_key] = 1
                                else:
                                    aggr_info[item_key] += 1

                            else:
                                item_key = item['id']
                                aggr_info.append(item_key)

                        filtered[key][plugin] = aggr_info

        return filtered

    def minimise(self, summary, mode):
        """ Converts the master output to include only issues and bugs. """

        log.debug("Minimising output (mode=%s).", mode)
        if not summary:
            return summary

        if mode == 'short':
            return self._get_short_format(summary)
        elif mode == 'very-short':
            return self._get_very_short_format(summary)

        log.warning("Unknown minimalmode '%s'", mode)
        return summary

    def get(self, format='yaml', html_escape=False, minimal_mode=None,
            plugin=None, max_level=2):
        if plugin:
            filtered = {plugin: self._summary[plugin]}
        else:
            filtered = self._summary

        if minimal_mode:
            filtered = self.minimise(filtered, minimal_mode)

        if format not in self.SUMMARY_FORMATS:
            raise Exception("unsupported summary format '{}'".format(format))

        hostname = CLIHelper().hostname() or ""
        log.debug('Saving summary as %s', format)
        if format == 'yaml':
            filtered = plugintools.yaml_dump(filtered)
        elif format == 'json':
            filtered = json.dumps(filtered, indent=2, sort_keys=True)
        elif format == 'markdown':
            filtered = plugintools.MarkdownFormatter().dump(filtered)
        elif format == 'html':
            filtered = plugintools.HTMLFormatter(
                                            hostname=hostname,
                                            max_level=max_level).dump(filtered)

        if html_escape:
            log.debug('Applying html escaping to summary')
            filtered = html.escape(filtered)

        return filtered

    def _save(self, path, format, html_escape=None, minimal_mode=None,
              plugin=None):
        content = self.get(format=format, html_escape=html_escape,
                           minimal_mode=minimal_mode, plugin=plugin)
        with open(path, 'w', encoding='utf-8') as fd:
            fd.write(content)
            fd.write('\n')

    def save(self, name, html_escape=False, output_path=None):
        """
        Save all formats and styles to disk using either the provided path or
        an autogenerated one.

        Returns path of saved data.
        """
        if output_path:
            output_root = output_path
        else:
            output_root = ('hotsos-output-{}'.
                           format(CLIHelper().date(format='+%s')))

        for minimal_mode in ['full', 'short', 'very-short']:
            _minimal_mode = minimal_mode.replace('-', '_')
            for format in self.SUMMARY_FORMATS:
                output_path = os.path.join(output_root, name, 'summary',
                                           _minimal_mode, format)
                if minimal_mode == 'full':
                    minimal_mode = None

                if not os.path.exists(output_path):
                    os.makedirs(output_path)

                for plugin in self._summary:
                    path = os.path.join(output_path,
                                        "hotsos-summary.{}.{}".format(plugin,
                                                                      format))
                    self._save(path, format, html_escape=html_escape,
                               minimal_mode=minimal_mode, plugin=plugin)

                path = os.path.join(output_path,
                                    "hotsos-summary.all.{}".format(format))
                self._save(path, format, html_escape=html_escape,
                           minimal_mode=minimal_mode)

                if not minimal_mode:
                    dst = os.path.join(output_root, '{}.summary.{}'.
                                       format(name, format))
                    if os.path.exists(dst):
                        os.remove(dst)

                    os.symlink(path.partition(output_root)[2].lstrip('/'), dst)

        if log.handlers and isinstance(log.handlers[0], logging.FileHandler):
            log.handlers[0].close()
            # no logging after this point
            shutil.move(log.handlers[0].baseFilename,
                        os.path.join(output_root, name, 'hotsos.log'))

        return output_root

    def update(self, plugin, content):
        self._summary[plugin] = content


class HotSOSClient(object):

    def __init__(self, plugins=None):
        """
        @param plugins: list of plugin names to run. If no plugins are provided
        all will be run.
        """
        self._summary = OutputManager()
        if plugins:
            self.plugins = plugins
        else:
            self.plugins = list(PLUGIN_CATALOG.keys())

    def setup_global_env(self):
        """ State saved here persists across all plugin runs. """
        log.debug("setting up global env")
        global_tmp_dir = tempfile.mkdtemp()
        HotSOSConfig.global_tmp_dir = global_tmp_dir
        os.makedirs(os.path.join(global_tmp_dir, 'locks'))

    def teardown_global_env(self):
        log.debug("tearing down global env")
        if os.path.exists(HotSOSConfig.global_tmp_dir):
            shutil.rmtree(HotSOSConfig.global_tmp_dir)

    def setup_plugin_env(self, plugin):
        """ State saved here is specific to a plugin. """
        log.debug("setting up plugin env")
        global_tmp = HotSOSConfig.global_tmp_dir
        HotSOSConfig.plugin_tmp_dir = tempfile.mkdtemp(prefix=plugin,
                                                       dir=global_tmp)

    def _run(self, plugin):
        if plugin not in PLUGIN_CATALOG:
            raise Exception("unknown plugin {}".format(plugin))

        log.name = 'plugin.{}'.format(plugin)
        log.debug("running plugin %s", plugin)
        HotSOSConfig.plugin_name = plugin
        parts = PLUGIN_CATALOG[plugin]
        return plugintools.PluginRunner(parts).run()

    @property
    def summary(self):
        return self._summary

    def run(self):
        """
        Run the selected plugins. This will run the automatic (defs) checks as
        well as any extensions.
        """
        log.name = 'hotsos.client'
        try:
            self.setup_global_env()
            for plugin in PLUGIN_RUN_ORDER:
                if plugin in self.plugins:
                    self.setup_plugin_env(plugin)
                    content = self._run(plugin)
                    if content:
                        self.summary.update(plugin, content.get(plugin))
        finally:
            log.name = 'hotsos.client'
            self.teardown_global_env()
