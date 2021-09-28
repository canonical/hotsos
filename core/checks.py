import os

import operator
import re
import subprocess
import yaml

from core import constants
from core.issues import (
    issue_types,
    issue_utils,
)
from core.cli_helpers import CLIHelper
from core.log import log
from core.utils import sorted_dict
from core.known_bugs_utils import (
    add_known_bug,
    BugSearchDef,
)
from core.searchtools import (
    FileSearcher,
    SearchDef,
)

SVC_EXPR_TEMPLATES = {
    "absolute": r".+\S+bin/({})(?:\s+.+|$)",
    "snap": r".+\S+\d+/({})(?:\s+.+|$)",
    "relative": r".+\s({})(?:\s+.+|$)",
    }


class CallbackHelper(object):

    def __init__(self):
        self.callbacks = {}

    def callback(self, f):
        def callback_inner(*args, **kwargs):
            return f(*args, **kwargs)

        self.callbacks[f.__name__] = callback_inner
        # we don't need to return but we leave it so that we can unit test
        # these methods.
        return callback_inner


class ChecksBase(object):

    def __init__(self, *args, yaml_defs_group=None, searchobj=None, **kwargs):
        """
        @param _yaml_defs_group: optional key used to identify our yaml
                                 definitions if indeed we have any. This is
                                 given meaning by the implementing class.
        @param searchobj: optional FileSearcher object used for searches. If
                          multiple implementations of this class are used in
                          the same part it is recommended to provide a search
                          object that is shared across them to provide
                          concurrent execution.

        """
        super().__init__(*args, **kwargs)
        if searchobj:
            self.searchobj = searchobj
        else:
            self.searchobj = FileSearcher()

        self._yaml_defs_group = yaml_defs_group

    def register_search_terms(self):
        raise NotImplementedError

    def process_results(self, results):
        raise NotImplementedError

    def run_checks(self):
        self.register_search_terms()
        return self.process_results(self.searchobj.search())


class PackageReleaseCheckObj(object):
    def __init__(self, package_name):
        self.package_name = package_name
        self.bugs = {}

    def add_bug_check(self, id, release, minbroken, minfixed):
        bug = {'id': id, 'minbroken': minbroken, 'minfixed': minfixed}
        if release in self.bugs:
            self.bugs[release].append(bug)
        else:
            self.bugs[release] = [bug]


class PackageBugChecksBase(object):
    """
    This is used to check if the version of installed packages contain
    known bugs and report them if found.
    """
    def __init__(self, release_name, pkg_info):
        """
        @param release_name: release name we are checking against - this must
                             exist in the yaml defs.
        @param pkg_info: dict of installed packages in the for
                         {<name>: <version>}. This is typically obtained from
                         an implementation of APTPackageChecksBase.
        """
        self._release_name = release_name
        self._pkg_info = pkg_info
        self._checks = []

    def _load_definitions(self):
        """
        Load bug search definitions from yaml.

        @return: list of BugSearchDef objects
        """
        path = os.path.join(constants.PLUGIN_YAML_DEFS,
                            'package_bug_checks.yaml')
        with open(path) as fd:
            yaml_defs = yaml.safe_load(fd.read())

        if not yaml_defs:
            return

        plugin_checks = yaml_defs.get(constants.PLUGIN_NAME, {})
        for pkg, bugs in plugin_checks.items():
            p = PackageReleaseCheckObj(pkg)
            for bug, releases in bugs.items():
                for release in releases.values():
                    for name, info in release.items():
                        p.add_bug_check(bug, name, info['min-broken'],
                                        info['min-fixed'])

            self._checks.append(p)

    def __call__(self):
        self._load_definitions()
        for check in self._checks:
            pkg = check.package_name
            # if installed do check
            if pkg in self._pkg_info:
                pkgver = self._pkg_info[pkg]
                for release, bugs in check.bugs.items():
                    if release == self._release_name:
                        for bug in bugs:
                            minbroken = bug['minbroken']
                            minfixed = bug['minfixed']
                            if (not pkgver < DPKGVersionCompare(minbroken) and
                                    pkgver < DPKGVersionCompare(minfixed)):
                                desc = ("installed package '{}' with version "
                                        "{} has a known critical bug and "
                                        "should be upgraded to a version >= "
                                        "{}.".format(pkg, pkgver,
                                                     bug['minfixed']))
                                add_known_bug(bug['id'], desc)


