#!/usr/bin/python3
import re

from common import (
    helpers,
)


class ServiceChecksBase(object):
    """This class should be used by any plugin that wants to identify
    and check the status of running services."""

    def __init__(self, service_exprs, hint_range=None,
                 use_ps_axo_flags=False):
        """
        @param service_exprs: list of python.re expressions used to match a
        service name.
        @param use_ps_axo_flags: optional flag to change function used to get
        ps output.
        """
        self.services = {}
        self.service_exprs = []

        for expr in service_exprs:
            if hint_range:
                start, end = hint_range
            else:
                # arbitrarily use first 5 chars of search as a pre-search hint
                start = 0
                end = min(len(expr), 4)

            self.service_exprs.append((expr, expr[start:end]))

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
        for svc in sorted(self.services):
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

                """
                look for running process with this name.
                We need to account for different types of process binary e.g.

                /snap/<name>/1830/<svc>
                /usr/bin/<svc>

                and filter e.g.

                /var/lib/<svc> and /var/log/<svc>
                """
                ret = re.compile(r".+\S*(\s|(bin|[0-9]+)/)({})(\s+.+|$)".
                                 format(expr)).match(line)
                if ret:
                    svc = ret.group(3)
                    if svc not in self.services:
                        self.services[svc] = {"ps_cmds": []}

                    self.services[svc]["ps_cmds"].append(ret.group(0))

    def __call__(self):
        """This can/should be extended by inheriting class."""
        self._get_running_services()


class PackageChecksBase(object):
    """This class should be used by any plugin that wants to identify
    and check the status of some packages."""

    def __init__(self, packages):
        """
        @param package_exprs: list of python.re expressions used to match
        package names.
        """
        self.packages = packages
        self.pkg_match_expr_template = \
            r"^ii\s+(python3?-)?({}[0-9a-z\-]*)\s+(\S+)\s+.+"

    def _get_packages(self):
        info = []
        dpkg_l = helpers.get_dpkg_l()
        if not dpkg_l:
            return

        for line in dpkg_l:
            for pkg in self.packages:
                expr = self.pkg_match_expr_template.format(pkg)
                ret = re.compile(expr).match(line)
                if ret:
                    pyprefix = ret[1] or ""
                    result = "{}{} {}".format(pyprefix, ret[2], ret[3])
                    info.append(result)

        return info

    def __call__(self):
        """This can/should be extended by inheriting class."""
        return self._get_packages()
