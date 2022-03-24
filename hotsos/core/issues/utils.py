import os
import re
import yaml

from hotsos.core.config import HotSOSConfig

MASTER_YAML_ISSUES_FOUND_KEY = 'potential-issues'


class IssueEntry(object):
    def __init__(self, ref, desc, origin=None, key=None):
        if key is None:
            key = 'key'

        self.key = key
        self.ref = ref
        self.description = desc
        if origin is None:
            ret = re.compile("(.+).py$").match(HotSOSConfig.PART_NAME)
            if ret:
                part_name = ret.group(1)
            else:
                part_name = HotSOSConfig.PART_NAME

            self.origin = "{}.{}".format(HotSOSConfig.PLUGIN_NAME, part_name)
        else:
            self.origin = origin

    @property
    def data(self):
        return {self.key: self.ref,
                'desc': self.description,
                'origin': self.origin}


def get_plugin_issues():
    """
    Fetch the current plugin issues.yaml if it exists and return its
    contents or None if it doesn't exist yet.
    """
    if not os.path.isdir(HotSOSConfig.PLUGIN_TMP_DIR):
        raise Exception("plugin tmp dir  '{}' not found".
                        format(HotSOSConfig.PLUGIN_TMP_DIR))

    issues_yaml = os.path.join(HotSOSConfig.PLUGIN_TMP_DIR, 'issues.yaml')
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
    if not os.path.isdir(HotSOSConfig.PLUGIN_TMP_DIR):
        raise Exception("plugin tmp dir  '{}' not found".
                        format(HotSOSConfig.PLUGIN_TMP_DIR))

    entry = IssueEntry(issue.name, issue.msg, key='type')
    current = get_plugin_issues()
    if current and current.get(MASTER_YAML_ISSUES_FOUND_KEY):
        current[MASTER_YAML_ISSUES_FOUND_KEY].append(entry.data)
    else:
        current = {MASTER_YAML_ISSUES_FOUND_KEY: [entry.data]}

    issues_yaml = os.path.join(HotSOSConfig.PLUGIN_TMP_DIR, 'issues.yaml')
    with open(issues_yaml, 'w') as fd:
        fd.write(yaml.dump(current))
