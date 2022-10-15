import os


class SYSCtlHelper(object):

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
