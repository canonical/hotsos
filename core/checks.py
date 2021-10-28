import os

import importlib
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
from core.utils import mktemp_dump, sorted_dict
from core.known_bugs_utils import (
    add_known_bug,
    BugSearchDef,
)
from core.searchtools import (
    FileSearcher,
    SearchDef,
    SequenceSearchDef,
)
from core.ystruct import (
    YAMLDefOverrideBase,
    YAMLDefSection,
)

SVC_EXPR_TEMPLATES = {
    "absolute": r".+\S+bin/({})(?:\s+.+|$)",
    "snap": r".+\S+\d+/({})(?:\s+.+|$)",
    "relative": r".+\s({})(?:\s+.+|$)",
    }


class YAMLDefExpr(YAMLDefOverrideBase):
    KEYS = ['start', 'body', 'end', 'expr', 'hint']

    @property
    def expr(self):
        """
        Subkey e.g for start.expr, body.expr. Expression defs that are just
        a string or use subkey 'expr' will rely on __getattr__.
        """
        return self.content.get('expr', self.content)

    @property
    def hint(self):
        return self.content.get('hint', None)

    def __getattr__(self, name):
        """
        An expression can be provided in multiple ways. The simplest form is
        where the value of the event is a pattern string hence why we override
        this to just return the content if it is not a dict.
        """
        if type(self.content) == dict:
            return super().__getattr__(name)
        else:
            return self.content


class YAMLDefMessage(YAMLDefOverrideBase):
    KEYS = ['message', 'message-format-result-groups']

    @property
    def format_groups(self):
        return self.content

    def __str__(self):
        return self.content


class YAMLDefSettings(YAMLDefOverrideBase):
    KEYS = ['settings']

    def __iter__(self):
        for key, val in self.content.items():
            yield key, val


class YAMLDefReleases(YAMLDefOverrideBase):
    KEYS = ['releases']

    def __iter__(self):
        for key, val in self.content.items():
            yield key, val


class YAMLDefResultsPassthrough(YAMLDefOverrideBase):
    KEYS = ['passthrough-results']

    def __bool__(self):
        """ If returns True, the master results list is passed to callbacks
        so that they may fetch results in their own way. This is required e.g.
        when processing results with analytics.LogEventStats.
        """
        return bool(self.content)


class YAMLDefInput(YAMLDefOverrideBase):
    KEYS = ['input']
    TYPE_COMMAND = 'command'
    TYPE_FILESYSTEM = 'filesystem'

    # NOTE: this must be set by the handler object that is using the overrides.
    #       we need a better way to do this but we can't use __init__ because
    #       this class must be provided uninstantiated.
    EVENT_CHECK_OBJ = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._path = None

    @property
    def meta(self):
        defaults = {'allow-all-logs': True,
                    'args': [],
                    'kargs': {},
                    'args-callback': None}
        _meta = self.content.get('meta', defaults)
        defaults.update(_meta)
        return defaults

    @property
    def path(self):
        if self.type == self.TYPE_FILESYSTEM:
            path = os.path.join(constants.DATA_ROOT, self.value)
            if constants.USE_ALL_LOGS and self.meta['allow-all-logs']:
                path = "{}*".format(path)

            return path
        elif self.type == self.TYPE_COMMAND:
            if self._path:
                return self._path

            args_callback = self.meta['args-callback']
            if args_callback:
                args, kwargs = getattr(self.EVENT_CHECK_OBJ, args_callback)()
            else:
                args = self.meta['args']
                kwargs = self.meta['kwargs']

            # get command output
            out = getattr(CLIHelper(), self.value)(*args,
                                                   **kwargs)
            # store in temp file to make it searchable
            # NOTE: we dont need to delete this at the the end since they are
            # created in the plugun tmp dir which is wiped at the end of the
            # plugin run.
            self._path = mktemp_dump(''.join(out))
            return self._path


