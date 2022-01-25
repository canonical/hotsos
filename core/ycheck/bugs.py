from core import constants
from core.log import log
from core.checks import DPKGVersionCompare
from core.known_bugs_utils import add_known_bug
from core.ycheck import (
    YDefsLoader,
    YDefsSection,
    AutoChecksBase,
)
from core.searchtools import FileSearcher, SearchDef


class YBugChecker(AutoChecksBase):
    """ Class used to identify bugs by matching criteria defined in yaml. """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, searchobj=FileSearcher(), **kwargs)
        self._checks = None

    def _load_bug_checks(self):
        """ Load bug check definitions from yaml. """
        plugin_bugs = YDefsLoader('bugs').load_plugin_defs()
        if not plugin_bugs:
            return

        ybugchecks = YDefsSection(constants.PLUGIN_NAME, plugin_bugs)
        log.debug("loaded plugin '%s' bugs - sections=%s, events=%s",
                  ybugchecks.name,
                  len(ybugchecks.branch_sections),
                  len(ybugchecks.leaf_sections))
        if ybugchecks.requires and not ybugchecks.requires.passes:
            log.debug("plugin '%s' bugchecks pre-requisites not met - "
                      "skipping", constants.PLUGIN_NAME)
            return

        checks = []
        for bug in ybugchecks.leaf_sections:
            bugcheck = {'bug_id': str(bug.name),
                        'context': bug.context,
                        'requires': bug.requires,
                        'settings': bug.settings,
                        'message': bug.raises.message,
                        'message_format_result_groups':
                            bug.raises.format_groups}
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

    def _package_has_bugfix(self, pkg_version, versions_affected):
        for item in sorted(versions_affected, key=lambda i: i['min-fixed'],
                           reverse=True):
            min_fixed = item['min-fixed']
            min_broken = item['min-broken']
            lt_fixed = pkg_version < DPKGVersionCompare(min_fixed)
            if min_broken:
                lt_broken = pkg_version < DPKGVersionCompare(min_broken)
            else:
                lt_broken = None

            if lt_broken:
                continue

            if lt_fixed:
                return False
            else:
                return True

        return True

    def _get_format_list(self, result_group_indexes, search_result):
        """
        Extract results from search result at given indexes and return as list.

        @param result_group_indexes: list of int indexes
        @param search_result: filesearcher search result
        """
        values = []
        for idx in result_group_indexes:
            values.append(search_result.get(idx))

        return values

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
            format_dict = {}
            format_list = []
            bug_id = bugsearch['bug_id']
            requires = bugsearch['requires']
            if requires and not requires.passes:
                log.debug("bugcheck '%s' requirement not met - skipping check",
                          bug_id)
                continue

            settings = bugsearch['settings']
            if settings and settings.versions_affected and settings.package:
                pkg = settings.package
                pkg_ver = bugsearch['context'].apt_all.get(pkg)
                if pkg_ver:
                    if self._package_has_bugfix(pkg_ver,
                                                settings.versions_affected):
                        # No need to search since the bug is fixed.
                        log.debug('bug %s already fixed in package %s version '
                                  '%s - skipping check', bug_id, pkg, pkg_ver)
                        continue

                    format_dict = {'package_name': pkg,
                                   'version_current': pkg_ver}
                else:
                    log.debug("package %s not installed - skipping check", pkg)
                    continue

            message = bugsearch['message']
            if 'searchdef' in bugsearch:
                bug_matches = results.find_by_tag(bug_id)
                if not bug_matches:
                    continue

                indexes = bugsearch['message_format_result_groups']
                if indexes:
                    # we only use the first result
                    first_match = bug_matches[0]
                    format_list = self._get_format_list(indexes,
                                                        first_match)

            log.debug("bug %s identified", bug_id)
            if format_list:
                add_known_bug(bug_id, message.format(*format_list))
            elif format_dict:
                log.debug(message.format(**format_dict))
                add_known_bug(bug_id, message.format(**format_dict))
            else:
                add_known_bug(bug_id, message)
