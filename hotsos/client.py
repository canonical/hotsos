#!/usr/bin/python3
import gzip
import html
import json
import logging
import os
import shutil
import tempfile
from typing import Literal

# load all plugins
import hotsos.plugin_extensions  # noqa: F401, pylint: disable=W0611
from hotsos.core.config import HotSOSConfig
from hotsos.core.host_helpers.cli import CLIHelper
from hotsos.core.issues import IssuesManager
from hotsos.core.log import log
from hotsos.core import plugintools
from hotsos.core.exceptions import UnsupportedFormatError


class HotSOSSummary(plugintools.PluginPartBase):
    """
    This plugin will always be run and provides information specific to hotsos
    itself.
    """
    plugin_name = 'hotsos'
    plugin_root_index = 0
    summary_part_index = 0

    @classmethod
    def is_runnable(cls):
        return True

    @property
    def summary(self):
        out = {'version': HotSOSConfig.hotsos_version,
               'repo-info': HotSOSConfig.repo_info}
        if HotSOSConfig.force_mode:
            out['force'] = True

        return out


FILTER_SCHEMA = [IssuesManager.SUMMARY_OUT_ISSUES_ROOT,
                 IssuesManager.SUMMARY_OUT_BUGS_ROOT]


SUPPORTED_SUMMARY_FORMATS = ['yaml', 'json', 'markdown', 'html']
SUPPORTED_MINIMAL_MODES = ['full', 'short', 'very-short']


class OutputBuilder:
    """Builder class for generating desired output format from
    raw dictionary."""

    def __init__(self, content):
        self.content = content

    @staticmethod
    def _minimise(summary, mode):
        """ Converts the master output to include only issues and bugs. """

        log.debug("Minimising output (mode=%s).", mode)

        if not summary:
            return summary

        if mode == 'short':
            return OutputBuilder._get_short_format(summary)
        if mode == 'very-short':
            return OutputBuilder._get_very_short_format(summary)

        log.warning("Unknown minimalmode '%s'", mode)
        return summary

    @staticmethod
    def _get_short_format(summary):
        filtered = {}
        for plugin in summary:
            for key in FILTER_SCHEMA:
                if key not in summary[plugin]:
                    continue

                if key not in filtered:
                    filtered[key] = {}

                items = summary[plugin][key]
                filtered[key][plugin] = items

        return filtered

    @staticmethod
    def _get_very_short_format(summary):
        filtered = {}
        for plugin in summary:
            for key in FILTER_SCHEMA:
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

    def filter(self, plugin_name=None):
        if plugin_name:
            self.content = {plugin_name: self.content[plugin_name]}
        return self

    def minimal(self, mode=None):
        if mode:
            self.content = self._minimise(self.content, mode)
        return self

    def to(self, fmt: Literal[SUPPORTED_SUMMARY_FORMATS],
           **kwargs):
        if fmt == "html":
            return self.to_html(**kwargs)
        if fmt == "json":
            return self.to_json()
        if fmt == "yaml":
            return self.to_yaml()
        if fmt == "markdown":
            return self.to_markdown()

        raise UnsupportedFormatError(fmt)

    def to_html(self, *, max_level=2, html_escape=False):
        hostname = CLIHelper().hostname() or ""
        result = plugintools.HTMLFormatter(
            hostname=hostname,
            max_level=max_level
        ).dump(self.content)

        return result if not html_escape else html.escape(result)

    def to_json(self):
        return json.dumps(self.content, indent=2, sort_keys=True)

    def to_yaml(self):
        return plugintools.yaml_dump(self.content)

    def to_markdown(self):
        return plugintools.MarkdownFormatter().dump(self.content)


class OutputManager():
    """ Handle conversion of plugin output into summary format. """

    def __init__(self, initial=None):
        self._summary = initial or {}

    def get_builder(self):
        return OutputBuilder(self._summary)

    @staticmethod
    def _save_to_file(path, content):
        with open(path, "w", encoding="utf-8") as fd:
            fd.write(content)
            fd.write("\n")

    @staticmethod
    def compress(path):
        """
        Compress path to path.gz and delete path.
        """
        cpath = path + '.gz'
        with open(path, 'rb') as fd_in:
            with gzip.open(cpath, 'wb') as fd_out:
                shutil.copyfileobj(fd_in, fd_out)

        os.remove(path)

    def save(self, name, html_escape=False, output_path=None):
        """
        Save all formats and styles to disk using either the provided path or
        an autogenerated one.

        Returns path of saved data.

        @param name: name used to identify the data_root. This is typically
                     the basename of the path or local hostname.
        """
        if output_path:
            output_root = output_path
        else:
            output_root = f"hotsos-output-{CLIHelper().date(format='+%s')}"

        for minimal_mode in SUPPORTED_MINIMAL_MODES:
            _minimal_mode = minimal_mode.replace('-', '_')
            for fmt in SUPPORTED_SUMMARY_FORMATS:
                output_path = os.path.join(output_root, name, 'summary',
                                           _minimal_mode, fmt)
                if minimal_mode == 'full':
                    minimal_mode = None

                if not os.path.exists(output_path):
                    os.makedirs(output_path)

                # Save per-plugin summary
                for plugin in self._summary:
                    path = os.path.join(output_path,
                                        f"hotsos-summary.{plugin}.{fmt}")
                    output = self.get_builder()
                    output.filter(plugin).minimal(minimal_mode)
                    formatted_output = output.to(
                        fmt=fmt,
                        html_escape=html_escape)
                    log.debug('Saving plugin %s summary as %s',
                              plugin,
                              fmt)
                    self._save_to_file(path, formatted_output)

                # Save all summary
                path = os.path.join(output_path, f"hotsos-summary.all.{fmt}")
                output = self.get_builder()
                output.minimal(minimal_mode)
                formatted_output = output.to(fmt=fmt, html_escape=html_escape)
                log.debug('Saving all summary as %s', fmt)
                self._save_to_file(path, formatted_output)

                if not minimal_mode:
                    dst = os.path.join(output_root, f'{name}.summary.{fmt}')
                    if os.path.exists(dst):
                        os.remove(dst)

                    os.symlink(path.partition(output_root)[2].lstrip('/'), dst)

        if log.handlers and isinstance(log.handlers[0], logging.FileHandler):
            log.handlers[0].close()
            # no logging after this point
            logfile_dst = os.path.join(output_root, name, 'hotsos.log')
            shutil.move(log.handlers[0].baseFilename, logfile_dst)
            self.compress(logfile_dst)

        return output_root

    def update(self, plugin, content):
        self._summary[plugin] = content


class HotSOSClient():
    """
    Main HotSOS client from which all plugins are run.
    """
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