class BugChecksBase(ChecksBase):
    """
    Class used to identify bugs by searching for entries in files (typically
    log files). What we search for and how we respond is defined in
    defs/bugs.yaml so that we can grow our searches without touching code.

    Searches are defined per plugin and run automatically i.e. there is no need
    to implement this class.
    """
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

        if not yaml_defs:
            return

        plugin_bugs = yaml_defs.get(constants.PLUGIN_NAME, {})
        log.debug("running bug searches for plugin '%s' (groups=%d)",
                  constants.PLUGIN_NAME, len(plugin_bugs))
        for group, bugs in plugin_bugs.items():
            log.debug("running bug group '%s", group)
            for id in bugs:
                bug = bugs[id]
                reason_format = bug.get("reason-format-result-groups")
                _def = BugSearchDef(bug["expr"],
                                    bug_id=str(id),
                                    hint=bug.get("hint"),
                                    reason=bug["reason"],
                                    reason_format_result_groups=reason_format)
                bdef = {"def": _def}

                ds = os.path.join(constants.DATA_ROOT, bug["path"])
                if bug.get("allow-all-logs", True) and constants.USE_ALL_LOGS:
                    ds = "{}*".format(ds)

                bdef["datasource"] = ds
                self._bug_defs.append(bdef)

    @property
    def bug_definitions(self):
        """
        @return: dict of SearchDef objects and datasource for all entries in
        bugs.yaml under _yaml_defs_group.
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

    def __call__(self):
        """ Must be callable since its run automatically. """
        self.run_checks()


class EventCheckResult(object):

    def __init__(self, search_results, defs_section):
        """
        @param search_results:
        @param defs_section:
        """
        self.results = search_results
        self.section = defs_section


class EventChecksBase(ChecksBase):

    def __init__(self, *args, callback_helper=None,
                 event_results_output_key=None,
                 event_results_passthrough=False, **kwargs):
        """
        @param callback_helper: optionally provide a callback helper. This is
        used to "register" callbacks against events defined in the yaml so
        that they are automatically called when corresponding events are
        detected.
        @param event_results_output_key: by default the plugin output will be
                                         set to the return of process_results()
                                         but that can be optionally set
                                         with this key as root e.g. to avoid
                                         clobbering other results.
        @param event_results_passthrough: if set to True, the master results
                                          list is passed to callbacks so that
                                          they may fetch results in their own
                                          way.
        """
        super().__init__(*args, **kwargs)
        self.callback_helper = callback_helper
        self.event_results_output_key = event_results_output_key
        self.event_results_passthrough = event_results_passthrough
        self._event_defs = {}

    def _load_event_definitions(self):
        """
        Load event search definitions from yaml.

        An event is identified using between one and two expressions. If it
        requires a start and end to be considered complete then these can be
        specified for match otherwise we can match on a single line.
        Note that multi-line events can be overlapping hence why we don't use a
        SequenceSearchDef (we use core.analytics.LogEventStats).
        """
        path = os.path.join(constants.PLUGIN_YAML_DEFS, "events.yaml")
        with open(path) as fd:
            yaml_defs = yaml.safe_load(fd.read())

        if not yaml_defs:
            return

        # The following are keys that can be overriden at any level below
        # plugin.
        global_override_keys = ['path', 'allow-all-logs']

        log.debug("loading event definitions for plugin=%s group=%s",
                  constants.PLUGIN_NAME, self._yaml_defs_group)
        plugin = yaml_defs.get(constants.PLUGIN_NAME, {})
        groups = plugin.get(self._yaml_defs_group, {})

        section_names = []
        event_names = []
        for name, section in groups.items():
            if name in global_override_keys:
                continue

            section_names.append(name)
            for name in section:
                if name in global_override_keys:
                    continue

                event_names.append(name)

        log.debug("sections=%s, events=%s",
                  len(section_names), len(event_names))
        group_globals = {k: None for k in global_override_keys}
        for section_name, section in groups.items():
            if section_name in global_override_keys:
                group_globals[section_name] = section
                continue

            section_globals = {}
            section_globals.update(group_globals)
            for key in global_override_keys:
                if key in section:
                    section_globals[key] = section[key]
                    del section[key]

            for event_name in section:
                event = section[event_name]

                # if this is a multiline event (has a start and end), append
                # this to the tag so that it can be used with
                # core.analytics.LogEventStats.
                if 'end' in event:
                    tag = "{}-start".format(event_name)
                    expr = event['start']['expr']
                    hint = event['start'].get('hint')
                else:
                    tag = event_name
                    expr = event['expr']
                    hint = event.get('hint')

                start = SearchDef(expr, tag=tag, hint=hint)
                if 'end' in event:
                    tag = "{}-end".format(event_name)
                    hint = event['end'].get('hint')
                    end = SearchDef(event['end']['expr'], tag=tag, hint=hint)
                else:
                    end = None

                # allow low-level path to override section global path
                datasource = event.get('path', section_globals['path'])
                ds = os.path.join(constants.DATA_ROOT, datasource)
                if constants.USE_ALL_LOGS:
                    if section_globals['allow-all-logs'] is not None:
                        allow_all_logs = section_globals['allow-all-logs']
                    else:
                        allow_all_logs = event.get('allow-all-logs', True)

                    if allow_all_logs:
                        ds = "{}*".format(ds)

                if section_name not in self._event_defs:
                    self._event_defs[section_name] = {}

                if event_name not in self._event_defs[section_name]:
                    self._event_defs[section_name][event_name] = {}

                e_def = {'searchdefs': [start], 'datasource': ds}
                if end:
                    e_def['searchdefs'].append(end)

                self._event_defs[section_name][event_name] = e_def

    @property
    def event_definitions(self):
        """
        @return: dict of SearchDef objects and datasource for all entries in
        events.yaml under _yaml_defs_group.
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

    def process_results(self, results):
        """
        Provide a default way for results to be processed. This requires a
        CallbackHelper to have been provided and callbacks registered. If that
        is not the case the method must be re-implemented with another means
        of processing results.

        See defs/events.yaml for definitions.
        """
        if self.callback_helper is None or not self.callback_helper.callbacks:
            # If there are no callbacks registered this method must be
            # (re)implemented.
            raise NotImplementedError

        info = {}
        for section_name, section in self.event_definitions.items():
            for event in section:
                if self.event_results_passthrough:
                    # this is for implementations that have their own means of
                    # retreiving results.
                    search_results = results
                else:
                    search_results = results.find_by_tag(event)

                if not search_results:
                    continue

                # We want this to throw an exception if the callback is not
                # defined.
                callback_name = event.replace('-', '_')
                callback = self.callback_helper.callbacks[callback_name]
                log.debug("executing event callback '%s'", callback_name)
                event_results_obj = EventCheckResult(search_results,
                                                     section_name)
                ret = callback(self, event_results_obj)
                if not ret:
                    continue

                # if the return is a tuple it is assumed to be of the form
                # (<output value>, <output key>) where <output key> is used to
                # override the output key for the result which defaults to the
                # event name.
                if type(ret) == tuple:
                    out_key = ret[1]
                    ret = ret[0]
                else:
                    out_key = event

                # Don't clobber results, instead allow them to aggregate.
                if out_key in info:
                    info[out_key].update(ret)
                else:
                    info[out_key] = ret

        if info:
            if self.event_results_output_key:
                info = {self.event_results_output_key: info}

            return info


