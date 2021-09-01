from core.plugins.juju import JujuChecksBase

YAML_PRIORITY = 1


class JujuCharmChecks(JujuChecksBase):

    def __call__(self):
        if self.charms:
            charms = ["{}-{}".format(c.name, c.version) for c in self.charms]
            self._output['charms'] = sorted(charms)
