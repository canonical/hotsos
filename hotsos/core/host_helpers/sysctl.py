import os

from hotsos.core.host_helpers.common import HostHelperFactoryBase
from hotsos.core.host_helpers.cli import CLIHelper


class SYSCtl(object):

    def __init__(self, root, f_get):
        self.root = root
        self.f_get = f_get

    def __getattr__(self, key):
        return self.f_get("{}.{}".format(self.root, key))


class SYSCtlFactory(HostHelperFactoryBase):

    def __init__(self):
        self._sysctl_all = {}

    @property
    def sysctl_all(self):
        if self._sysctl_all:
            return self._sysctl_all

        for kv in CLIHelper().sysctl_all():
            k, _, v = kv.partition("=")
            # squash whitespaces into a single whitespace
            self._sysctl_all[k.strip()] = ' '.join(v.strip().split())

        return self._sysctl_all

    def get(self, key):
        """
        Fetch systcl value for a given key.
        """
        return self.sysctl_all.get(key)

    def __getattr__(self, root):
        """
        Return a SYSCtl object for a given root key. This is useful for yaml
        defs where the full key path is not a valid property name so can be
        accessed using getattr().
        """
        return SYSCtl(root, self.get)


class SYSCtlConfHelper(object):

    def __init__(self, path):
        self.path = path
        self._config = {}
        self._read_conf()

    @property
    def setters(self):
        """
        Returns a dict of keys and the value they are set to.
        """
        if not self._config:
            return {}

        return self._config['set']

    @property
    def unsetters(self):
        """
        Returns a dict of keys that are unset/reset.
        """
        if not self._config:
            return {}

        return self._config['unset']

    def _read_conf(self):
        if not os.path.isfile(self.path):
            return

        setters = {}
        unsetters = {}
        with open(self.path) as fd:
            for line in fd.readlines():
                if line.startswith("#"):
                    continue

                split = line.partition("=")
                if split[1]:
                    key = split[0].strip()
                    value = split[2].strip()

                    # ignore wildcarded keys'
                    if '*' in key:
                        continue

                    setters[key] = value
                elif line.startswith('-'):
                    key = line.partition('-')[2].strip()
                    unsetters[key] = None
                    continue

        self._config['set'] = setters
        self._config['unset'] = unsetters
