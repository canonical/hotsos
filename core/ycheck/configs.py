from core import constants
from core.issues import issue_utils
from core.log import log
from core.ycheck import (
    YDefsLoader,
    AutoChecksBase,
    YDefsSection,
)


class YConfigChecker(AutoChecksBase):
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

        group = YDefsSection(constants.PLUGIN_NAME, plugin_checks,
                             checks_handler=self)
        log.debug("sections=%s, checks=%s",
                  len(group.branch_sections),
                  len(group.leaf_sections))

        for cfg_check in group.leaf_sections:
            # This is only available if there is a section above us
            if cfg_check.parent:
                group_name = cfg_check.parent.name
            else:
                group_name = None

            self._check_defs[cfg_check.name] = {
                'group': group_name,
                'config': cfg_check.config,
                'requires': cfg_check.requires,
                'settings': dict(cfg_check.settings),
                'raises': cfg_check.raises}

    def run(self):
        for name, cfg_check in self._check_defs.items():
            # this is optional
            requires = cfg_check['requires']
            if requires and not cfg_check['requires'].passes:
                continue

            log.debug("config check section=%s", name)
            message = cfg_check['raises'].message
            for cfg_key, settings in cfg_check['settings'].items():
                op = settings['operator']
                value = settings['value']
                section = settings.get('section')
                allow_unset = bool(settings.get('allow-unset', False))
                raise_issue = False
                actual = cfg_check['config'].actual(cfg_key, section=section)
                log.debug("checking config %s %s %s (actual=%s)", cfg_key, op,
                          value, actual)
                if not cfg_check['config'].check(actual, value, op,
                                                 allow_unset=allow_unset):
                    raise_issue = True

                if raise_issue:
                    if not message:
                        message = ("{} config {} expected to be {} {} "
                                   "but actual={}".format(cfg_check['group'],
                                                          cfg_key, op, value,
                                                          actual))

                    issue = cfg_check['raises'].type(message)
                    issue_utils.add_issue(issue)
                    # move on to next set of checks
                    break
