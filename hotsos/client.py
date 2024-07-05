#!/usr/bin/python3
import html
import json
import logging
import os
import shutil
import tempfile

# load all plugins
import hotsos.plugin_extensions  # noqa: F401, pylint: disable=W0611
from hotsos.core.config import HotSOSConfig
from hotsos.core.host_helpers.cli import CLIHelper
from hotsos.core.issues import IssuesManager
from hotsos.core.log import log
from hotsos.core import plugintools


class HotSOSSummary(plugintools.PluginPartBase):
    """
    This plugin will always be run and provides information specific to hotsos
    itself.
    """
    plugin_name = 'hotsos'
    plugin_root_index = 0
    summary_part_index = 0

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


class OutputManager():
    FILTER_SCHEMA = [IssuesManager.SUMMARY_OUT_ISSUES_ROOT,
                     IssuesManager.SUMMARY_OUT_BUGS_ROOT]
    SUMMARY_FORMATS = ['yaml', 'json', 'markdown', 'html']

    def __init__(self, initial=None):
        self._summary = initial or {}

    def _get_short_format(self, summary):
        filtered = {}
        for plugin in summary:
            for key in self.FILTER_SCHEMA:
                if key not in summary[plugin]:
                    continue

                if key not in filtered:
                    filtered[key] = {}

                items = summary[plugin][key]
                filtered[key][plugin] = items

        return filtered

    def _get_very_short_format(self, summary):
        filtered = {}
        for plugin in summary:
            for key in self.FILTER_SCHEMA:
                if key not in summary[plugin]:
                    continue

                if key not in filtered:
                    filtered[key] = {}

                items = summary[plugin][key]
                if isinstance(items, dict):
                    filtered[key][plugin] = {key: len(val)
                                             for key, val in items.items()}
                    continue

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
        if mode == 'very-short':
            return self._get_very_short_format(summary)

        log.warning("Unknown minimalmode '%s'", mode)
        return summary

    def get(self, fmt='yaml', html_escape=False, minimal_mode=None,
            plugin=None, max_level=2):
        if plugin:
            filtered = {plugin: self._summary[plugin]}
        else:
            filtered = self._summary

        if minimal_mode:
            filtered = self.minimise(filtered, minimal_mode)

        if fmt not in self.SUMMARY_FORMATS:
            raise Exception(f"unsupported summary format '{fmt}'")

        hostname = CLIHelper().hostname() or ""
        log.debug('Saving summary as %s', fmt)
        if fmt == 'yaml':
            filtered = plugintools.yaml_dump(filtered)
        elif fmt == 'json':
            filtered = json.dumps(filtered, indent=2, sort_keys=True)
        elif fmt == 'markdown':
            filtered = plugintools.MarkdownFormatter().dump(filtered)
        elif fmt == 'html':
            filtered = plugintools.HTMLFormatter(
                                            hostname=hostname,
                                            max_level=max_level).dump(filtered)

        if html_escape:
            log.debug('Applying html escaping to summary')
            filtered = html.escape(filtered)

        return filtered

    def _save(self, path, fmt, html_escape=None, minimal_mode=None,
              plugin=None):
        content = self.get(fmt=fmt, html_escape=html_escape,
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
            output_root = f"hotsos-output-{CLIHelper().date(format='+%s')}"

        for minimal_mode in ['full', 'short', 'very-short']:
            _minimal_mode = minimal_mode.replace('-', '_')
            for fmt in self.SUMMARY_FORMATS:
                output_path = os.path.join(output_root, name, 'summary',
                                           _minimal_mode, fmt)
                if minimal_mode == 'full':
                    minimal_mode = None

                if not os.path.exists(output_path):
                    os.makedirs(output_path)

                for plugin in self._summary:
                    path = os.path.join(output_path,
                                        f"hotsos-summary.{plugin}.{fmt}")
                    self._save(path, fmt, html_escape=html_escape,
                               minimal_mode=minimal_mode, plugin=plugin)

                path = os.path.join(output_path, f"hotsos-summary.all.{fmt}")
                self._save(path, fmt, html_escape=html_escape,
                           minimal_mode=minimal_mode)

                if not minimal_mode:
                    dst = os.path.join(output_root, f'{name}.summary.{fmt}')
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


class HotSOSClient():

    def __init__(self, plugins=None):
        """
        @param plugins: list of plugin names to run. If no plugins are provided
        all will be run.
        """
        self._summary = OutputManager()
        self.plugins = plugins or plugintools.PLUGINS.keys()

    @staticmethod
    def setup_global_env():
        """ State saved here persists across all plugin runs. """
        log.debug("setting up global env")
        global_tmp_dir = tempfile.mkdtemp()
        HotSOSConfig.global_tmp_dir = global_tmp_dir
        os.makedirs(os.path.join(global_tmp_dir, 'locks'))

    @staticmethod
    def teardown_global_env():
        log.debug("tearing down global env")
        if os.path.exists(HotSOSConfig.global_tmp_dir):
            shutil.rmtree(HotSOSConfig.global_tmp_dir)
        # Ensure tmp dir doesn't get accidentally recreated
        HotSOSConfig.plugin_tmp_dir = None

    @staticmethod
    def setup_plugin_env(plugin):
        """ State saved here is specific to a plugin. """
        log.debug("setting up plugin env")
        global_tmp = HotSOSConfig.global_tmp_dir
        HotSOSConfig.plugin_tmp_dir = tempfile.mkdtemp(prefix=plugin,
                                                       dir=global_tmp)

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
            for plugin in plugintools.get_plugins_sorted():
                if plugin not in self.plugins:
                    continue

                self.setup_plugin_env(plugin)
                log.name = f'hotsos.plugin.{plugin}'
                log.debug("running plugin %s", plugin)
                HotSOSConfig.plugin_name = plugin
                content = plugintools.PluginRunner(plugin).run()
                if content:
                    self.summary.update(plugin, content.get(plugin))
        finally:
            log.name = 'hotsos.client'
            self.teardown_global_env()
