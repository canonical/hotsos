import os
import yaml

from hotsos.core.config import HotSOSConfig
from hotsos.core.log import log


class CallbackHelper(object):

    def __init__(self):
        self.callbacks = {}

    def callback(self, *event_names):
        def callback_inner(f):
            def callback_inner2(*args, **kwargs):
                return f(*args, **kwargs)

            if event_names:
                for name in event_names:
                    # convert event name to valid method name
                    name = name.replace('-', '_')
                    self.callbacks[name] = callback_inner2
            else:
                self.callbacks[f.__name__] = callback_inner2

            return callback_inner2

        # we don't need to return but we leave it so that we can unit test
        # these methods.
        return callback_inner


class YDefsLoader(object):
    def __init__(self, ytype):
        self.ytype = ytype
        self.stats_num_files_loaded = 0

    def _is_def(self, abs_path):
        return abs_path.endswith('.yaml')

    def _get_yname(self, path):
        return os.path.basename(path).partition('.yaml')[0]

    def _get_defs_recursive(self, path):
        """ Recursively find all yaml/files beneath a directory. """
        defs = {}
        for entry in os.listdir(path):
            abs_path = os.path.join(path, entry)
            if os.path.isdir(abs_path):
                subdefs = self._get_defs_recursive(abs_path)
                defs[os.path.basename(abs_path)] = subdefs
            else:
                if not self._is_def(abs_path):
                    continue

                if self._get_yname(abs_path) == os.path.basename(path):
                    with open(abs_path) as fd:
                        log.debug("applying dir globals %s", entry)
                        self.stats_num_files_loaded += 1
                        defs.update(yaml.safe_load(fd.read()) or {})

                    continue

                with open(abs_path) as fd:
                    self.stats_num_files_loaded += 1
                    _content = yaml.safe_load(fd.read()) or {}
                    defs[self._get_yname(abs_path)] = _content

        return defs

    @property
    def plugin_defs(self):
        path = os.path.join(HotSOSConfig.PLUGIN_YAML_DEFS, self.ytype,
                            HotSOSConfig.PLUGIN_NAME)
        # reset
        self.stats_num_files_loaded = 0
        if os.path.isdir(path):
            _defs = self._get_defs_recursive(path)
            log.debug("YDefsLoader: plugin %s loaded %s files",
                      HotSOSConfig.PLUGIN_NAME, self.stats_num_files_loaded)
            return _defs

    @property
    def plugin_defs_legacy(self):
        path = os.path.join(HotSOSConfig.PLUGIN_YAML_DEFS,
                            '{}.yaml'.format(self.ytype))
        if not os.path.exists(path):
            return {}

        log.debug("using legacy defs path %s", path)
        with open(path) as fd:
            defs = yaml.safe_load(fd.read()) or {}

        return defs.get(HotSOSConfig.PLUGIN_NAME, {})

    def load_plugin_defs(self):
        log.debug('loading %s definitions for plugin=%s', self.ytype,
                  HotSOSConfig.PLUGIN_NAME)

        yaml_defs = self.plugin_defs
        if not yaml_defs:
            yaml_defs = self.plugin_defs_legacy

        return yaml_defs


class ChecksBase(object):

    def __init__(self, *args, yaml_defs_group=None, searchobj=None, **kwargs):
        """
        @param _yaml_defs_group: optional key used to identify our yaml
                                 definitions if indeed we have any. This is
                                 given meaning by the implementing class.
        @param searchobj: optional FileSearcher object used for searches. If
                          multiple implementations of this class are used in
                          the same part it is recommended to provide a search
                          object that is shared across them to provide
                          concurrent execution.

        """
        super().__init__(*args, **kwargs)
        self.searchobj = searchobj
        self._yaml_defs_group = yaml_defs_group
        self.__final_checks_results = None

    def load(self):
        raise NotImplementedError

    def run(self, results=None):
        raise NotImplementedError

    def run_checks(self):
        if self.__final_checks_results:
            return self.__final_checks_results

        self.load()
        if self.searchobj:
            ret = self.run(self.searchobj.search())
        else:
            ret = self.run()

        self.__final_checks_results = ret
        return ret

    def __call__(self):
        return self.run_checks()