class ConfigBase(object):

    def __init__(self, path):
        self.path = path

    @classmethod
    def squash_int_range(cls, ilist):
        """Takes a list of integers and squashes consecutive values into a
        string range. Returned list contains mix of strings and ints.
        """
        irange = []
        rstart = None
        rprev = None

        sorted(ilist)
        for i, value in enumerate(ilist):
            if rstart is None:
                if i == (len(ilist) - 1):
                    irange.append(value)
                    break

                rstart = value

            if rprev is not None:
                if rprev != (value - 1):
                    if rstart == rprev:
                        irange.append(rstart)
                    else:
                        irange.append("{}-{}".format(rstart, rprev))
                        if i == (len(ilist) - 1):
                            irange.append(value)

                    rstart = value
                elif i == (len(ilist) - 1):
                    irange.append("{}-{}".format(rstart, value))
                    break

            rprev = value

        return irange

    @classmethod
    def expand_value_ranges(cls, ranges):
        """
        Takes a string containing ranges of values such as 1-3 and 4,5,6,7 and
        expands them into a single list.
        """
        if not ranges:
            return ranges

        expanded = []
        ranges = ranges.split(',')
        for subrange in ranges:
            # expand ranges
            subrange = subrange.partition('-')
            if subrange[1] == '-':
                expanded += range(int(subrange[0]), int(subrange[2]) + 1)
            else:
                expanded.append(int(subrange[0]))

        return expanded

    @property
    def exists(self):
        if os.path.exists(self.path):
            return True

        return False

    def get(self, key, section=None, expand_ranges=False):
        raise NotImplementedError


