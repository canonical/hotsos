from core import checks


class JujuBugChecks(checks.BugChecksBase):

    def __init__(self):
        """ see defs/bugs.yaml """
        super().__init__(yaml_defs_group="common")
