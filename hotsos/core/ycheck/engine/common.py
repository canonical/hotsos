import abc
import os

import yaml
from hotsos.core.config import HotSOSConfig
from hotsos.core.log import log


class YDefsLoader():
    """ Load yaml definitions. """

    def __init__(self, ytype, filter_path=None):
        """
        @param ytype: the type of defs we are loading i.e. defs/<ytype>
        """
        self.ytype = ytype
        self._loaded_defs = None
        self.stats_num_files_loaded = 0
        self.filter_path = filter_path

    @staticmethod
    def _is_def(abs_path):
        return abs_path.endswith('.yaml')

    @staticmethod
    def _get_yname(path):
        return os.path.basename(path).partition('.yaml')[0]

    def _get_defs_recursive(self, path):
        """ Recursively find all yaml/files beneath a directory. """
        defs = {}
        for entry in os.listdir(path):
            abs_path = os.path.join(path, entry)
            if os.path.isdir(abs_path):
                subdefs = self._get_defs_recursive(abs_path)
                if subdefs:
                    defs[os.path.basename(abs_path)] = subdefs
            else:
                if not self._is_def(abs_path):
                    continue

                if self._get_yname(abs_path) == os.path.basename(path):
                    with open(abs_path) as fd:
                        log.debug("applying dir globals %s", entry)
                        defs.update(yaml.safe_load(fd.read()) or {})

                    # NOTE: these files do not count towards the total loaded
                    # since they are only supposed to contain directory-level
                    # globals that apply to other definitions in or below this
                    # directory.
                    continue

                with open(abs_path) as fd:
                    self.stats_num_files_loaded += 1
                    _content = yaml.safe_load(fd.read()) or {}
                    defs[self._get_yname(abs_path)] = _content

        return defs

    def _apply_filter(self, loaded):
        """
        If a path filter has been provided, exclude any/all properties that are
        not descendants of that path.
        """
        if not self.filter_path:
            return loaded

        groups = self.filter_path.split('.')
        for i, subgroup in enumerate(groups):
            if i == 0:
                loaded = {subgroup: loaded[subgroup]}
            else:
                prev = groups[i - 1]
                loaded[prev] = {subgroup: loaded[prev][subgroup]}

        return loaded

    @property
    def plugin_defs(self):
        """ Load yaml defs for the current plugin and type. """
        log.debug('loading %s definitions for plugin=%s', self.ytype,
                  HotSOSConfig.plugin_name)

        if self._loaded_defs:
            return self._loaded_defs

        path = os.path.join(HotSOSConfig.plugin_yaml_defs, self.ytype,
                            HotSOSConfig.plugin_name)
        # reset
        self.stats_num_files_loaded = 0
        if os.path.isdir(path):
            loaded = self._get_defs_recursive(path)
            log.debug("YDefsLoader: plugin %s loaded %s file(s)",
                      HotSOSConfig.plugin_name, self.stats_num_files_loaded)
            # only return if we loaded actual definitions (not just globals)
            if self.stats_num_files_loaded:
                loaded = self._apply_filter(loaded)
                self._loaded_defs = loaded
                return loaded


class YHandlerBase():

    def __init__(self, global_searcher, *args, **kwargs):
        self.global_searcher = global_searcher
        super().__init__(*args, **kwargs)

    @abc.abstractmethod
    def run(self):
        """ Process operations. """
