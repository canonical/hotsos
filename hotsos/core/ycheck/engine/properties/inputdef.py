import os
from functools import cached_property

from hotsos.core.config import HotSOSConfig
from hotsos.core.host_helpers import CLIHelperFile
from hotsos.core.log import log
from hotsos.core.ycheck.engine.properties.common import (
    YPropertyOverrideBase,
)


class YPropertyInputBase(object):

    @property
    def options(self):
        defaults = {'disable-all-logs': False,
                    'args': [],
                    'kwargs': {},
                    'args-callback': None}

        if isinstance(self.content, dict):
            _options = self.content.get('options', defaults)
            defaults.update(_options)

        return defaults

    @property
    def command(self):
        if not isinstance(self.content, dict):
            return

        return self.content.get('command')

    def expand_paths(self, paths):
        _paths = []
        for path in paths:
            path = os.path.join(HotSOSConfig.data_root, path)
            if (HotSOSConfig.use_all_logs and not
                    self.options['disable-all-logs']):
                path = "{}*".format(path)

            _paths.append(path)

        return _paths

    @property
    def path(self):
        raise Exception("do not call this directly")

    @cached_property
    def paths(self):
        _paths = []
        fs_path = None
        if isinstance(self.content, (str, list)):
            fs_path = self.content
        else:
            fs_path = self.content.get('path')

        if fs_path:
            if isinstance(fs_path, list):
                for path in fs_path:
                    _paths.append(path)
            else:
                _paths.append(fs_path)

            return self.expand_paths(_paths)

        if self.command:
            cmd_tmp_path = self.cache.cmd_tmp_path
            if cmd_tmp_path:
                return [cmd_tmp_path]

            args_callback = self.options['args-callback']
            if args_callback:
                args, kwargs = self.get_method(args_callback)
            else:
                args = self.options['args']
                kwargs = self.options['kwargs']

            with CLIHelperFile(delete_temp=False) as cli:
                outfile = getattr(cli, self.command)(*args, **kwargs)
                self.cache.set('cmd_tmp_path', outfile)
                return [outfile]

        log.debug("no input provided")


class YPropertyInput(YPropertyOverrideBase, YPropertyInputBase):
    _override_keys = ['input']
    # We want to be able to use this property both on its own and as a member
    # of other mapping properties e.g. Checks. The following setting enables
    # this.
    _override_auto_implicit_member = False
