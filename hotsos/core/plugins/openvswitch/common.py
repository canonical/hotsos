import abc
import re
from dataclasses import dataclass, field

from hotsos.core import plugintools
from hotsos.core.host_helpers import (
    APTPackageHelper,
    InstallInfoBase,
    PebbleHelper,
    SnapPackageHelper,
    SystemdHelper,
)
from hotsos.core.plugins.openstack.openstack import OST_SUNBEAM_SNAP_NAMES
from hotsos.core.ycheck.events import EventCallbackBase, EventHandlerBase
from hotsos.core.ycheck.common import GlobalSearcherAutoRegisterBase
from hotsos.core.utils import sorted_dict

OVS_SERVICES_EXPRS = [r'ovsdb[a-zA-Z-]*',
                      r'ovs-vswitch[a-zA-Z-]*',
                      r'ovn[a-zA-Z-]*',
                      'openvswitch-switch',
                      ]
PY_CLIENT_PREFIX = r"python3?-{}\S*"
_OVS_PKGS_CORE = ['openvswitch-switch',
                  'ovn',
                  ]
OVS_PKGS_CORE = _OVS_PKGS_CORE + \
                [PY_CLIENT_PREFIX.format(p) for p in _OVS_PKGS_CORE]
_OVS_PKGS_DEPS = ['libc-bin',
                  'openvswitch',
                  'ovsdbapp',
                  'openssl',
                  'openvswitch-switch-dpdk',
                  ]
OVS_PKGS_DEPS = _OVS_PKGS_DEPS + \
                [PY_CLIENT_PREFIX.format(p) for p in _OVS_PKGS_DEPS]

OVS_SNAPS_CORE = ['microovn'] + OST_SUNBEAM_SNAP_NAMES


class OpenvSwitchGlobalSearchBase(GlobalSearcherAutoRegisterBase):
    """ Base class for global searcher registration for OpenvSwitch. """
    plugin_name = "openvswitch"

    @classmethod
    @abc.abstractmethod
    def paths(cls):
        """ Returns a list of one or more paths to search. """


@dataclass
class OpenvSwitchInstallInfo(InstallInfoBase):
    """ OpenvSwitch installation information. """
    apt: APTPackageHelper = field(default_factory=lambda:
                                  APTPackageHelper(core_pkgs=OVS_PKGS_CORE,
                                                   other_pkgs=OVS_PKGS_DEPS))
    pebble: PebbleHelper = field(default_factory=lambda:
                                 PebbleHelper(
                                            service_exprs=OVS_SERVICES_EXPRS))
    systemd: SystemdHelper = field(default_factory=lambda:
                                   SystemdHelper(
                                            service_exprs=OVS_SERVICES_EXPRS))
    snaps: SnapPackageHelper = field(default_factory=lambda:
                                     SnapPackageHelper(
                                            core_snaps=OVS_SNAPS_CORE))


class OpenvSwitchChecks(plugintools.PluginPartBase):
    """ OpenvSwitch checks. """
    plugin_name = "openvswitch"
    plugin_root_index = 6

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        OpenvSwitchInstallInfo().mixin(self)

    @classmethod
    def is_runnable(cls):
        """
        Determine whether or not this plugin can and should be run.

        @return: True or False
        """
        # require at least one core package to be installed to run this plugin.
        if len(OpenvSwitchInstallInfo().apt.core) > 0:
            return True

        # This is to account for OpenStack Sunbeam
        return len(OpenvSwitchInstallInfo().snaps.core) > 0


class OpenvSwitchEventCallbackBase(EventCallbackBase):
    """ Base class for OpenvSwitch events callbacks. """
    @classmethod
    def global_event_tally_time_granularity_override(cls):
        return True

    @abc.abstractmethod
    def __call__(self):
        """ Callback method. """


class OpenvSwitchEventHandlerBase(OpenvSwitchChecks, EventHandlerBase):
    """ Base class for OpenvSwitch event handlers. """
    @property
    def summary(self):
        # mainline all results into summary root
        ret = self.run()
        if ret:
            return sorted_dict(ret)

        return None


class OVSDBTableBase():
    """
    Provides an interface to an OVSDB table. Records can be extracted from
    either 'get' or 'list' command outputs. We try 'get' first and of not found
    we search in output of 'list'.
    """
    def __init__(self, name):
        self.name = name

    @staticmethod
    def _convert_record_to_dict(record):
        """ Convert the ovsdb record dict format to a python dictionary. """
        out = {}
        if not record or record == '{}':
            return out

        expr = r'(\S+="[^"]+"|\S+=\S+),? ?'
        for _field in re.compile(expr).findall(record):
            for char in [',', '}', '{']:
                _field = _field.strip(char)

            key, _, val = _field.partition('=')
            out[key] = val.strip('"')

        return out

    @staticmethod
    def _get_cmd(table):
        raise NotImplementedError

    @staticmethod
    def _list_cmd(table):
        raise NotImplementedError

    def _fallback_query(self, column):
        """ Find first occurrence of column and return it. """
        for cmd in [self._list_cmd(self.name),
                    self._list_cmd(self.name.lower())]:
            for line in cmd():
                if not line.startswith(f'{column} '):
                    continue

                return line.partition(':')[2].strip()

        return None

    def get(self, record, column):
        """
        Try to get column using get command and failing that, try getting it
        from list.
        """
        value = self._get_cmd(self.name)(record=record, column=column)
        if not value:
            value = self._fallback_query(column=column)

        if not (value and value.startswith('{')):
            return value

        return self._convert_record_to_dict(value)

    def __getattr__(self, column):
        """ Get column for special records i.e. with key '.' """
        return self.get(record='.', column=column)
