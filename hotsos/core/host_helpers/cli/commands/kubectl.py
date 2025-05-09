from hotsos.core.host_helpers.cli.common import BinCmd, FileCmd
from hotsos.core.host_helpers.exceptions import SourceNotFound


class KubectlBinCmdBase(BinCmd):
    """ Implementation for kubectl commands to allow providing different
    variants. """
    # Set this to kubectl command
    KUBE_COMMAND = None

    def __init__(self, cmd, *args, **kwargs):
        cmd = cmd + f' {self.KUBE_COMMAND} --namespace {{namespace}} {{opt}} '
        super().__init__(cmd, *args, **kwargs)


class KubectlGetBinCmd(KubectlBinCmdBase):
    """ Implements kubectl get """
    KUBE_COMMAND = 'get'


class KubectlLogsBinCmd(BinCmd):
    """ Implements kubectl logs """
    KUBE_COMMAND = 'logs'

    def __init__(self, cmd, *args, **kwargs):
        cmd = (cmd + f' {self.KUBE_COMMAND} --namespace {{namespace}} {{opt}} '
               '-c {container}')
        super().__init__(cmd, *args, **kwargs)


class KubectlGetFileCmd(FileCmd):
    """ This is not yet supported by sosreport. """

    def __init__(self, path, *args, **kwargs):  # noqa pylint: disable=super-init-not-called
        super().__init__(path, *args, **kwargs)


class KubectlLogsFileCmd(FileCmd):
    """ Implementation for kubectl commands to allow providing different
    variants. """

    def __init__(self, path, *args, **kwargs):
        path = ('sos_commands/kubernetes/cluster-info/{namespace}/'
                'podlogs/{opt}/' + path + '_--namespace_{namespace}_'
                'logs_{opt}_-c_{container}')
        super().__init__(path, *args, **kwargs)
