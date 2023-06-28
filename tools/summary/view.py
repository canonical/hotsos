#!/usr/bin/env python3
"""
Create a structured summary of key information from hotsos summary outputs.
"""
import glob
import os
import json
import sys
import subprocess

import yaml
# load all plugins
import hotsos.plugin_extensions  # noqa: F401, pylint: disable=W0611
from hotsos.core import plugintools


def get_summary(root):
    if root is None:
        root = '.'

    paths = []
    if os.path.isdir(root):
        for encoding in ['json', 'yaml']:
            results = glob.glob(os.path.join(root, f'*.{encoding}'))
            if results:
                paths = results
                break
    else:
        paths = [root]

    for path in paths:
        with open(path, encoding='utf-8') as fd:
            if path.endswith('json'):
                yield json.loads(fd.read())
            else:
                yield yaml.safe_load(fd.read())


def get_info(s):
    _enabled = []
    _services = {}
    _has_bugs = {}
    _has_potential_issues = {}
    for plugin in plugintools.PLUGINS:
        if plugin in s:
            _enabled.append(plugin)
            if 'services' in s[plugin]:
                enabled = s[plugin]['services']
                enabled = enabled.get('systemd', {})
                _services[plugin] = enabled.get('enabled')

            if 'known-bugs' in s[plugin]:
                _has_bugs.update(s[plugin]['known-bugs'])

            if 'potential-issues' in s[plugin]:
                _has_potential_issues.update(
                    s[plugin]['potential-issues'])

    return _enabled, _services, _has_bugs, _has_potential_issues


def main():
    if len(sys.argv) > 1:
        path = sys.argv[1]
    else:
        path = None

    for s in get_summary(path):
        subprocess.call(['clear'])
        print(f"host: {s['system']['hostname']}")
        print(f"date: {s['system']['date']}")
        _enabled, _services, _has_bugs, _has_potential_issues = get_info(s)
    #            print("enabled: {}".format(', '.join(sorted(_enabled))))
        print("services:")
        for plugin, svcs in _services.items():
            _svcs = ', '.join(svcs)
            print(f"  {plugin}: {_svcs}")

        if _has_bugs:
            print("bugs:")
            for btype, content in _has_bugs.items():
                _content = '\n'.join(content)
                print(f"  {btype}: {_content}\n")

        if _has_potential_issues:
            print("issues:")
            for btype, content in _has_potential_issues.items():
                print(f"  {btype}:")
                for msg in content:
                    print(f"    {msg}")

            input("\nNext? [ENTER]")

            print("")


if __name__ == "__main__":
    main()
