#!/usr/bin/python3
"""
This is typically added as the last part of any plugin to be executed. It
serves to collect any bug information created during the course of the plugin
execution (i.e. each preceding part) and output as yaml for inclusion in the
master yaml section for this plugin.
"""
from core.known_bugs_utils import (
    add_known_bugs_to_master_plugin,
)
from core.issues_utils import (
    add_issues_to_master_plugin,
)
from core import plugintools


class KnownBugsAndIssuesCollector(object):
    def __call__(self):
        add_known_bugs_to_master_plugin()
        add_issues_to_master_plugin()
        plugintools.dump_all_parts()
