#!/usr/bin/python3
import re

from common import (
    helpers,
)


class ServiceChecksBase(object):

    def __init__(self, service_exprs, use_ps_axo_flags=False):
        """
        @param service_exprs: list of python.re expressions used to match a
        service name.
        @param use_ps_axo_flags: optional flag to change function used to get
        ps output.
        """
        self.services = {}
        self.service_exprs = []

        for expr in service_exprs:
            # arbitrarily use first 5 chars of search as a pre-search hint
            self.service_exprs.append((expr, expr[:4]))

        # only use if exists
        if use_ps_axo_flags and helpers.get_ps_axo_flags_available():
            self.ps_func = helpers.get_ps_axo_flags
        else:
            self.ps_func = helpers.get_ps

    @property
    def has_ps_axo_flags(self):
        """Returns True if it is has been requested and is possible to get
        output of helpers.get_ps_axo_flags.
        """
        return self.ps_func == helpers.get_ps_axo_flags

    def get_service_info_str(self):
        """Create a list of "<service> (<num running>)" for running services
        detected. Useful for display purposes."""
        service_info_str = []
        for svc in self.services:
            num_daemons = self.services[svc]["ps_cmds"]
            service_info_str.append("{} ({})".format(svc, len(num_daemons)))

        return service_info_str

    def _get_running_services(self):
        """
        Execute each provided service expression against lines in ps and store
        each full line in a list against the service matched.
        """
        for line in self.ps_func():
            for expr, hint in self.service_exprs:
                ret = re.compile(hint).search(line)
                if not ret:
                    continue

                # look for running process with this name
                ret = re.compile(r".+\s\S*({})(\s+.+|$)".format(expr)
                                 ).match(line)
                if ret:
                    svc = ret.group(1)
                    if svc not in self.services:
                        self.services[svc] = {"ps_cmds": []}

                    self.services[svc]["ps_cmds"].append(ret.group(0))

    def __call__(self):
        """This can/should be extended by inheriting class."""
        self._get_running_services()
