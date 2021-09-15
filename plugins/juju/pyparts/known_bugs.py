from core.plugins.juju import JujuBugChecksBase


class JujuBugChecks(JujuBugChecksBase):

    def __init__(self):
        """ see defs/bugs.yaml """
        super().__init__(yaml_defs_group="common")
