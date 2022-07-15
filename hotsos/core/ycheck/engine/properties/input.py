import os

from hotsos.core.config import HotSOSConfig
from hotsos.core.host_helpers import CLIHelper
from hotsos.core.log import log
from hotsos.core.utils import mktemp_dump
from hotsos.core.ycheck.engine.properties.common import (
    cached_yproperty_attr,
    YPropertyOverrideBase,
    add_to_property_catalog,
)


class YPropertyInputBase(object):

    @property
    def options(self):
        defaults = {'disable-all-logs': False,
                    'args': [],
                    'kwargs': {},
                    'args-callback': None}

        if type(self.content) == dict:
            _options = self.content.get('options', defaults)
            defaults.update(_options)

        return defaults

    @cached_yproperty_attr
    def command(self):
        return self.content.get('command')

    @cached_yproperty_attr
    def fs_path(self):
        if type(self.content) == str:
            return self.content

        return self.content.get('path')

    @cached_yproperty_attr
    def path(self):
        if self.fs_path:  # pylint: disable=W0125
            path = os.path.join(HotSOSConfig.DATA_ROOT, self.fs_path)
            if (HotSOSConfig.USE_ALL_LOGS and not
                    self.options['disable-all-logs']):
                path = "{}*".format(path)

            return path

        if self.command:  # pylint: disable=W0125
            cmd_tmp_path = self.cache.cmd_tmp_path
            if cmd_tmp_path:
                return cmd_tmp_path

            args_callback = self.options['args-callback']
            if args_callback:
                args, kwargs = self.get_method(args_callback)
            else:
                args = self.options['args']
                kwargs = self.options['kwargs']

            # get command output
            out = getattr(CLIHelper(), self.command)(*args, **kwargs)
            # store in temp file to make it searchable
            # NOTE: we dont need to delete this at the the end since they are
            # created in the plugun tmp dir which is wiped at the end of the
            # plugin run.
            if type(out) == list:
                out = ''.join(out)
            elif type(out) == dict:
                out = str(out)

            cmd_tmp_path = mktemp_dump(out)
            self.cache.set('cmd_tmp_path', cmd_tmp_path)
            return cmd_tmp_path

        log.debug("no input provided")


@add_to_property_catalog
class YPropertyInput(YPropertyOverrideBase, YPropertyInputBase):

    @classmethod
    def _override_keys(cls):
        return ['input']
