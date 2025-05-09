from collections import UserList

from hotsos.core.host_helpers.cli.common import BinCmd, FileCmd

KubectlAliases = ['kubectl', 'microk8s.kubectl', 'k8s kubectl']

# Paths checked by sos report
KUBE_CONFIGS = ['/etc/kubernetes/admin.conf',
                '/root/cdk/cdk_addons_kubectl_config',
                '/var/snap/microk8s/current/credentials/client.config']


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


class KubectlLogsCmds(UserList):
    """ Generate kubectl logs command variants. """

    def __init__(self):
        cmds = [KubectlLogsBinCmd(cmd) for cmd in KubectlAliases]

        confs = [p.replace('/', '.') for p in KUBE_CONFIGS]
        paths = []
        for cmd in KubectlAliases:
            cmd = cmd.replace('.', '_').replace(' ', '_')
            paths.append('sos_commands/kubernetes/cluster-info/{namespace}/'
                         'podlogs/{opt}/' + cmd +
                         '_--namespace_{namespace}_logs_{opt}_{subopts}')

            paths.extend([(f'sos_commands/kubernetes/pods/{cmd}'
                           f'_--kubeconfig_{conf}'
                           '_--namespace_{namespace}_logs_{opt}') for conf in
                          confs])

        for path in paths:
            cmds.append(FileCmd(path))

        super().__init__(cmds)


class KubectlGetBinCmd(KubectlBinCmdBase):
    """ Implements kubectl get """
    KUBECTL_CMD = 'get'


class KubectlGetCmds(UserList):
    """ Generate kubectl get command variants. """

    def __init__(self):
        cmds = [KubectlGetBinCmd(cmd) for cmd in KubectlAliases]

        confs = [p.replace('/', '.') for p in KUBE_CONFIGS]
        paths = []
        for cmd in KubectlAliases:
            cmd = cmd.replace('.', '_').replace(' ', '_')
            paths.extend([(f'sos_commands/kubernetes/services/{cmd}'
                           f'_--kubeconfig_{conf}'
                           '_get_-o_json_--namespace_{namespace}_{opt}')
                          for conf in confs])

            paths.append('sos_commands/kubernetes/cluster-info/{namespace}/'
                         + cmd +
                         '_get_-o_json_--namespace_{namespace}_{opt}')

        for path in paths:
            cmds.append(FileCmd(path, json_decode=True))

        super().__init__(cmds)
