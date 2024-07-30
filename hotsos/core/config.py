import abc
import copy
from collections import UserDict
from dataclasses import dataclass

from hotsos.core.exceptions import (
    NameAlreadyRegisteredError,
)


@dataclass
class ConfigOpt:
    """ Basic information required to define a config option. """

    name: str
    description: str
    default_value: str
    value_type: type


class ConfigOptGroupBase(UserDict):
    """ Base class for defining groups of config options. """
    def __init__(self):
        super().__init__()
        self.opts = {}

    @property
    @abc.abstractmethod
    def name(self):
        """ OptGroup name """

    def __getattribute__(self, name):
        """ Ensure dict contains all registered options. """
        if name == 'data':
            return {_name: opt.default_value
                    for _name, opt in self.opts.items()}

        return super().__getattribute__(name)

    def add(self, opt):
        self.opts[opt.name] = opt


class HotSOSConfigOpts(ConfigOptGroupBase):
    """ Group of hotsos common options. """
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
                           description='Set to True to enable debug logging '
                                       'to standard output',
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
        self.add(ConfigOpt(name='event_filter',
                           description=("Name of event to run. Set this if "
                                        "you want to run a single event. "
                                        "Useful for testing/debugging"),
                           default_value='', value_type=str))
        self.add(ConfigOpt(name='scenario_filter',
                           description=("Name of scenario to run. Set this if "
                                        "you want to run a single scenario. "
                                        "Useful for testing/debugging"),
                           default_value='', value_type=str))
        self.add(ConfigOpt(name='debug_log_levels',
                           description=("Debug mode log levels for "
                                        "submodules/dependencies"),
                           default_value={'propertree': 'WARNING',
                                          'searchkit': 'DEBUG'},
                           value_type=dict))

    @property
    def name(self):
        return 'hotsos'


class SearchtoolsConfigOpts(ConfigOptGroupBase):
    """ Group of search options. """
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

    @property
    def name(self):
        return 'search'


class RegisteredOpts(UserDict):
    """ Registers config options. """
    def __init__(self, *optgroups):
        self.optsgroups = []
        data = {}
        for optgroup in optgroups:
            optgroup = optgroup()
            self.optsgroups.append(optgroup)
            a = [name.lower() for name in data]
            b = [name.lower() for name in optgroup]
            if set(a).intersection(b):
                raise NameAlreadyRegisteredError(
                    f"optgroup '{optgroup.name}' contains one or "
                    "more names that have already been registered")

            data.update(optgroup)

        super().__init__(data)

    def __setitem__(self, key, item):
        for group in self.optsgroups:
            if key in group.opts:
                item = group.opts[key].value_type(item)
                break
        else:
            raise KeyError(
                f"config option '{key}' not found in any optgroup")

        self.data[key] = item


class ConfigMeta(abc.ABCMeta):
    """ Metadata used to register config options. """
    REGISTERED = RegisteredOpts(HotSOSConfigOpts,
                                SearchtoolsConfigOpts)
    CONFIG = copy.deepcopy(REGISTERED)

    def __getattr__(cls, key):
        if key in cls.CONFIG:
            return cls.CONFIG[key]

        raise KeyError(f"fetching unknown config '{key}'.")

    def __setattr__(cls, key, val):
        if key in cls.CONFIG:
            cls.CONFIG[key] = val
            return
        if key not in ['__abstractmethods__', '_abc_impl', 'CONFIG',
                       'REGISTERED']:
            raise KeyError(f"setting unknown config '{key}'.")

        super().__setattr__(key, val)


class HotSOSConfig(metaclass=ConfigMeta):
    """ The main registry of config options.

    Options are automatically registered on module load."""

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
