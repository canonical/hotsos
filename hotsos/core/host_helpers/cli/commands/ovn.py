from collections import UserList

from hotsos.core.host_helpers.cli.common import BinCmd, FileCmd


OVNAliases = ['openstack-hypervisor.', 'microovn.']


class OVNDBCTLShowBinCmd(BinCmd):
    """ Implementation for binary ovndb ctl show commands providing support
        for different variants.
    """

    def __init__(self, ctl_command, *args, prefix=None, **kwargs):
        prefix = prefix or ''
        cmd = f'{prefix}{ctl_command} --no-leader-only show'
        super().__init__(cmd, *args, **kwargs)


class OVNDBCTLShowFileCmd(FileCmd):
    """ Implementation for file-based ovndb ctl show commands providing support
        for different variants.
    """

    def __init__(self, ctl_command, *args, prefix=None, **kwargs):
        prefix = prefix or ''
        path = (f'sos_commands/ovn_central/{prefix}{ctl_command}_'
                '--no-leader-only_show')
        super().__init__(path, *args, **kwargs)


class OVNDBCTLShowCmds(UserList):
    """ Generate ovn-nbctl show command variants. """

    def __init__(self, ctl_command):
        cmds = [OVNDBCTLShowBinCmd(ctl_command=ctl_command)]
        cmds.extend([OVNDBCTLShowBinCmd(ctl_command=ctl_command,
                     prefix=prefix) for prefix in OVNAliases])
        cmds.append(OVNDBCTLShowFileCmd(ctl_command=ctl_command))
        # sosreport < 4.5
        cmds.append(FileCmd(f'sos_commands/ovn_central/{ctl_command}_show'))
        cmds.extend([OVNDBCTLShowFileCmd(ctl_command=ctl_command,
                     prefix=prefix) for prefix in OVNAliases])
        super().__init__(cmds)


class OVNDBCTLListBinCmd(BinCmd):
    """ Implementation for binary ovndb ctl list commands providing support
        for different variants.
    """

    def __init__(self, ctl_command, *args, prefix=None, **kwargs):
        prefix = prefix or ''
        cmd = f'{prefix}{ctl_command} --no-leader-only list' + ' {table}'
        super().__init__(cmd, *args, **kwargs)


class OVNDBCTLListFileCmd(FileCmd):
    """ Implementation for file-based ovndb ctl list commands providing support
        for different variants.
    """

    def __init__(self, ctl_command, *args, prefix=None, **kwargs):
        prefix = prefix or ''
        path = (f'sos_commands/ovn_central/{prefix}{ctl_command}_'
                '--no-leader-only_list_{table}')
        super().__init__(path, *args, **kwargs)


class OVNDBCTLListCmds(UserList):
    """ Generate ovn-nbctl list command variants. """

    def __init__(self, ctl_command):
        cmds = [OVNDBCTLListBinCmd(ctl_command=ctl_command)]
        cmds.extend([OVNDBCTLListBinCmd(ctl_command=ctl_command,
                     prefix=prefix) for prefix in OVNAliases])
        cmds.append(OVNDBCTLListFileCmd(ctl_command=ctl_command))
        # sosreport < 4.5
        cmds.append(FileCmd(f'sos_commands/ovn_central/{ctl_command}_list'))
        cmds.extend([OVNDBCTLListFileCmd(ctl_command=ctl_command,
                     prefix=prefix) for prefix in OVNAliases])
        super().__init__(cmds)
