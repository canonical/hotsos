import os
import yaml

from core import constants
from core.issues.utils import IssueEntry

LAUNCHPAD = "launchpad"
MASTER_YAML_KNOWN_BUGS_KEY = "bugs-detected"
KNOWN_BUGS = {MASTER_YAML_KNOWN_BUGS_KEY: []}


def get_known_bugs():
    """
    Fetch the current plugin known_bugs.yaml if it exists and return its
    contents or None if it doesn't exist yet.
    """
    if not os.path.isdir(constants.PLUGIN_TMP_DIR):
        raise Exception("plugin tmp dir  '{}' not found".
                        format(constants.PLUGIN_TMP_DIR))

    known_bugs_yaml = os.path.join(constants.PLUGIN_TMP_DIR, "known_bugs.yaml")
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
    if not os.path.isdir(constants.PLUGIN_TMP_DIR):
        raise Exception("plugin tmp dir  '{}' not found".
                        format(constants.PLUGIN_TMP_DIR))

    if type == LAUNCHPAD:
        new_bug = "https://bugs.launchpad.net/bugs/{}".format(bug_id)

    if description is None:
        description = "no description provided"

    entry = IssueEntry(new_bug, description, key="id")
    current = get_known_bugs()
    if current and current.get(MASTER_YAML_KNOWN_BUGS_KEY):
        current[MASTER_YAML_KNOWN_BUGS_KEY].append(entry.data)
    else:
        current = {MASTER_YAML_KNOWN_BUGS_KEY: [entry.data]}

    known_bugs_yaml = os.path.join(constants.PLUGIN_TMP_DIR, "known_bugs.yaml")
    with open(known_bugs_yaml, 'w') as fd:
        fd.write(yaml.dump(current))
