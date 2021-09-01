import os
import re
import yaml

from core import plugintools
from core import constants

MASTER_YAML_ISSUES_FOUND_KEY = "potential-issues"


class IssueEntry(object):
    def __init__(self, ref, desc, origin=None, key=None):
        if key is None:
            key = "key"

        self.key = key
        self.ref = ref
        self.description = desc
        if origin is None:
            ret = re.compile("(.+).py$").match(constants.PART_NAME)
            if ret:
                part_name = ret.group(1)
            else:
                part_name = constants.PART_NAME

            self.origin = "{}.{}".format(constants.PLUGIN_NAME, part_name)
        else:
            self.origin = origin

    @property
    def data(self):
        return {self.key: self.ref,
                "desc": self.description,
                "origin": self.origin}


def _get_issues():
    """
    Fetch the current plugin issues.yaml if it exists and return its
    contents or None if it doesn't exist yet.
    """
    if not os.path.isdir(constants.PLUGIN_TMP_DIR):
        raise Exception("plugin tmp dir  '{}' not found".
                        format(constants.PLUGIN_TMP_DIR))

    issues_yaml = os.path.join(constants.PLUGIN_TMP_DIR, "issues.yaml")
    if not os.path.exists(issues_yaml):
        return {}

    issues = yaml.safe_load(open(issues_yaml))
    if issues and issues.get(MASTER_YAML_ISSUES_FOUND_KEY):
        return issues

    return issues


def add_issue(issue):
    """
    Fetch the current plugin issues.yaml if it exists and add new issue with
    description of the issue.
    """
    if not os.path.isdir(constants.PLUGIN_TMP_DIR):
        raise Exception("plugin tmp dir  '{}' not found".
                        format(constants.PLUGIN_TMP_DIR))

    entry = IssueEntry(issue.name, issue.msg, key="type")
    current = _get_issues()
    if current and current.get(MASTER_YAML_ISSUES_FOUND_KEY):
        current[MASTER_YAML_ISSUES_FOUND_KEY].append(entry.data)
    else:
        current = {MASTER_YAML_ISSUES_FOUND_KEY: [entry.data]}

    issues_yaml = os.path.join(constants.PLUGIN_TMP_DIR, "issues.yaml")
    with open(issues_yaml, 'w') as fd:
        fd.write(yaml.dump(current))


def add_issues_to_master_plugin():
    """
    Fetch the current plugin issues.yaml and add it to the master yaml.
    Note that this can only be called once per plugin and is typically
    performed as a final part after all others have executed.
    """
    issues = _get_issues()
    if issues and issues.get(MASTER_YAML_ISSUES_FOUND_KEY):
        plugintools.save_part(issues, priority=99)
