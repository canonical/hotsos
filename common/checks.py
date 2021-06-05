#!/usr/bin/python3
import os
import re
import yaml

from common import (
    cli_helpers,
    constants,
)
from common.utils import sorted_dict
from common.known_bugs_utils import (
    add_known_bug,
    BugSearchDef,
)
from common.searchtools import (
    SearchDef,
)

SVC_EXPR_TEMPLATES = {
    "absolute": r".+\S+bin/({})(?:\s+.+|$)",
    "snap": r".+\S+\d+/({})(?:\s+.+|$)",
    "relative": r".+\s({})(?:\s+.+|$)",
    }


class ChecksBase(object):

    def __init__(self, searchobj, root):
        """
        @param searchobj: FileSearcher object used for searches.
        @param root: yaml root key
        """
        self.searchobj = searchobj
        self._yaml_root = root

    def register_search_terms(self):
        raise NotImplementedError

    def process_results(self, results):
        raise NotImplementedError


class BugChecksBase(ChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bug_defs = []

    def _load_bug_definitions(self):
        """
        Load bug search definitions from yaml.

        @return: list of BugSearchDef objects
        """
        path = os.path.join(constants.PLUGIN_YAML_DEFS, "bugs.yaml")
        with open(path) as fd:
            yaml_defs = yaml.safe_load(fd.read())

        bugs = yaml_defs.get(self._yaml_root, {})
        for id in bugs:
            bug = bugs[id]
            reason_format = bug.get("reason-format-result-groups")
            _def = BugSearchDef(bug["expr"],
                                bug_id=str(id),
                                hint=bug["hint"],
                                reason=bug["reason"],
                                reason_format_result_groups=reason_format)
            bdef = {"def": _def}

            ds = os.path.join(constants.DATA_ROOT, bug["datasource"])
            if bug.get("allow-all-logs", True) and constants.USE_ALL_LOGS:
                ds = "{}*".format(ds)

            bdef["datasource"] = ds
            self._bug_defs.append(bdef)

    @property
    def bug_definitions(self):
        """
        @return: dict of SearchDef objects and datasource for all entries in
        bugs.yaml under _yaml_root.
        """
        if self._bug_defs:
            return self._bug_defs

        self._load_bug_definitions()
        return self._bug_defs

    def register_search_terms(self):
        for bugsearch in self.bug_definitions:
            self.searchobj.add_search_term(bugsearch["def"],
                                           bugsearch["datasource"])

    def process_results(self, results):
        for bugsearch in self.bug_definitions:
            tag = bugsearch["def"].tag
            _results = results.find_by_tag(tag)
            if _results:
                if bugsearch["def"].reason_format_result_groups:
                    reason = bugsearch["def"].rendered_reason(_results[0])
                    add_known_bug(tag, reason)
                else:
                    add_known_bug(tag, bugsearch["def"].reason)


class EventChecksBase(ChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._event_defs = {}

    def _load_event_definitions(self):
        """
        Load event search definitions from yaml.

        An event has two expressions; one to identify the start and one to
        identify the end. Note that these events can be overlapping hence why
        we don't use a SequenceSearchDef.
        """
        path = os.path.join(constants.PLUGIN_YAML_DEFS, "events.yaml")
        with open(path) as fd:
            yaml_defs = yaml.safe_load(fd.read())

        for group_name, group in yaml_defs.get(self._yaml_root, {}).items():
            for label in group:
                event = group[label]
                start = SearchDef(event["start"]["expr"],
                                  tag="{}-start".format(label),
                                  hint=event["start"]["hint"])
                end = SearchDef(event["end"]["expr"],
                                tag="{}-end".format(label),
                                hint=event["end"]["hint"])

                ds = os.path.join(constants.DATA_ROOT, event["datasource"])
                if (event.get("allow-all-logs", True) and
                        constants.USE_ALL_LOGS):
                    ds = "{}*".format(ds)

                if group_name not in self._event_defs:
                    self._event_defs[group_name] = {}

                if label not in self._event_defs[group_name]:
                    self._event_defs[group_name][label] = {}

                self._event_defs[group_name][label] = \
                    {"searchdefs": [start, end], "datasource": ds}

    @property
    def event_definitions(self):
        """
        @return: dict of SearchDef objects and datasource for all entries in
        events.yaml under _yaml_root.
        """
        if self._event_defs:
            return self._event_defs

        self._load_event_definitions()
        return self._event_defs

    def register_search_terms(self):
        """
        Register the search definitions for all events.

        @param root_key: events.yaml root key
        """
        for defs in self.event_definitions.values():
            for label in defs:
                event = defs[label]
                for sd in event["searchdefs"]:
                    self.searchobj.add_search_term(sd, event["datasource"])


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

    def get_version(self, pkg):
        """
        Return version of package.
        """
        raise NotImplementedError

    @staticmethod
    def dict_to_formatted_str_list(f):
        """
        Convert dict returned by function f to a list of strings of format
        '<name> <version>'.
        """
        def _dict_to_formatted_str_list(*args, **kwargs):
            ret = f(*args, **kwargs)
            return ["{} {}".format(*e) for e in ret.items()]

        return _dict_to_formatted_str_list

    @property
    def all(self):
        """ Returns results matched for all expressions. """
        raise NotImplementedError

    @property
    def core(self):
        """ Returns results matched for core expressions. """
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
        self._core_packages = {}
        self._other_packages = {}
        self._all_packages = {}
        # The following expression muct match any package name.
        self._match_expr_template = \
            r"^ii\s+(python3?-)?({}[0-9a-z\-]*)\s+(\S+)\s+.+"

    def get_version(self, pkg):
        """ Return version of package. """
        if pkg in self._all:
            return self._all[pkg]

        dpkg_l = cli_helpers.get_dpkg_l()
        if dpkg_l:
            for line in dpkg_l:
                name, version = self._match_package(pkg, line)
                if name:
                    return version

    def _match_package(self, pkg, entry):
        """ Returns tuple of (package name, version) """
        expr = self._match_expr_template.format(pkg)
        ret = re.compile(expr).match(entry)
        if ret:
            pyprefix = ret[1] or ""
            return "{}{}".format(pyprefix, ret[2]), ret[3]

        return None, None

    @property
    def _all(self):
        """ Returns dict of all packages matched. """
        if self._all_packages:
            return self._all_packages

        dpkg_l = cli_helpers.get_dpkg_l()
        if not dpkg_l:
            return

        all_exprs = self.core_pkg_exprs + self.other_pkg_exprs
        for line in dpkg_l:
            for pkg in all_exprs:
                name, version = self._match_package(pkg, line)
                if name is None:
                    continue

                if pkg in self.core_pkg_exprs:
                    self._core_packages[name] = version
                else:
                    self._other_packages[name] = version

        # ensure sorted
        self._core_packages = sorted_dict(self._core_packages)
        self._other_packages = sorted_dict(self._other_packages)
        combined = {}
        combined.update(self._core_packages)
        combined.update(self._other_packages)
        self._all_packages = sorted_dict(combined)

        return self._all_packages

    @property
    @PackageChecksBase.dict_to_formatted_str_list
    def all(self):
        """
        Returns list of all packages matched. Each entry in the list is an item
        looking like "<pkgname> <pkgver>".
        """
        return self._all

    @property
    @PackageChecksBase.dict_to_formatted_str_list
    def core(self):
        """
        Only return results that matched from the "core" set of packages.
        """
        if self._core_packages:
            return self._core_packages

        if self._other_packages:
            return {}

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
        self._core_snaps = {}
        self._other_snaps = {}
        self._all_snaps = {}
        self._match_expr_template = \
            r"^ii\s+(python3?-)?({}[0-9a-z\-]*)\s+(\S+)\s+.+"

    def get_version(self, snap):
        """ Return version of package. """
        if snap in self._all:
            return self._all[snap]

        snap_list_all = cli_helpers.get_snap_list_all()
        if snap_list_all:
            for line in snap_list_all:
                name, version = self._get_snap_info_from_line(line, snap)
                if name:
                    return version

    def _get_snap_info_from_line(self, line, snap):
        """Returns snap name and version if found in line.

        @return: tuple of (name, version) or None, None
        """
        ret = re.compile(r"^({})\s+([\S]+)\s+.+".format(snap)).match(line)
        if ret:
            return (ret[1], ret[2])

        return None, None

    @property
    def _all(self):
        if self._all_snaps:
            return self._all_snaps

        snap_list_all = cli_helpers.get_snap_list_all()
        if not snap_list_all:
            return {}

        _core = {}
        _other = {}
        all_exprs = self.core_snap_exprs + self.other_snap_exprs
        for line in snap_list_all:
            for snap in all_exprs:
                name, version = self._get_snap_info_from_line(line, snap)
                if not name:
                    continue

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
        self._core_snaps = sorted_dict(_core)
        self._other_snaps = sorted_dict(_other)
        combined = {}
        combined.update(_core)
        combined.update(_other)
        self._all_snaps = sorted_dict(combined)

        return self._all_snaps

    @property
    @PackageChecksBase.dict_to_formatted_str_list
    def all(self):
        """
        Return results that matched from the all/any set of snaps.
        """
        return self._all

    @property
    @PackageChecksBase.dict_to_formatted_str_list
    def core(self):
        """
        Only return results that matched from the "core" set of snaps.
        """
        if self._core_snaps:
            return self._core_snaps

        if self._other_snaps:
            return {}

        # go fetch
        self.all
        return self._core_snaps
