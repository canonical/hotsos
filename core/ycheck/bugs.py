from core import constants
from core.log import log
from core.checks import DPKGVersionCompare
from core.known_bugs_utils import (
    add_known_bug,
    BugSearchDef,
)
from core.ycheck import (
    YDefsLoader,
    YDefsSection,
    AutoChecksBase,
)
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
        plugin_bugs = YDefsLoader('bugs').load_plugin_defs()
        if not plugin_bugs:
            return

        ybugchecks = YDefsSection(constants.PLUGIN_NAME, plugin_bugs,
                                  checks_handler=self)
        log.debug("loaded plugin '%s' bugs - sections=%s, events=%s",
                  ybugchecks.name,
                  len(ybugchecks.branch_sections),
                  len(ybugchecks.leaf_sections))
        if ybugchecks.requires and not ybugchecks.requires.passes:
            log.debug("plugin not runnable - skipping bug checks")
            return

        bug_defs = []
        for bug in ybugchecks.leaf_sections:
            id = bug.name
            message = bug.raises.message
            message_format = bug.raises.format_groups
            pattern = bug.expr.value
            datasource = bug.input.path
            # NOTE: pattern can be string or list of strings
            bdef = {'def': BugSearchDef(
                               pattern,
                               bug_id=str(id),
                               hint=bug.hint.value,
                               message=message,
                               message_format_result_groups=message_format),
                    'context': bug.context,
                    'settings': bug.settings,
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
        if not self.bug_definitions:
            return

        for bugsearch in self.bug_definitions:
            self.searchobj.add_search_term(bugsearch["def"],
                                           bugsearch["datasource"])

    def package_has_bugfix(self, pkg_version, versions_affected):
        for item in sorted(versions_affected, key=lambda i: i['min-fixed'],
                           reverse=True):
            min_fixed = item.get('min-fixed')
            min_broken = item.get('min-broken')
            lt_fixed = pkg_version < DPKGVersionCompare(min_fixed)
            if min_broken:
                lt_broken = pkg_version < DPKGVersionCompare(min_broken)
            else:
                lt_broken = None

            if (min_broken and lt_broken):
                continue

            if lt_fixed:
                return False
            else:
                return True

        return True

    def run(self, results):
        if not self.bug_definitions:
            return

        for bugsearch in self.bug_definitions:
            bug_def = bugsearch['def']
            bug_id = bug_def.tag

            settings = bugsearch['settings']
            if settings and settings.versions_affected and settings.package:
                pkg = settings.package
                pkg_ver = bugsearch['context'].apt_all.get(pkg)
                if pkg_ver:
                    if self.package_has_bugfix(pkg_ver,
                                               settings.versions_affected):
                        # No need to search since the bug is fixed.
                        log.debug('bug %s already fixed in package %s version '
                                  '%s - skipping check', bug_id, pkg, pkg_ver)
                        continue

            _results = results.find_by_tag(bug_id)
            if _results:
                log.debug("bug %s identified", bug_id)
                if bug_def.message_format_result_groups:
                    # we only use the first result
                    message = bug_def.rendered_message(_results[0])
                    add_known_bug(bug_id, message)
                else:
                    add_known_bug(bug_id, bug_def.message)
