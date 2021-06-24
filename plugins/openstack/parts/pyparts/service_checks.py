#!/usr/bin/python3
import re

from common import (
    cli_helpers,
    issue_types,
    issues_utils,
)


class NeutronServiceChecks(object):

    def check_ovs_cleanup(self):
        """
        Allow one run on node boot/reboot but not after.
        """
        raise_issue = False
        start_count = 0
        for line in cli_helpers.get_journalctl(unit="neutron-ovs-cleanup"):
            expr = r"Started OpenStack Neutron OVS cleanup."
            if re.compile("-- Reboot --").match(line):
                # reset after reboot
                start_count = 0
            elif re.compile(expr).search(line):
                if start_count:
                    raise_issue = True
                    break

                start_count += 1

        if raise_issue:
            msg = ("neutron-ovs-cleanup has been manually run on this "
                   "host. This is not recommended and can have unintended "
                   "side-effects.")
            issues_utils.add_issue(issue_types.OpenstackWarning(msg))

    def __call__(self):
        self.check_ovs_cleanup()
