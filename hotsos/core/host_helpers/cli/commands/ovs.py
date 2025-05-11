import abc
from collections import UserList

from hotsos.core.log import log
from hotsos.core.host_helpers.cli.common import BinCmd, FileCmd, CmdOutput
from hotsos.core.host_helpers.exceptions import (
    CLIExecError,
    SourceNotFound,
)

OVSAliases = ['openstack-hypervisor.', 'microovn.']


class OVSVSCtlCmdsBase(UserList):
    """ Base for generating ovs-vsctl command variants. """
    CMD = None
    ARGS = None
    SINGLELINE = False

    @abc.abstractmethod
    def get_sos_path(self, prefix):
        """ Return path to sosereport file output. """

    def __init__(self):
        cmd = f'ovs-vsctl {self.CMD}'
        if self.ARGS:
            cmd += f' {self.ARGS}'

        # binary commands
        cmds = [BinCmd(cmd, singleline=self.SINGLELINE)]
        cmds.extend([BinCmd(f'{prefix}{cmd}', singleline=self.SINGLELINE)
                    for prefix in OVSAliases])
        # file-based commands
        cmds.append(FileCmd(self.get_sos_path(prefix=''),
                            singleline=self.SINGLELINE))
        cmds.extend([FileCmd(self.get_sos_path(prefix=prefix),
                             singleline=self.SINGLELINE)
                    for prefix in OVSAliases])
        super().__init__(cmds)


class OVSVSCtlGetCmds(OVSVSCtlCmdsBase):
    """ Generate ovs-vsctl get command variants. """
    CMD = 'get'
    ARGS = '{table} {record} {column}'
    SINGLELINE = True

    def get_sos_path(self, prefix):
        return (f'sos_commands/openvswitch/{prefix}ovs-vsctl_-t_5_'
                f'{self.CMD}_{self.ARGS.replace(" ", "_")}')


class OVSVSCtlListCmds(OVSVSCtlCmdsBase):
    """ Generate ovs-vsctl list command variants. """
    CMD = 'list'
    ARGS = '{table}'

    def get_sos_path(self, prefix):
        return (f'sos_commands/openvswitch/{prefix}ovs-vsctl_-t_5_{self.CMD}_'
                f'{self.ARGS.replace(" ", "_")}')


class OVSVSCtlListBrCmds(OVSVSCtlCmdsBase):
    """ Generate ovs-vsctl list-br command variants. """
    CMD = 'list-br'

    def get_sos_path(self, prefix):
        return f'sos_commands/openvswitch/{prefix}ovs-vsctl_-t_5_{self.CMD}'


class OVSAppCtlBinCmd(BinCmd):
    """ Implements ovs-appctl binary command. """

    def __call__(self, *args, **kwargs):
        # Set defaults for optional args
        for key in ['flags', 'args']:
            if key not in kwargs:
                kwargs[key] = ''

        return super().__call__(*args, **kwargs)


class OVSAppCtlFileCmd(FileCmd):
    """ Implements ovs-appctl file-based command. """

    def __init__(self, *args, prefix=None, **kwargs):
        if not prefix:
            prefix = ''

        path = (f'sos_commands/openvswitch/{prefix}ovs-appctl_'
                '{command}{flags}{args}')
        super().__init__(path, *args, **kwargs)

    def __call__(self, *args, **kwargs):
        for key in ['flags', 'args']:
            if key in kwargs:
                kwargs[key] = f'_{kwargs[key]}'
            else:
                kwargs[key] = ''

        if 'args' in kwargs and kwargs['command'].startswith('dpctl/'):
            # e.g. this would be for dpctl datapath
            kwargs['args'] = kwargs['args'].replace('@', '_')

        kwargs['command'] = kwargs['command'].replace('/', '.')
        try:
            out = super().__call__(*args, **kwargs)
        except SourceNotFound:
            log.debug("%s: source not found: %s", self.__class__.__name__,
                      self.path)
            raise

        return out


