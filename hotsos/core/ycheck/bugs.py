from hotsos.core.config import HotSOSConfig
from hotsos.core.log import log
from hotsos.core.issues import utils, LaunchpadBug
from hotsos.core.ycheck import (
    YDefsLoader,
    YDefsSection,
    ChecksBase,
)
from hotsos.core.searchtools import FileSearcher, SearchDef


class YBugChecker(ChecksBase):
    """ Class used to identify bugs by matching criteria defined in yaml. """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, searchobj=FileSearcher(), **kwargs)
        self._checks = None

    def _load_bug_checks(self):
        """ Load bug check definitions from yaml. """
        plugin_bugs = YDefsLoader('bugs').load_plugin_defs()
        if not plugin_bugs:
            return

        ybugchecks = YDefsSection(HotSOSConfig.PLUGIN_NAME, plugin_bugs)
        log.debug("loaded plugin '%s' bugs - sections=%s, events=%s",
                  ybugchecks.name,
                  len(ybugchecks.branch_sections),
                  len(ybugchecks.leaf_sections))
        if ybugchecks.requires and not ybugchecks.requires.passes:
            log.debug("plugin '%s' bugchecks pre-requisites not met - "
                      "skipping", HotSOSConfig.PLUGIN_NAME)
            return

        checks = []
        for bug in ybugchecks.leaf_sections:
            bugcheck = {'bug_id': str(bug.name),
                        'requires': bug.requires,
                        'raises': bug.raises}
            if bug.expr:
                pattern = bug.expr.value
                datasource = bug.input.path
                searchdef = SearchDef(pattern,
                                      tag=bugcheck['bug_id'],
                                      hint=bug.hint.value)
                bugcheck['searchdef'] = searchdef
                bugcheck['datasource'] = datasource

            log.debug("bug=%s path=%s", bugcheck['bug_id'],
                      bugcheck.get('datasource'))
            checks.append(bugcheck)

        return checks

    @property
    def _bug_checks(self):
        """
        @return: list of bug check defintions.
        """
        if self._checks is not None:
            return self._checks

        self._checks = self._load_bug_checks()
        return self._checks

    def load(self):
        """
        Load definitions and register search patterns if any.
        """
        if not self._bug_checks:
            return

        for check in self._bug_checks:
            if 'searchdef' in check:
                self.searchobj.add_search_term(check['searchdef'],
                                               check['datasource'])

    def run(self, results):
        if not self._bug_checks:
            return

        for bugsearch in self._bug_checks:
            bug_id = bugsearch['bug_id']
            requires = bugsearch['requires']
            if requires:
                if not requires.passes:
                    log.debug("bugcheck '%s' requirement not met - "
                              "skipping check", bug_id)
                    continue

            raises = bugsearch['raises']
            bug_matches = None
            if 'searchdef' in bugsearch:
                bug_matches = results.find_by_tag(bug_id)
                if not bug_matches:
                    continue

            log.debug("bug %s identified", bug_id)
            if bug_matches and raises.format_groups:
                # we only use the first result
                message = raises.message_with_format_list_applied(
                                                                bug_matches[0])
            else:
                message = raises.message_with_format_dict_applied(
                                                property=bugsearch['requires'])

            bug_type = raises.type
            if not raises.type:
                bug_type = LaunchpadBug
                log.info("no type provided for bug check so assuming %s",
                         bug_type)

            utils.add_issue(raises.type(bug_id, message))
