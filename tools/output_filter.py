#!/usr/bin/python3
import yaml

from core import (
    constants,
    known_bugs_utils,
    plugintools,
)
from core.issues import issue_utils

FILTER_SCHEMA = [issue_utils.MASTER_YAML_ISSUES_FOUND_KEY,
                 known_bugs_utils.MASTER_YAML_KNOWN_BUGS_KEY]


def filter_master_yaml():
    with open(constants.MASTER_YAML_OUT) as fd:
        master_yaml = yaml.safe_load(fd)

    # Create a master list of issues and bugs adding info about which plugin
    # added them.

    filtered = {}
    for plugin in master_yaml:
        for key in FILTER_SCHEMA:
            if key in master_yaml[plugin]:
                if key not in filtered:
                    filtered[key] = {}

                if plugin not in filtered[key]:
                    filtered[key][plugin] = []

                items = master_yaml[plugin][key]
                for item in items:
                    filtered[key][plugin].append(item)

    with open(constants.MASTER_YAML_OUT, 'w') as fd:
        if filtered:
            fd.write(plugintools.dump(filtered, stdout=False))
            fd.write("\n")
        else:
            fd.write("")


if __name__ == "__main__":
    filter_master_yaml()
