#!/usr/bin/python3
import re

from common import (
    cli_helpers,
)

SVC_EXPR_TEMPLATES = {
    "absolute": r".+\S+bin/({})(?:\s+.+|$)",
    "snap": r".+\S+\d+/({})(?:\s+.+|$)",
    "relative": r".+\s({})(?:\s+.+|$)",
    }


class ServiceChecksBase(object):
    """This class should be used by any plugin that wants to identify
    and check the status of running services."""

    def __init__(self, service_exprs, hint_range=None):
        """
        @param service_exprs: list of python.re expressions used to match a
        service name.
        @param hint_range: optional range reflecting a range that can be
                           extracted from any of the provided expressions and
                           used as a pre-search before doing a full search in
                           order to reduce unnecessary full searches.
        """
        self.services = {}
        self.service_exprs = []

        for expr in service_exprs:
            hint = None
            if hint_range:
                start, end = hint_range
                hint = expr[start:end]

            self.service_exprs.append((expr, hint))

        self.ps_func = cli_helpers.get_ps

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
                if hint:
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
                for expr_tmplt in SVC_EXPR_TEMPLATES.values():
                    ret = re.compile(expr_tmplt.format(expr)).match(line)
                    if ret:
                        svc = ret.group(1)
                        if svc not in self.services:
                            self.services[svc] = {"ps_cmds": []}

                        self.services[svc]["ps_cmds"].append(ret.group(0))
                        break

    def __call__(self):
        """This can/should be extended by inheriting class."""
        self._get_running_services()


class PackageChecksBase(object):

    @property
    def all(self):
        """
        Returns list results matched for all expressions. List items have the
        format "<name> <version>".
        """
        raise NotImplementedError

    @property
    def core(self):
        """
        Returns list results matched for core expressions. List items have the
        format "<name> <version>".
        """
        raise NotImplementedError


class APTPackageChecksBase(PackageChecksBase):

    def __init__(self, core_pkgs, other_pkgs=None):
        """
        @param core_pkgs: list of python.re expressions used to match
        package names.
        @param other_pkg_exprs: optional list of python.re expressions used to
        match packages that are not considered part of the core set. This can
        be used to distinguish between core and non-core packages.
        """
        self.core_pkg_exprs = core_pkgs
        self.other_pkg_exprs = other_pkgs or []
        self._core_packages = []
        self._other_packages = []
        self._all_packages = []
        self._match_expr_template = \
            r"^ii\s+(python3?-)?({}[0-9a-z\-]*)\s+(\S+)\s+.+"

    def _match_package(self, pkg, entry):
        expr = self._match_expr_template.format(pkg)
        ret = re.compile(expr).match(entry)
        if ret:
            pyprefix = ret[1] or ""
            return "{}{} {}".format(pyprefix, ret[2], ret[3])

    @property
    def all(self):
        """
        Returns list of all packages matched. Each entry in the list is an item
        looking like "<pkgname> <pkgver>".
        """
        if self._all_packages:
            return self._all_packages

        dpkg_l = cli_helpers.get_dpkg_l()
        if not dpkg_l:
            return

        all_exprs = self.core_pkg_exprs + self.other_pkg_exprs
        for line in dpkg_l:
            for pkg in all_exprs:
                result = self._match_package(pkg, line)
                if result:
                    if pkg in self.core_pkg_exprs:
                        self._core_packages.append(result)
                    else:
                        self._other_packages.append(result)

        # ensure sorted
        self._core_packages = sorted(self._core_packages)
        self._other_packages = sorted(self._other_packages)
        self._all_packages = sorted(self._core_packages + self._other_packages)

        return self._all_packages

    @property
    def core(self):
        """
        Only return results that matched from the "core" set of packages.
        """
        if self._core_packages:
            return self._core_packages

        if self._other_packages:
            return []

        # go fetch
        self.all
        return self._core_packages


class SnapPackageChecksBase(PackageChecksBase):

    def __init__(self, core_snaps, other_snaps=None):
        """
        @param core_snaps: list of python.re expressions used to match
        snap names.
        @param other_snap_exprs: optional list of python.re expressions used to
        match snap names for snaps that are not considered part of the
        core set.
        """
        self.core_snap_exprs = core_snaps
        self.other_snap_exprs = other_snaps or []
        self._core_snaps = []
        self._other_snaps = []
        self._all_snaps = []
        self._match_expr_template = \
            r"^ii\s+(python3?-)?({}[0-9a-z\-]*)\s+(\S+)\s+.+"

    @classmethod
    def _get_snap_info_from_line(cls, line, snap):
        """Returns snap name and version if found in line.

        @return: tuple of (name, version) or None
        """
        ret = re.compile(r"^({})\s+([\S]+)\s+.+".format(snap)).match(line)
        if ret:
            return (ret[1], ret[2])

        return None

    @property
    def all(self):
        if self._all_snaps:
            return self._all_snaps

        snap_list_all = cli_helpers.get_snap_list_all()
        if not snap_list_all:
            return []

        _core = {}
        _other = {}
        all_exprs = self.core_snap_exprs + self.other_snap_exprs
        for line in snap_list_all:
            for snap in all_exprs:
                info = self._get_snap_info_from_line(line, snap)
                if not info:
                    continue

                name, version = info
                # only show latest version installed
                if snap in self.core_snap_exprs:
                    if name in _core:
                        if version > _core[name]:
                            _core[name] = version
                    else:
                        _core[name] = version
                else:
                    if name in _other:
                        if version > _other[name]:
                            _other[name] = version
                    else:
                        _other[name] = version

        # ensure sorted
        self._core_snaps = sorted(["{} {}".format(name, _core[name])
                                   for name in _core])
        self._other_snaps = sorted(["{} {}".format(name, _other[name])
                                    for name in _other])
        self._all_snaps = sorted(self._core_snaps + self._other_snaps)

        return self._all_snaps

    @property
    def core(self):
        """
        Only return results that matched from the "core" set of snaps.
        """
        if self._core_snaps:
            return self._core_snaps

        if self._other_snaps:
            return []

        # go fetch
        self.all
        return self._core_snaps
