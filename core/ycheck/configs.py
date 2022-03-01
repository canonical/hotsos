from core import constants
from core.issues import issue_utils
from core.log import log
from core.ycheck import (
    YDefsLoader,
    ChecksBase,
    YDefsSection,
)


class YConfigChecker(ChecksBase):
    """
    This class is used to peform checks on any kind of config. See
    defs/config_checks.yaml.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._check_defs = {}

    def load(self):
        plugin_checks = YDefsLoader('config_checks').load_plugin_defs()
        if not plugin_checks:
            return

        yconfigchecks = YDefsSection(constants.PLUGIN_NAME, plugin_checks)
        log.debug("sections=%s, checks=%s",
                  len(yconfigchecks.branch_sections),
                  len(yconfigchecks.leaf_sections))
        if yconfigchecks.requires and not yconfigchecks.requires.passes:
            log.debug("plugin not runnable - skipping config checks")
            return

        for cfg_check in yconfigchecks.leaf_sections:
            # This is only available if there is a section above us
            if cfg_check.parent:
                group_name = cfg_check.parent.name
            else:
                group_name = None

            self._check_defs[cfg_check.name] = {
                'group': group_name,
                'config': cfg_check.config,
                'requires': cfg_check.requires,
                'raises': cfg_check.raises}

    def run(self):
        for name, cfg_check in self._check_defs.items():
            log.debug("config check section=%s", name)
            if not cfg_check['requires'].passes:
                message = cfg_check['raises'].message
                if not message:
                    rcache = cfg_check['requires'].cache
                    message = ("{} config {} expected to be {} {} "
                               "but actual={}".format(cfg_check['group'],
                                                      rcache['config.key'],
                                                      rcache['config.op'],
                                                      rcache['config.value'],
                                                      rcache['config.actual']))

                issue = cfg_check['raises'].type(message)
                issue_utils.add_issue(issue)
