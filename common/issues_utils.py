#!/usr/bin/python3
import os
import yaml

from common import plugin_yaml
from common.constants import (
    PLUGIN_TMP_DIR,
)

MASTER_YAML_ISSUES_FOUND_KEY = "potential-issues"


def _get_issues():
    """
    Fetch the current plugin issues.yaml if it exists and return its
    contents or None if it doesn't exist yet.
    """
    if not os.path.isdir(PLUGIN_TMP_DIR):
        raise Exception("plugin tmp dir  '{}' not found".
                        format(PLUGIN_TMP_DIR))

    issues_yaml = os.path.join(PLUGIN_TMP_DIR, "issues.yaml")
    if not os.path.exists(issues_yaml):
        return

    return yaml.safe_load(open(issues_yaml))


def add_issue(issue):
    """
    Fetch the current plugin issues.yaml if it exists and add new issue with
    description of the issue.
    """
    if not os.path.isdir(PLUGIN_TMP_DIR):
        raise Exception("plugin tmp dir  '{}' not found".
                        format(PLUGIN_TMP_DIR))

    entry = {issue.name: issue.msg}

    current = _get_issues()
    if current and current.get(MASTER_YAML_ISSUES_FOUND_KEY):
        current[MASTER_YAML_ISSUES_FOUND_KEY].append(entry)
    else:
        current = {MASTER_YAML_ISSUES_FOUND_KEY: [entry]}

    issues_yaml = os.path.join(PLUGIN_TMP_DIR, "issues.yaml")
    with open(issues_yaml, 'w') as fd:
        fd.write(yaml.dump(current))


def add_issues_to_master_plugin():
    """
    Fetch the current plugin issues.yaml and add it to the master yaml.
    Note that this can only be called once per plugin and is typically
    performed as a final part after all others have executed.
    """
    issues = _get_issues()
    if issues:
        plugin_yaml.dump(issues)
