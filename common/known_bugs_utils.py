#!/usr/bin/python3
import os
import yaml

from common import plugin_yaml
from common.constants import PLUGIN_TMP_DIR
from common.searchtools import SearchDef
from common.issues_utils import IssueEntry

LAUNCHPAD = "launchpad"
MASTER_YAML_KNOWN_BUGS_KEY = "bugs-detected"
KNOWN_BUGS = {MASTER_YAML_KNOWN_BUGS_KEY: []}


class BugSearchDef(SearchDef):
    def __init__(self, expr, bug_id, hint, reason,
                 reason_format_result_groups=None):
        """
        @param reason: string reason describing the issue and why it has been
        flagged. This string can be a template i.e. containing {} fields that
        can be rendered using results.
        @param reason_format_result_groups: if the reason string is a template,
        this is a list of indexes in the results that can be extracted for
        inclusion in the reason.
        """
        super().__init__(expr, tag=bug_id, hint=hint)
        self._reason = reason
        if reason is None:
            self._reason = ""

        self.reason_format_result_groups = reason_format_result_groups

    @property
    def reason(self):
        return self._reason

    def rendered_reason(self, search_result):
        if self._reason and self.reason_format_result_groups:
            values = []
            for idx in self.reason_format_result_groups:
                values.append(search_result.get(idx))

            return self._reason.format(*values)

        return self._reason


def _get_known_bugs():
    """
    Fetch the current plugin known_bugs.yaml if it exists and return its
    contents or None if it doesn't exist yet.
    """
    if not os.path.isdir(PLUGIN_TMP_DIR):
        raise Exception("plugin tmp dir  '{}' not found".
                        format(PLUGIN_TMP_DIR))

    known_bugs_yaml = os.path.join(PLUGIN_TMP_DIR, "known_bugs.yaml")
    if not os.path.exists(known_bugs_yaml):
        return {}

    bugs = yaml.safe_load(open(known_bugs_yaml))
    if bugs and bugs.get(MASTER_YAML_KNOWN_BUGS_KEY):
        return bugs

    return {}


def add_known_bug(bug_id, description=None, type=LAUNCHPAD):
    """
    Fetch the current plugin known_bugs.yaml if it exists and add new bug with
    description of the bug.
    """
    if not os.path.isdir(PLUGIN_TMP_DIR):
        raise Exception("plugin tmp dir  '{}' not found".
                        format(PLUGIN_TMP_DIR))

    if type == LAUNCHPAD:
        new_bug = "https://bugs.launchpad.net/bugs/{}".format(bug_id)

    if description is None:
        description = "no description provided"

    entry = IssueEntry(new_bug, description, key="id")
    current = _get_known_bugs()
    if current and current.get(MASTER_YAML_KNOWN_BUGS_KEY):
        current[MASTER_YAML_KNOWN_BUGS_KEY].append(entry.data)
    else:
        current = {MASTER_YAML_KNOWN_BUGS_KEY: [entry.data]}

    known_bugs_yaml = os.path.join(PLUGIN_TMP_DIR, "known_bugs.yaml")
    with open(known_bugs_yaml, 'w') as fd:
        fd.write(yaml.dump(current))


def add_known_bugs_to_master_plugin():
    """
    Fetch the current plugin known_bugs.yaml and add it to the master yaml.
    Note that this can only be called once per plugin and is typically
    performed as a final part after all others have executed.
    """
    bugs = _get_known_bugs()
    if bugs and bugs.get(MASTER_YAML_KNOWN_BUGS_KEY):
        plugin_yaml.save_part(bugs, priority=99)
