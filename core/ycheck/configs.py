import os
import yaml

from core import constants
from core.issues import issue_utils
from core.log import log
from core.ycheck import (
    AutoChecksBase,
    YAMLDefConfig,
    YAMLDefInput,
    YAMLDefExpr,
    YAMLDefMessage,
    YAMLDefRequires,
    YAMLDefSettings,
    YAMLDefIssueType,
)
from core.ystruct import YAMLDefSection


class YConfigChecker(AutoChecksBase):
    """
    This class is used to peform checks on any kind of config. See
    defs/config_checks.yaml.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._check_defs = {}

    def load(self):
        path = os.path.join(constants.PLUGIN_YAML_DEFS, "config_checks.yaml")
        with open(path) as fd:
            yaml_defs = yaml.safe_load(fd.read())

        if not yaml_defs:
            return

        log.debug("loading config check definitions for plugin '%s'",
                  constants.PLUGIN_NAME)
        overrides = [YAMLDefInput, YAMLDefExpr, YAMLDefMessage,
                     YAMLDefRequires, YAMLDefConfig, YAMLDefSettings,
                     YAMLDefIssueType]
        # TODO: need a better way to provide this instance to the input
        #       override.
        YAMLDefInput.EVENT_CHECK_OBJ = self
        plugin = yaml_defs.get(constants.PLUGIN_NAME, {})
        group = YAMLDefSection(constants.PLUGIN_NAME, plugin,
                               override_handlers=overrides)
        log.debug("sections=%s, events=%s",
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
                'message': cfg_check.message,
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
            message = None
            if cfg_check['message']:
                message = str(cfg_check['message'])

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
                    if message:
                        _message = message
                    else:
                        _message = ("{} config {} expected to be {} {} "
                                    "but actual={}".format(cfg_check['group'],
                                                           cfg_key, op, value,
                                                           actual))

                    issue = cfg_check['raises'].issue(_message)
                    issue_utils.add_issue(issue)
                    # move on to next set of checks
                    break
