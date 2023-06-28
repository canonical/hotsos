#!/usr/bin/env python3
"""
Create a structured summary of key information from hotsos summary outputs.
"""
import glob
import os
import json
import sys
import subprocess

from hotsos.core import plugintools


if __name__ == "__main__":
    if len(sys.argv) > 1:
        path = os.path.join(sys.argv[1], '*.json')
    else:
        path = '*.json'

    for f in glob.glob(path):
        with open(f) as fd:
            subprocess.call(['clear'])
            s = json.loads(fd.read())
            print("host: {} ".format(s['system']['hostname']))
            print("date: {}".format(s['system']['date']))
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

#            print("enabled: {}".format(', '.join(sorted(_enabled))))
            print("services:")
            for plugin, svcs in _services.items():
                print("  {}: {}".format(plugin, ', '.join(svcs)))

            if _has_bugs:
                print("bugs:")
                for btype, content in _has_bugs.items():
                    print("  {}: {}\n".format(btype, '\n'.join(content)))

            if _has_potential_issues:
                print("issues:")
                for btype, content in _has_potential_issues.items():
                    print("  {}:".format(btype))
                    for msg in content:
                        print("    {}".format(msg))

            input("\nNext? [ENTER]")

        print("")
