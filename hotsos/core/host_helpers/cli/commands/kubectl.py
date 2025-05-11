from collections import UserList

from hotsos.core.host_helpers.cli.common import BinCmd, FileCmd

KubectlAliases = ['kubectl', 'microk8s.kubectl', 'k8s kubectl']


class KubectlBinCmdBase(BinCmd):
    """ Generic kubctl implementation for binary kubectl commands. Aims to
    support all kubectl commands and their subcommands. """
    KUBECTL_CMD = None

    def __init__(self, cmd, *args, **kwargs):
        cmd = (f'{cmd} {self.KUBECTL_CMD} --namespace {{namespace}} {{opt}} '
               '{subopts}')
        super().__init__(cmd, *args, **kwargs)


class KubectlLogsBinCmd(KubectlBinCmdBase):
    """ Implements kubectl logs binary command. """
    KUBECTL_CMD = 'logs'


class KubectlLogsFileCmd(FileCmd):
    """ Implementation for file-based kubectl logs command. """

    def __init__(self, path, *args, **kwargs):
        path = ('sos_commands/kubernetes/cluster-info/{namespace}/'
                'podlogs/{opt}/' + path + '_--namespace_{namespace}_'
                'logs_{opt}_{subopts}')
        super().__init__(path, *args, **kwargs)


class KubectlLogsCmds(UserList):
    """ Generate kubectl command variants. """

    def __init__(self):
        cmds = [KubectlLogsBinCmd(cmd) for cmd in KubectlAliases]
        cmds.extend([KubectlLogsFileCmd(cmd.replace('.', '_'))
                     for cmd in KubectlAliases])
        super().__init__(cmds)