class YAMLDefRequires(YAMLDefOverrideBase):
    KEYS = ['requires']

    @property
    def passes(self):
        if self.type == 'apt':
            pkg = self.value
            return APTPackageChecksBase(core_pkgs=[pkg]).is_installed(pkg)
        else:
            self.debug("unsupported yaml requires type=%s", self.type)

        return False


class YAMLDefConfig(YAMLDefOverrideBase):
    KEYS = ['config']

    def check(self, key, value, op, allow_unset=False, section=None):
        mod = self.handler.rpartition('.')[0]
        cls = self.handler.rpartition('.')[2]
        self.cfg = getattr(importlib.import_module(mod), cls)(self.path)
        actual = self.cfg.get(key, section=section)
        if actual is None:
            if allow_unset:
                return True
            else:
                return False

        if getattr(operator, op)(actual, value):
            return True

        return False


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

    def add_bug_check(self, id, release, minbroken, minfixed, message):
        bug = {'id': id, 'minbroken': minbroken, 'minfixed': minfixed,
               'message': message}
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

        overrides = [YAMLDefInput, YAMLDefExpr, YAMLDefMessage,
                     YAMLDefReleases]
        # TODO: need a better way to provide this instance to the input
        #       override.
        YAMLDefInput.EVENT_CHECK_OBJ = self
        plugin_checks = yaml_defs.get(constants.PLUGIN_NAME, {})
        for name, group in plugin_checks.items():
            group = YAMLDefSection(name, group, override_handlers=overrides)
            log.debug("sections=%s, events=%s",
                      len(group.branch_sections),
                      len(group.leaf_sections))

            pkg_name = group.name
            p = PackageReleaseCheckObj(pkg_name)
            for bug_check in group.leaf_sections:
                bug = bug_check.name
                message = str(bug_check.message)
                for rel, info in dict(bug_check.releases).items():
                    p.add_bug_check(bug, rel, info['min-broken'],
                                    info['min-fixed'], message)

            self._checks.append(p)

    def __call__(self):
        self._load_definitions()
        for check in self._checks:
            pkg = check.package_name
            # if installed do check
            if pkg not in self._pkg_info:
                return

            pkgver = self._pkg_info[pkg]
            for release, bugs in check.bugs.items():
                if release != self._release_name:
                    continue

                for bug in bugs:
                    minbroken = bug['minbroken']
                    minfixed = bug['minfixed']
                    if (not pkgver < DPKGVersionCompare(minbroken) and
                            pkgver < DPKGVersionCompare(minfixed)):
                        log.debug("bug identified for package=%s release=%s "
                                  "version=%s", pkg, release, pkgver)
                        message_format_kwargs = {'package_name': pkg,
                                                 'version_current': pkgver,
                                                 'version_fixed': minfixed}

                        message = bug.get('message')
                        if not message:
                            # generic message
                            message = ("package {package_name} with version "
                                       "{version_current} contains a known "
                                       "bug and should be upgraded to >= "
                                       "{version_fixed}")

                        add_known_bug(bug['id'],
                                      message.format(**message_format_kwargs))


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
        log.debug("loading bug searches for plugin '%s' (groups=%d)",
                  constants.PLUGIN_NAME, len(plugin_bugs))

        overrides = [YAMLDefInput, YAMLDefExpr, YAMLDefMessage]
        # TODO: need a better way to provide this instance to the input
        #       override.
        YAMLDefInput.EVENT_CHECK_OBJ = self
        for name, group in plugin_bugs.items():
            bug_group = YAMLDefSection(name, group,
                                       override_handlers=overrides)
            log.debug("loading bug group '%s' - sections=%s, events=%s",
                      bug_group.name,
                      len(bug_group.branch_sections),
                      len(bug_group.leaf_sections))
            for bug in bug_group.leaf_sections:
                id = bug.name
                message_format = bug.message_format_result_groups
                if message_format:
                    message_format = message_format.format_groups

                pattern = bug.expr.value
                # NOTE: pattern can be string or list of strings
                bdef = {'def':
                        BugSearchDef(
                                pattern,
                                bug_id=str(id),
                                hint=bug.hint.value,
                                message=str(bug.message),
                                message_format_result_groups=message_format)}

                datasource = bug.input.path
                log.debug("bug=%s path=%s", id, datasource)
                bdef["datasource"] = datasource
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
                if bugsearch["def"].message_format_result_groups:
                    message = bugsearch["def"].rendered_message(_results[0])
                    add_known_bug(tag, message)
                else:
                    add_known_bug(tag, bugsearch["def"].message)

    def __call__(self):
        """ Must be callable since its run automatically. """
        self.run_checks()


