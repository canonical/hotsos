import os
from functools import cached_property

from hotsos.core.factory import FactoryBase
from hotsos.core.host_helpers.cli import CLIHelper


class SYSCtlFactory(FactoryBase):
    """
    Factory to create interface objects to sysctl. This allows us to load
    values dynamically without continuously loaded from the kernel.
    """

    @cached_property
    def sysctl_all(self):
        sysctl_all = {}
        for kv in CLIHelper().sysctl_all():
            k, _, v = kv.partition("=")
            # squash whitespaces into a single whitespace
            sysctl_all[k.strip()] = ' '.join(v.strip().split())

        return sysctl_all

    def get(self, key):
        """
        Fetch systcl value for a given key. This is passed to the created
        objects as an interface instead of passing the full dict.
        """
        return self.sysctl_all.get(key)

    def __getattr__(self, name):
        """
        Return a value for given sysctl key.
        """
        return self.get(name)


class SYSCtlConfHelper():

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
                    value = split[2].split('#')[0].strip()

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
