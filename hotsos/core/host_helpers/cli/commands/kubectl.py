import os
from collections import UserList

from hotsos.core.host_helpers.cli.common import BinCmd, FileCmd

# See https://github.com/sosreport/sos/pull/4599 for the reason
# why the snap path is added.
KUBECTL_ALIASES = ['kubectl', 'k8s kubectl',
                   '/snap/k8s/current/bin/kubectl',
                   'microk8s kubectl']


def sos_convert_cmd_path(cmd):
    """
    Apply sosreport cmd path conversion rules.

    Converts a command into a file path used by sosreport to store output.
    """
    cmd = cmd.lstrip('/')
    cmd = cmd.replace('.', '_')
    cmd = cmd.replace(' ', '_')
    cmd = cmd.replace('/', '.')
    return cmd


# Paths checked by sos report
KUBE_CONFIGS = ['/etc/kubernetes/admin.conf',
                '/root/cdk/cdk_addons_kubectl_config',
                '/var/snap/microk8s/current/credentials/client.config']

# See https://kubernetes.io/docs/reference/kubectl/generated/kubectl_config for
# info on standard config paths.
#
# NOTE: the user can optionally set KUBECONFIG env var to override these paths.
DEFAULT_CFG_PATH = f"{os.environ.get('HOME', '~')}/.kube/config"


class KubectlBinCmdBase(BinCmd):
    """ Generic kubectl implementation for binary kubectl commands.

    Aims to support all kubectl commands and their subcommands in a format
    comparable to sosreport. This means that if e.g. sosreport executes the
    command with -o json then we need to do the same here for the binary
    version.
    """
    KUBECTL_CMD = None

    @property
    def _use_json_encoding(self):
        return self.KUBECTL_CMD == 'get'

    def __init__(self, cmd, *args, **kwargs):
        cmd = (f'{cmd} {self.KUBECTL_CMD} --namespace {{namespace}} {{opt}} '
               '{subopts}')

        # NOTE: sosreport runs kubectl get with -o json so we will do the
        # same for binary commands so that the api calls can be expect
        # consistent return type.
        if self._use_json_encoding:
            kwargs['json_decode'] = True

        super().__init__(cmd, *args, **kwargs)

    def __call__(self, *args, **kwargs):
        if self._use_json_encoding:
            _subopts = kwargs.get('subopts', "")
            if not _subopts:
                kwargs['subopts'] = "-o json"
            else:
                kwargs['subopts'] += " -o json"

        return super().__call__(*args, **kwargs)


class KubectlLogsBinCmd(KubectlBinCmdBase):
    """ Implements kubectl logs binary command. """
    KUBECTL_CMD = 'logs'


class KubectlFileBinCmd(FileCmd):
    """ Implements kubectl logs file command. """
    KUBECTL_CMD = 'logs'

    def __call__(self, *args, **kwargs):
        subopts = kwargs.get('subopts')
        if subopts:
            kwargs['subopts'] = subopts.replace(' ', '_')

        return super().__call__(*args, **kwargs)


class KubectlLogsCmds(UserList):
    """ Generate kubectl logs command variants. """

    def __init__(self):
        cmds = [KubectlLogsBinCmd(cmd) for cmd in KUBECTL_ALIASES]

        confs = [p.replace('/', '.') for p in KUBE_CONFIGS]
        paths = []
        for cmd in KUBECTL_ALIASES:
            cmd = sos_convert_cmd_path(cmd)
            paths.append('sos_commands/kubernetes/cluster-info/{namespace}/'
                         'podlogs/{opt}/' + cmd +
                         '_--namespace_{namespace}_logs_{opt}_{subopts}')

            paths.extend([(f'sos_commands/kubernetes/pods/{cmd}'
                           f'_--kubeconfig_{conf}'
                           '_--namespace_{namespace}_logs_{opt}'
                           '_{subopts}') for conf in
                          confs])

        for path in paths:
            cmds.append(KubectlFileBinCmd(path))

        super().__init__(cmds)


class KubectlGetBinCmd(KubectlBinCmdBase):
    """ Implements kubectl get """
    KUBECTL_CMD = 'get'


class KubectlGetCmds(UserList):
    """ Generate kubectl get command variants. """

    def __init__(self):
        cmds = [KubectlGetBinCmd(cmd) for cmd in KUBECTL_ALIASES]

        confs = [p.replace('/', '.') for p in KUBE_CONFIGS]
        paths = []
        for cmd in KUBECTL_ALIASES:
            cmd = sos_convert_cmd_path(cmd)
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