class SectionalConfigBase(ConfigBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._sections = {}
        # this provides an easy sectionless lookup but is prone to collisions.
        # always returns the last value for key found in config file.
        self._flattened_config = {}
        self._load()

    @property
    def all(self):
        return self._sections

    def get(self, key, section=None, expand_ranges=False):
        """ If section is None use flattened """
        if section is None:
            value = self._flattened_config.get(key)
        else:
            value = self._sections.get(section, {}).get(key)

        if expand_ranges:
            return self.expand_value_ranges(value)

        return value

    def _load(self):
        if not self.exists:
            return

        current_section = None
        with open(self.path) as fd:
            for line in fd:
                if re.compile(r"^\s*#").search(line):
                    continue

                # section names are not expected to contain whitespace
                ret = re.compile(r"^\s*\[(\S+)].*").search(line)
                if ret:
                    current_section = ret.group(1)
                    self._sections[current_section] = {}
                    continue

                if current_section is None:
                    continue

                # key names may contain whitespace
                expr = r"^\s*(\S+(?:\s+\S+)?)\s*=\s*(\S+)"
                ret = re.compile(expr).search(line)
                if ret:
                    key = ret.group(1)
                    val = constants.bool_str(ret.group(2))
                    self._sections[current_section][key] = val
                    self._flattened_config[key] = val


class ConfigChecksBase(object):
    """
    This class is used to peform checks on file based config. The input is
    typically defined in defs/config_checks.yaml and each plugin that wants to
    perform these checks can implement this class.
    """

    def _validate(self, method):
        """
        @param method: name of a method that must exist in the implementation
        of this class and that is called to determine whether to run a config
        check. An example method could be one that checks if a particular
        package is installed.
        """
        return getattr(self, method)()

    def _get_config_handler(self, path):
        """
        Different services will have different config file formats.
        Implementations of this class should implement this method such that it
        returns an implementation of ConfigBase.
        """
        raise NotImplementedError

    def run_config_checks(self):
        path = os.path.join(constants.PLUGIN_YAML_DEFS, "config_checks.yaml")
        with open(path) as fd:
            yaml_defs = yaml.safe_load(fd.read())

        if not yaml_defs:
            return

        plugin_configs = yaml_defs.get(constants.PLUGIN_NAME, {})
        for label in plugin_configs:
            args = plugin_configs[label]
            callback = args.get("callback")
            if callback:
                if not self._validate(callback):
                    # assume feature not enabled
                    return

            path = os.path.join(constants.DATA_ROOT, args['path'])
            cfg = self._get_config_handler(path)
            for name in args["settings"]:
                check = args["settings"][name]
                op = check["operator"]
                section = check.get("section")
                actual = cfg.get(name, section=section)
                value = check["value"]
                raise_issue = False
                if actual is None:
                    if value is not None and not check["allow-unset"]:
                        raise_issue = True
                    else:
                        continue

                if not raise_issue and not getattr(operator, op)(actual,
                                                                 value):
                    raise_issue = True

                if raise_issue:
                    msg = (args["message"])
                    issue_utils.add_issue(issue_types.OpenstackWarning(msg))
                    # move on to next set of checks
                    break


class ServiceChecksBase(object):
    """This class should be used by any plugin that wants to identify
    and check the status of running services."""

    def __init__(self, service_exprs, *args, hint_range=None, **kwargs):
        """
        @param service_exprs: list of python.re expressions used to match a
        service name.
        @param hint_range: optional range reflecting a range that can be
                           extracted from any of the provided expressions and
                           used as a pre-search before doing a full search in
                           order to reduce unnecessary full searches.
        """
        super().__init__(*args, **kwargs)
        self.services = {}
        self.service_exprs = []
        for expr in service_exprs:
            hint = None
            if hint_range:
                start, end = hint_range
                hint = expr[start:end]

            self.service_exprs.append((expr, hint))

        self._get_running_services()

    def _get_running_services(self):
        """
        Execute each provided service expression against lines in ps and store
        each full line in a list against the service matched.
        """
        for line in CLIHelper().ps():
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

    def get_service_info_str(self):
        """Create a list of "<service> (<num running>)" for running services
        detected. Useful for display purposes."""
        service_info_str = []
        for svc in sorted(self.services):
            num_daemons = self.services[svc]["ps_cmds"]
            service_info_str.append("{} ({})".format(svc, len(num_daemons)))

        return service_info_str


class DPKGVersionCompare(object):

    def __init__(self, a):
        self.a = a

    def _exec(self, op, b):
        try:
            subprocess.check_call(['dpkg', '--compare-versions',
                                   self.a, op, b])
        except subprocess.CalledProcessError as se:
            if se.returncode == 1:
                return False

            raise se

        return True

    def __eq__(self, b):
        return self._exec('eq', b)

    def __lt__(self, b):
        return not self._exec('ge', b)

    def __gt__(self, b):
        return not self._exec('le', b)

    def __le__(self, b):
        return self._exec('le', b)

    def __ge__(self, b):
        return self._exec('ge', b)


def dict_to_formatted_str_list(f):
    """
    Convert dict returned by function f to a list of strings of format
    '<name> <version>'.
    """
    def _dict_to_formatted_str_list(*args, **kwargs):
        ret = f(*args, **kwargs)
        if not ret:
            return []

        return ["{} {}".format(*e) for e in ret.items()]

    return _dict_to_formatted_str_list


class PackageChecksBase(object):

    def get_version(self, pkg):
        """
        Return version of package.
        """
        raise NotImplementedError

    def is_installed(self, pkg):
        """ Returns True if pkg is installed """
        raise NotImplementedError

    @property
    @dict_to_formatted_str_list
    def all_formatted(self):
        """
        Returns list of packages. Each entry in the list is an item
        looking like "<pkgname> <pkgver>".
        """
        return self.all

    @property
    def all(self):
        """ Returns results matched for all expressions. """
        raise NotImplementedError

    @property
    def core(self):
        """ Returns results matched for core expressions. """
        raise NotImplementedError


class DockerImageChecksBase(PackageChecksBase):

    def __init__(self, core_pkgs, other_pkgs=None):
        """
        @param core_pkgs:
        package names.
        @param other_pkg_exprs:
        """
        self.core_image_exprs = core_pkgs
        self.other_image_exprs = other_pkgs or []
        self._core_images = {}
        self._other_images = {}
        self._all_images = {}
        # The following expression muct match any package name.
        self._match_expr_template = \
            r"^(\S+/(\S+))\s+([\d\.]+)\s+(\S+)\s+.+"
        self.cli = CLIHelper()

    def _match_image(self, image, entry):
        expr = self._match_expr_template.format(image)
        ret = re.compile(expr).match(entry)
        if ret:
            return ret[1], ret[2], ret[3]

        return None, None, None

    def get_container_images(self):
        images = []
        for line in self.cli.docker_ps():
            ret = re.compile(r"^\S+\s+(\S+):(\S+)\s+.+").match(line)
            if not ret:
                continue

            images.append((ret[1], ret[2]))

        return images

    @property
    def _all(self):
        """ Returns dict of all packages matched. """
        if self._all_images:
            return self._all_images

        used_images = self.get_container_images()
        image_list = self.cli.docker_images()
        if not image_list:
            return

        all_exprs = self.core_image_exprs + self.other_image_exprs
        for line in image_list:
            for image in all_exprs:
                fullname, shortname, version = self._match_image(image, line)
                if shortname is None:
                    continue

                if (fullname, version) not in used_images:
                    continue

                if image in self.core_image_exprs:
                    self._core_images[shortname] = version
                else:
                    self._other_images[shortname] = version

        # ensure sorted
        self._core_images = sorted_dict(self._core_images)
        self._other_images = sorted_dict(self._other_images)
        combined = {}
        combined.update(self._core_images)
        combined.update(self._other_images)
        self._all_images = sorted_dict(combined)

        return self._all_images

    @property
    def all(self):
        """
        Returns list of all images matched.
        """
        return self._all

    @property
    def core(self):
        """
        Only return results that matched from the "core" set of images.
        """
        if self._core_images:
            return self._core_images

        if self._other_images:
            return {}

        # go fetch
        self.all
        return self._core_images


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
        self._match_expr_template = r"^ii\s+({}[0-9a-z\-]*)\s+(\S+)\s+.+"
        self.cli = CLIHelper()

    def is_installed(self, pkg):
        dpkg_l = self.cli.dpkg_l()
        if not dpkg_l:
            return

        for line in dpkg_l:
            if re.compile(r"^ii\s+{}\s+.+".format(pkg)).search(line):
                return True

        return False

    def get_version(self, pkg):
        """ Return version of package. """
        if pkg in self._all:
            return self._all[pkg]

        dpkg_l = self.cli.dpkg_l()
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
            return ret[1], ret[2]

        return None, None

    @property
    def _all(self):
        """ Returns dict of all packages matched. """
        if self._all_packages:
            return self._all_packages

        dpkg_l = self.cli.dpkg_l()
        if not dpkg_l:
            return self._all_packages

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
    def all(self):
        """
        Returns list of all packages matched. Each entry in the list is an item
        looking like "<pkgname> <pkgver>".
        """
        return self._all

    @property
    def core(self):
        """
        Only return results that matched from the "core" set of packages.
        """
        if self._core_packages:
            return self._core_packages

        # If _other_packages has contents it implies that we have already
        # collected and there are no core packages so return empty.
        if self._other_packages:
            return self._core_packages

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
        self.snap_list_all = CLIHelper().snap_list_all()

    def get_version(self, snap):
        """ Return version of package. """
        if snap in self._all:
            return self._all[snap]

        if self.snap_list_all:
            for line in self.snap_list_all:
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

        if not self.snap_list_all:
            return {}

        _core = {}
        _other = {}
        all_exprs = self.core_snap_exprs + self.other_snap_exprs
        for line in self.snap_list_all:
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
    def all(self):
        """
        Return results that matched from the all/any set of snaps.
        """
        return self._all

    @property
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