class OVSAppCtlCmds(UserList):
    """ Generate ovs-appctl command variants. """

    def __init__(self):
        cmd = 'ovs-appctl'
        # binary commands
        cmds = [OVSAppCtlBinCmd(cmd + ' {command} {flags} {args}')]
        cmds.extend([OVSAppCtlBinCmd(f"{prefix}{cmd}" +
                                     ' {command} {flags} {args}')
                    for prefix in OVSAliases])
        # file-based commands
        cmds.append(OVSAppCtlFileCmd())
        cmds.extend([OVSAppCtlFileCmd(prefix=prefix)
                    for prefix in OVSAliases])
        super().__init__(cmds)


OFPROTOCOL_VERSIONS = [
    "OpenFlow15",
    "OpenFlow14",
    "OpenFlow13",
    "OpenFlow12",
    "OpenFlow11",
    "OpenFlow10",
]


class OVSOFCtlBinCmd(BinCmd):
    """ Implementation of ovs-ofctl binary command. """
    BIN_CMD = 'ovs-ofctl'

    def __init__(self, *args, prefix=None, **kwargs):
        self.prefix = prefix
        super().__init__(*args, **kwargs)

    def __call__(self, *args, **kwargs):
        """
        First try without specifying protocol version. If error is raised
        try with different versions until we get a result.
        """
        self.cmd = f"{self.BIN_CMD} {self.cmd}"
        if self.prefix:
            self.cmd = f'{self.prefix}{self.cmd}'

        try:
            return super().__call__(*args, **kwargs)
        except CLIExecError:
            log.debug("%s: command with no protocol version failed",
                      self.__class__.__name__)

        # If the command raised an exception it will have been caught by the
        # catch_exceptions decorator and [] returned. We have no way of knowing
        # if that was the actual return or an exception was raised so we just
        # go ahead and retry with specific OF versions until we get a result.
        for ver in OFPROTOCOL_VERSIONS:
            log.debug("%s: trying again with protocol version %s",
                      self.__class__.__name__, ver)
            self.reset()
            self.cmd = f"{self.BIN_CMD} -O {ver} {self.cmd}"
            if self.prefix:
                self.cmd = f'{self.prefix}{self.cmd}'

            try:
                return super().__call__(*args, **kwargs)
            except CLIExecError:
                log.debug("%s: command with protocol version %s failed",
                          self.__class__.__name__, ver)

        return CmdOutput([])


class OVSOFCtlFileCmd(FileCmd):
    """ Implementation of ovs-ofctl file-based command. """

    def __init__(self, *args, prefix=None, **kwargs):
        if not prefix:
            prefix = ''

        path = (f'sos_commands/openvswitch/{prefix}ovs-ofctl'
                '{ofversion}_{command}_{args}')
        super().__init__(path, *args, **kwargs)

    def __call__(self, *args, **kwargs):
        """
        We do this in reverse order to bin command since it won't actually
        raise an error.
        """
        for ver in OFPROTOCOL_VERSIONS:
            log.debug("%s: trying again with protocol version %s",
                      self.__class__.__name__, ver)
            self.reset()
            try:
                kwargs['ofversion'] = f'_-O_{ver}'
                out = super().__call__(*args, **kwargs)
                if out.value and 'version negotiation failed' in out.value[0]:
                    continue

                return out
            except SourceNotFound:
                pass

        try:
            kwargs['ofversion'] = ''
            return super().__call__(*args, **kwargs)
        except SourceNotFound:
            log.debug("%s: command with no protocol version failed",
                      self.__class__.__name__)

        return None


class OVSOFCtlCmds(UserList):
    """ Generate ovs-ofctl command variants. """

    def __init__(self):
        # binary
        cmds = [OVSOFCtlBinCmd('{command} {args}')]
        cmds.extend([OVSOFCtlBinCmd('{command} {args}', prefix=prefix)
                    for prefix in OVSAliases])
        # file-based
        cmds.append(OVSOFCtlFileCmd())
        cmds.extend([OVSOFCtlFileCmd(prefix=prefix)
                    for prefix in OVSAliases])
        super().__init__(cmds)
