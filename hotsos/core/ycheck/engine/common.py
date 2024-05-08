import abc
import os
import re

import yaml
from hotsos.core.config import HotSOSConfig
from hotsos.core.log import log


class YRefKeyNotFoundException(Exception):
    def __init__(self, key):
        message = f"{key} could not be found."
        super().__init__(message)


class YRefReachedMaxAttemptsException(Exception):
    def __init__(self, key):
        message = f"Max search attempts have been reached for {key}"
        super().__init__(message)


class YRefNotAScalarValueException(Exception):
    def __init__(self, key, type_name):
        message = f"{key} has non-scalar value type ({type_name})"
        super().__init__(message)


class YSafeRefLoader(yaml.SafeLoader):
    """This class is just the regular yaml.SafeLoader but also resolves the
    variable names to their values in YAML, e.g.;

        x:
            y: abc
            z: def
        foo : ${x.y} ${x.z}
    # foo's value would be "abc def"

    """

    # The regex pattern for detecting the variable names.
    ref_matcher = None

    def __init__(self, stream):
        super().__init__(stream)
        if not YSafeRefLoader.ref_matcher:
            YSafeRefLoader.ref_matcher = re.compile(r'\$\{([^}^{]+)\}')
            # register a custom tag for which our constructor is called
            YSafeRefLoader.add_constructor("!ref",
                                           YSafeRefLoader.ref_constructor)

            # tell PyYAML that a scalar that looks like `${...}` is to be
            # implicitly tagged with `!ref`, so that our custom constructor
            # is called.
            YSafeRefLoader.add_implicit_resolver("!ref",
                                                 YSafeRefLoader.ref_matcher,
                                                 None)

    # we override this method to remember the root node,
    # so that we can later resolve paths relative to it
    def get_single_node(self):
        self.cur_root = super().get_single_node()
        return self.cur_root

    @staticmethod
    def ref_constructor(loader, node):
        max_resolve_attempts = 1000  # arbitrary choice

        while max_resolve_attempts:
            max_resolve_attempts -= 1
            var = YSafeRefLoader.ref_matcher.search(node.value)
            if not var:
                break
            target_key = var.group(1)
            key_segments = target_key.split(".")
            cur = loader.cur_root
            # Try to resolve the target variable
            while key_segments:
                # Get the segment on the front
                current_segment = key_segments.pop(0)
                found = False
                # Iterate over current node's children
                for (key, value) in cur.value:
                    # Check if node name matches with the current segment
                    if key.value == current_segment:
                        found = True
                        # we're the end of the segments, so we've
                        # reached to the node we want
                        if not key_segments:
                            ref_value = loader.construct_object(value)
                            if isinstance(ref_value, (dict, list)):
                                raise YRefNotAScalarValueException(
                                        target_key,
                                        type(ref_value))
                            node.value = node.value[:var.span()[0]] + \
                                str(ref_value) + node.value[var.span()[1]:]
                            break
                        # Set the current node as root for key search
                        cur = value
                        break

                if not found:
                    raise YRefKeyNotFoundException(target_key)

        if not max_resolve_attempts:
            raise YRefReachedMaxAttemptsException(target_key)

        return node.value


class YDefsLoader(object):
    """ Load yaml definitions. """

    def __init__(self, ytype):
        """
        @param ytype: the type of defs we are loading i.e. defs/<ytype>
        """
        self.ytype = ytype
        self._loaded_defs = None
        self.stats_num_files_loaded = 0

    def load(self, fd):
        return yaml.load(fd.read(), Loader=YSafeRefLoader) or {}

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
                if subdefs:
                    defs[os.path.basename(abs_path)] = subdefs
            else:
                if not self._is_def(abs_path):
                    continue

                if self._get_yname(abs_path) == os.path.basename(path):
                    with open(abs_path) as fd:
                        log.debug("applying dir globals %s", entry)
                        defs.update(self.load(fd))

                    # NOTE: these files do not count towards the total loaded
                    # since they are only supposed to contain directory-level
                    # globals that apply to other definitions in or below this
                    # directory.
                    continue

                with open(abs_path) as fd:
                    self.stats_num_files_loaded += 1
                    _content = self.load(fd)
                    defs[self._get_yname(abs_path)] = _content

        return defs

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
                self._loaded_defs = loaded
                return loaded


class YHandlerBase(object):

    @property
    @abc.abstractmethod
    def searcher(self):
        """
        @return: FileSearcher object to be used by this handler.
        """

    @abc.abstractmethod
    def run(self):
        """ Process operations. """