class EventCheckResult(object):
    """ This is passed to an event check callback when matches are found """

    def __init__(self, defs_section, defs_event, search_results,
                 sequence_def=None):
        """
        @param defs_section: section name from yaml
        @param defs_event: event label/name from yaml
        @param search_results: searchtools.SearchResultsCollection
        @param sequence_def: if set the search results are from a
                            searchtools.SequenceSearchDef and are therefore
                            grouped as sections of results rather than a single
                            set of results.
        """
        self.section = defs_section
        self.name = defs_event
        self.results = search_results
        self.sequence_def = sequence_def


class EventChecksBase(ChecksBase):

    def __init__(self, *args, callback_helper=None,
                 event_results_output_key=None, **kwargs):
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
        """
        super().__init__(*args, **kwargs)
        self.callback_helper = callback_helper
        self.event_results_output_key = event_results_output_key
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

        log.debug("loading event definitions for plugin=%s group=%s",
                  constants.PLUGIN_NAME, self._yaml_defs_group)
        plugin = yaml_defs.get(constants.PLUGIN_NAME, {})
        group_name = self._yaml_defs_group

        overrides = [YAMLDefInput, YAMLDefExpr, YAMLDefResultsPassthrough]
        # TODO: need a better way to provide this instance to the input
        #       override.
        YAMLDefInput.EVENT_CHECK_OBJ = self
        group = YAMLDefSection(group_name, plugin.get(group_name),
                               override_handlers=overrides)
        log.debug("sections=%s, events=%s",
                  len(group.branch_sections),
                  len(group.leaf_sections))

        for event in group.leaf_sections:
            results_passthrough = bool(event.passthrough_results)
            log.debug("event: %s", event.name)
            log.debug("input: %s:%s", event.input.type, event.input.path)
            log.debug("passthrough: %s", results_passthrough)

            # if this is a multiline event (has a start and end), append
            # this to the tag so that it can be used with
            # core.analytics.LogEventStats.
            search_meta = {'searchdefs': [], 'datasource': None,
                           'passthrough_results': results_passthrough}

            if event.expr:
                hint = None
                if event.hint:
                    hint = event.hint.value

                search_meta['searchdefs'].append(
                    SearchDef(event.expr.value, tag=event.name, hint=hint))
            elif event.start:
                if (event.body or
                        (event.end and not results_passthrough)):
                    log.debug("event '%s' search is a sequence", event.name)
                    sd_start = SearchDef(event.start.expr)

                    sd_end = None
                    # explicit end is optional for sequence definition
                    if event.end:
                        sd_end = SearchDef(event.end.expr)

                    sd_body = None
                    if event.body:
                        sd_body = SearchDef(event.body.expr)

                    # NOTE: we don't use hints here
                    sequence_def = SequenceSearchDef(start=sd_start,
                                                     body=sd_body,
                                                     end=sd_end,
                                                     tag=event.name)
                    search_meta['searchdefs'].append(sequence_def)
                    search_meta['is_sequence'] = True
                elif (results_passthrough and
                      (event.start and event.end)):
                    # start and end required for core.analytics.LogEventStats
                    search_meta['searchdefs'].append(
                        SearchDef(event.start.expr,
                                  tag="{}-start".format(event.name),
                                  hint=event.start.hint))
                    search_meta['searchdefs'].append(
                        SearchDef(event.end.expr,
                                  tag="{}-end".format(event.name),
                                  hint=event.end.hint))
                else:
                    log.debug("unexpected search definition passthrough=%s "
                              "body provided=%s, end provided=%s",
                              results_passthrough, event.body is not None,
                              event.end is not None)
            else:
                log.debug("invalid search definition for event '%s' in "
                          "section '%s'", event, event.parent.name)
                continue

            datasource = event.input.path
            section_name = event.parent.name
            if section_name not in self._event_defs:
                self._event_defs[section_name] = {}

            search_meta['datasource'] = datasource
            self._event_defs[section_name][event.name] = search_meta

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
            for event, event_meta in section.items():
                sequence_def = None
                if event_meta.get('passthrough_results'):
                    # this is for implementations that have their own means of
                    # retreiving results.
                    search_results = results
                else:
                    if event_meta.get('is_sequence'):
                        sequence_def = event_meta['searchdefs'][0]
                        search_results = results.find_sequence_sections(
                            sequence_def)
                        if search_results:
                            search_results = search_results.values()
                    else:
                        search_results = results.find_by_tag(event)

                if not search_results:
                    continue

                # We want this to throw an exception if the callback is not
                # defined.
                callback_name = event.replace('-', '_')
                callback = self.callback_helper.callbacks[callback_name]
                log.debug("executing event callback '%s'", callback_name)
                event_results_obj = EventCheckResult(section_name, event,
                                                     search_results,
                                                     sequence_def=sequence_def)
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
    defined in defs/config_checks.yaml.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._check_defs = {}

    def _load_definitions(self):
        path = os.path.join(constants.PLUGIN_YAML_DEFS, "config_checks.yaml")
        with open(path) as fd:
            yaml_defs = yaml.safe_load(fd.read())

        if not yaml_defs:
            return

        overrides = [YAMLDefInput, YAMLDefExpr, YAMLDefMessage,
                     YAMLDefRequires, YAMLDefConfig, YAMLDefSettings]
        # TODO: need a better way to provide this instance to the input
        #       override.
        YAMLDefInput.EVENT_CHECK_OBJ = self
        plugin = yaml_defs.get(constants.PLUGIN_NAME, {})
        for name, group in plugin.items():
            group = YAMLDefSection(name, group, override_handlers=overrides)
            log.debug("sections=%s, events=%s",
                      len(group.branch_sections),
                      len(group.leaf_sections))

            for cfg_check in group.leaf_sections:
                self._check_defs[cfg_check.name] = {
                    'message': cfg_check.message,
                    'config': cfg_check.config,
                    'requires': cfg_check.requires,
                    'settings': dict(cfg_check.settings)}

    def run_checks(self):
        for name, cfg_check in self._check_defs.items():
            if not cfg_check['requires'].passes:
                continue

            log.debug("config check section=%s", name)
            message = str(cfg_check['message'])
            for cfg_key, settings in cfg_check['settings'].items():
                op = settings['operator']
                value = settings['value']
                section = settings['section']
                allow_unset = bool(settings.get('allow-unset', False))
                log.debug("checking config %s has value %s", cfg_key, value)
                raise_issue = False
                if not cfg_check['config'].check(cfg_key, value, op,
                                                 section=section,
                                                 allow_unset=allow_unset):
                    raise_issue = True

                if raise_issue:
                    issue = issue_types.OpenstackWarning(message)
                    issue_utils.add_issue(issue)
                    # move on to next set of checks
                    break

    def __call__(self):
        """ Must be callable since it's run automatically. """
        self._load_definitions()
        self.run_checks()


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
        self.service_exprs = []
        self.hint_range = hint_range
        self._processes = {}
        self._service_info = {}
        self.service_exprs = service_exprs

    def hint(self, expr, line, offset=None):
        """
        Apply a hint search to the line. Returns True if a match is found
        otherwise False.

        Since this hint is a chopped version of the full expression it may now
        contain incomplete/invalid regex. In this case we automatically grow it
        until it no longer causes an exception to be raised.
        """
        if not self.hint_range:
            return True

        start, end = self.hint_range
        if offset is not None:
            # Set a limit to how far we will go
            if offset > min(10, len(expr) - 1):
                return False

            offset += 1
            end += offset

        try:
            ret = re.compile(expr[start:end]).search(line)
            if ret:
                return True
        except re.error:
            # if sre_constants is raised we need to adjust the
            # hint.
            if offset is None:
                offset = 1

            return self.hint(expr, line, offset)

        return False

    def _get_systemd_units(self, expr):
        """
        Search systemd unit instances.

        @param expr: expression used to match one or more units in --list-units
        """
        units = []
        for line in CLIHelper().systemctl_list_units():
            ret = re.compile(expr).match(line)
            if ret:
                units.append(ret.group(1))

        return units

    @property
    def services(self):
        """
        Return a dict of identified systemd services and their state.

        Services are represented as either direct or indirect units and
        typically use one or the other. We homongenise these to present state
        based on the one we think is being used. Enabled units are aggregated
        but masked units are not so that they can be identified and reported.
        """
        if self._service_info:
            return self._service_info

        svc_info = {}
        indirect_svc_info = {}
        for line in CLIHelper().systemctl_list_unit_files():
            for expr in self.service_exprs:
                if not self.hint(expr, line):
                    continue

                # Add snap prefix/suffixes
                base_expr = r"(?:snap\.)?{}(?:\.daemon)?".format(expr)
                # NOTE: we include indirect services (ending with @) so that
                #       we can search for related units later.
                unit_expr = r'^\s*({}(?:@\S*)?)\.service'.format(base_expr)
                # match entries in systemctl list-unit-files
                unit_files_expr = r'{}\s+(\S+)'.format(unit_expr)

                ret = re.compile(unit_files_expr).match(line)
                if ret:
                    unit = ret.group(1)
                    state = ret.group(2)
                    if unit.endswith('@'):
                        # indirect or "template" units can have "instantiated"
                        # units where only the latter represents whether the
                        # unit is in use. If an indirect unit has instanciated
                        # units we use them to represent the state of the
                        # service.
                        unit_svc_expr = r"\s+({}\d*)".format(unit)
                        unit = unit.partition('@')[0]
                        if self._get_systemd_units(unit_svc_expr):
                            state = 'enabled'

                        indirect_svc_info[unit] = state
                    else:
                        svc_info[unit] = state

        if indirect_svc_info:
            # Allow indirect unit info to override given certain conditions
            for unit, state in indirect_svc_info.items():
                if unit in svc_info:
                    if state == 'disabled' or svc_info[unit] == 'enabled':
                        continue

                svc_info[unit] = state

        self._service_info = svc_info
        return self._service_info

    @property
    def processes(self):
        """
        Identify running processes from ps using the provided search filter.
        """
        if self._processes:
            return self._processes

        for line in CLIHelper().ps():
            for expr in self.service_exprs:
                if not self.hint(expr, line):
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
                        if svc not in self._processes:
                            self._processes[svc] = []

                        self._processes[svc].append(ret.group(0))
                        break

        return self._processes

    @property
    def service_info_str(self):
        """Return a dictionary of systemd services and processes.

        The services under the `systemd` key are sub-keyed by service state.
        The processes unde the `ps` key are returned as a list.
        """
        info = {'systemd': {},
                'ps': []}
        for svc, state in self.services.items():
            if state not in info['systemd']:
                info['systemd'][state] = []

            info['systemd'][state].append(svc)

        for svc in sorted(self.processes):
            num_daemons = len(self.processes[svc])
            info['ps'].append("{} ({})".format(svc, num_daemons))

        return info


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
