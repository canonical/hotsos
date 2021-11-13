import os
import yaml

from core import constants
from core.log import log
from core.known_bugs_utils import (
    add_known_bug,
    BugSearchDef,
)
from core.ycheck import (
    AutoChecksBase,
    YAMLDefInput,
    YAMLDefExpr,
    YAMLDefMessage,
)
from core.ystruct import YAMLDefSection
from core.searchtools import FileSearcher


class YBugChecker(AutoChecksBase):
    """
    Class used to identify bugs by matching content from files or commands.
    Searches are defined in defs/bugs.yaml per plugin and run automatically.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, searchobj=FileSearcher(), **kwargs)
        self._bug_defs = None

    def _load_bug_definitions(self):
        """ Load bug search definitions from yaml """
        path = os.path.join(constants.PLUGIN_YAML_DEFS, "bugs.yaml")
        with open(path) as fd:
            yaml_defs = yaml.safe_load(fd.read())

        if not yaml_defs:
            return

        plugin_bugs = yaml_defs.get(constants.PLUGIN_NAME, {})
        overrides = [YAMLDefInput, YAMLDefExpr, YAMLDefMessage]
        # TODO: need a better way to provide this instance to the input
        #       override.
        YAMLDefInput.EVENT_CHECK_OBJ = self
        plugin = YAMLDefSection(constants.PLUGIN_NAME, plugin_bugs,
                                override_handlers=overrides)
        log.debug("loading plugin '%s' bugs - sections=%s, events=%s",
                  plugin.name,
                  len(plugin.branch_sections),
                  len(plugin.leaf_sections))
        bug_defs = []
        for bug in plugin.leaf_sections:
            id = bug.name
            message_format = bug.message_format_result_groups
            if message_format:
                message_format = message_format.format_groups

            pattern = bug.expr.value
            datasource = bug.input.path
            # NOTE: pattern can be string or list of strings
            bdef = {'def': BugSearchDef(
                               pattern,
                               bug_id=str(id),
                               hint=bug.hint.value,
                               message=str(bug.message),
                               message_format_result_groups=message_format),
                    'datasource': datasource}

            log.debug("bug=%s path=%s", id, datasource)
            bug_defs.append(bdef)

        self._bug_defs = bug_defs

    @property
    def bug_definitions(self):
        """
        @return: dict of SearchDef objects and datasource for all entries in
        bugs.yaml under _yaml_defs_group.
        """
        if self._bug_defs is not None:
            return self._bug_defs

        self._load_bug_definitions()
        return self._bug_defs

    def load(self):
        for bugsearch in self.bug_definitions:
            self.searchobj.add_search_term(bugsearch["def"],
                                           bugsearch["datasource"])

    def run(self, results):
        for bugsearch in self.bug_definitions:
            tag = bugsearch["def"].tag
            _results = results.find_by_tag(tag)
            if _results:
                if bugsearch["def"].message_format_result_groups:
                    message = bugsearch["def"].rendered_message(_results[0])
                    add_known_bug(tag, message)
                else:
                    add_known_bug(tag, bugsearch["def"].message)
