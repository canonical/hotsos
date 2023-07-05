import abc
import copy
from collections import UserDict


class ConfigException(Exception):
    pass


class ConfigOpt(object):

    def __init__(self, name, description, default_value, value_type):
        self.name = name
        self.description = description
        self.default_value = default_value
        self.value_type = value_type


class ConfigOptGroupBase(UserDict):

    def __init__(self):
        self.opts = {}

    @property
    @abc.abstractmethod
    def name(self):
        """ OptGroup name """

    @property
    def data(self):
        d = {}
        for name, opt in self.opts.items():
            d[name] = opt.default_value

        return d

    def add(self, opt):
        self.opts[opt.name] = opt


class HotSOSConfigOpts(ConfigOptGroupBase):

    def __init__(self):
        super().__init__()
        self.add(ConfigOpt(name='data_root',
                           description=('This is the filesystem root used for '
                                        'all files and is typically / or a '
                                        'path to a sosreport'),
                           default_value=None, value_type=str))
        self.add(ConfigOpt(name='force_mode',
                           description=('Plugin execution is usually gated '
                                        'on a set of conditions. Setting this '
                                        'to True bypasses these conditions '
                                        'and forces all plugins to run'),
                           default_value=False, value_type=bool))
        self.add(ConfigOpt(name='global_tmp_dir',
                           description=('A temporary directory created at the '
                                        'start of execution and visible to '
                                        'all plugins.'),
                           default_value=None, value_type=str))
        self.add(ConfigOpt(name='plugin_tmp_dir',
                           description=('A temporary directory created for '
                                        'each plugin.'),
                           default_value=None, value_type=str))
        self.add(ConfigOpt(name='use_all_logs',
                           description=('Automatically convert log paths to '
                                        'glob e.g. <path> becomes <path>*'),
                           default_value=False, value_type=bool))
        self.add(ConfigOpt(name='machine_readable',
                           description=('If set to True, the summary output'
                                        'will contain extra information '
                                        'that might be useful if the output '
                                        'is being read by an application.'),
                           default_value=False, value_type=bool))
        self.add(ConfigOpt(name='part_name',
                           description=('Plugins have many parts each with '
                                        'its own name and this will be set to '
                                        'the current part being executed.'),
                           default_value=None, value_type=str))
        self.add(ConfigOpt(name='repo_info',
                           description=('Source repository sha1 from which '
                                        'the current build was created'),
                           default_value=None, value_type=str))
        self.add(ConfigOpt(name='hotsos_version',
                           description='Version of hotsos being run.',
                           default_value=None, value_type=str))
        self.add(ConfigOpt(name='debug_mode',
                           description='Set to True to enable debug logging',
                           default_value=False, value_type=bool))
        self.add(ConfigOpt(name='plugin_yaml_defs',
                           description='Path to yaml-defined checks.',
                           default_value=None, value_type=str))
        self.add(ConfigOpt(name='templates_path',
                           description='Path to jinja templates.',
                           default_value='templates', value_type=str))
        self.add(ConfigOpt(name='plugin_name',
                           description='Name of current plugin being executed',
                           default_value=None, value_type=str))
        self.add(ConfigOpt(name='event_tally_granularity',
                           description=("By default event tallies are listed "
                                        "by date in the summary. This option "
                                        "can be set to one of 'date' or "
                                        "'time' to get the corresponding "
                                        "granularity of results."),
                           default_value='date', value_type=str))
        self.add(ConfigOpt(name='command_timeout',
                           description=("Maximum time in seconds before "
                                        "command execution will timeout. Used "
                                        "by host_helpers.cli when executing "
                                        "binary commands"),
                           default_value=300, value_type=int))

    @property
    def name(self):
        return 'hotsos'


class SearchtoolsConfigOpts(ConfigOptGroupBase):

    def __init__(self):
        super().__init__()
        self.add(ConfigOpt(name='max_parallel_tasks',
                           description=('Maximum parallelism for searching '
                                        'files concurrently'),
                           default_value=8, value_type=int))
        self.add(ConfigOpt(name='max_logrotate_depth',
                           description=('When log paths are expanded using '
                                        'use_all_logs and they are logrotated '
                                        'log files, this is used to limit the '
                                        'logrotate history in days.'),
                           default_value=7, value_type=int))
        self.add(ConfigOpt(name='allow_constraints_for_unverifiable_logs',
                           description=('Search constraints use a binary '
                                        'search that sometimes needs to '
                                        'seek backwards to find a last '
                                        'known good line i.e. in log files '
                                        "that contain lines that don't start "
                                        'with a timestamp we treat those as '
                                        'unverifiable and so have to find the '
                                        'most recent verifiable line which '
                                        'can be ahead or behind the current '
                                        'position. Seeking backwards seems to '
                                        'force a SEEK_SET in the kernel '
                                        'regardless of what whence is set to '
                                        'which for large files becomes very '
                                        'slow as it will start from 0 each '
                                        'time. Backwards seeking is now not '
                                        'supported by default and requires '
                                        'setting this option to True '
                                        'to enable search constraints for '
                                        'files that contain unverifiable '
                                        'lines.'),
                           default_value=False, value_type=bool))

    @property
    def name(self):
        return 'search'


class RegisteredOpts(UserDict):

    def __init__(self, *optgroups):
        self.optsgroups = []
        self.data = {}
        for optgroup in optgroups:
            optgroup = optgroup()
            self.optsgroups.append(optgroup)
            a = [name.lower() for name in self.data.keys()]
            b = [name.lower() for name in optgroup.keys()]
            if set(a).intersection(b):
                raise Exception("optgroup '{}' contains one or more names "
                                "that have already been registered".
                                format(optgroup.name))

            self.data.update(optgroup)

    def __setitem__(self, key, item):
        for group in self.optsgroups:
            if key in group.opts:
                item = group.opts[key].value_type(item)
                break
        else:
            raise Exception("config option '{}' not found in any optgrpup".
                            format(key))

        self.data[key] = item


class ConfigMeta(abc.ABCMeta):
    REGISTERED = RegisteredOpts(HotSOSConfigOpts,
                                SearchtoolsConfigOpts)
    CONFIG = copy.deepcopy(REGISTERED)

    def __getattr__(cls, key):
        if key in cls.CONFIG:
            return cls.CONFIG[key]

        raise ConfigException("fetching unknown config '{}'.".
                              format(key))

    def __setattr__(cls, key, val):
        if key in cls.CONFIG:
            cls.CONFIG[key] = val
            return
        if key not in ['__abstractmethods__', '_abc_impl', 'CONFIG',
                       'REGISTERED']:
            raise ConfigException("setting unknown config '{}'.".
                                  format(key))

        super().__setattr__(key, val)


class HotSOSConfig(object, metaclass=ConfigMeta):

    @classmethod
    def reset(cls):
        """ Reset all config options to their default values. """
        cls.CONFIG = copy.deepcopy(cls.REGISTERED)

    @classmethod
    def set(cls, **config_options):
        """
        Provides a way to set multiple config options at once.

        @param config_options: a dictionary of one or more config option to
                               set.
        """
        for k, v in config_options.items():
            setattr(cls, k, v)
