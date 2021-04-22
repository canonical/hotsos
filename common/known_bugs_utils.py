#!/usr/bin/python3
import os
import yaml

from launchpadlib.launchpad import Launchpad
from common import plugin_yaml
from common.constants import (
    PLUGIN_TMP_DIR,
)

LAUNCHPAD = "launchpad"
MASTER_YAML_KNOWN_BUGS_KEY = "known-bugs"
KNOWN_BUGS = {MASTER_YAML_KNOWN_BUGS_KEY: []}

# TODO: Add caching
launchpad = Launchpad.login_anonymously('hotsos', 'production')


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
        return

    return yaml.safe_load(open(known_bugs_yaml))


def add_known_bug(bug_id, description=None, type=LAUNCHPAD):
    """
    Fetch the current plugin known_bugs.yaml if it exists and add new bug with
    description of the bug.
    """
    if not os.path.isdir(PLUGIN_TMP_DIR):
        raise Exception("plugin tmp dir  '{}' not found".
                        format(PLUGIN_TMP_DIR))

    if type == LAUNCHPAD:
        try:
            lp_bug = launchpad.bugs[bug_id]
            description = lp_bug.title
            new_bug = lp_bug.web_link
        except (KeyError, AttributeError):
            new_bug = "https://bugs.launchpad.net/bugs/{}".format(bug_id)

    if description is None:
        description = "no description provided"

    entry = {new_bug: description}
    current = _get_known_bugs()
    if current and current.get(MASTER_YAML_KNOWN_BUGS_KEY):
        if entry not in current.get(MASTER_YAML_KNOWN_BUGS_KEY):
            current[MASTER_YAML_KNOWN_BUGS_KEY].append(entry)
    else:
        current = {MASTER_YAML_KNOWN_BUGS_KEY: [entry]}

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
    if bugs:
        plugin_yaml.dump(bugs)
