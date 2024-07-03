from functools import cached_property

from propertree.propertree2 import (
    PTreeLogicalGrouping,
    PTreeOverrideLiteralType,
)
from hotsos.core.exceptions import ScenarioException
from hotsos.core.issues import IssueContext
from hotsos.core.log import log
from hotsos.core.ycheck.engine.properties.common import (
    YPropertyOverrideBase,
    PropertyCacheRefResolver,
    YPropertyMappedOverrideBase,
    YDefsSection,
    YDefsContext,
)


class YPropertyPriority(YPropertyOverrideBase):
    _override_keys = ['priority']

    def __int__(self):
        return int(self.content or 1)


class YPropertyRaises(YPropertyOverrideBase):
    _override_keys = ['raises']

    @property
    def cve_id(self):
        """ optional setting. """
        return self.content.get('cve-id')

    @property
    def bug_id(self):
        """ optional setting. do this to allow querying. """
        return self.content.get('bug-id')

    @property
    def message(self):
        """ optional setting. do this to allow querying. """
        return self.content.get('message')

    def message_formatted(self, checks=None):
        """
        If a format-dict is provided this will resolve any cache references
        then format the message. Returns formatted message.

        @params checks: optional dict of YPropertyChecks objects.
        """
        fdict = self.format_dict
        if not fdict:
            return self.message

        fdict = dict(fdict)

        for key, value in fdict.items():
            if PropertyCacheRefResolver.is_valid_cache_ref(value):
                rvalue = PropertyCacheRefResolver(value,
                                                  pcrr_vars=self.context.vars,
                                                  checks=checks).resolve()
                log.debug("updating format-dict key=%s with cached %s (%s)",
                          key, value, rvalue)
                fdict[key] = rvalue

        message = self.message
        if message is not None:
            message = str(message).format(**fdict)

        return message

    @cached_property
    def format_dict(self):
        """
        Optional dict of key/val pairs used to format the message string.

        Keys that start with @ are used as references to yaml properties
        allowing us to extract cached values. Alternatively an import path
        can be specified in which case the value is imported immediately and
        optional rendering function applied.
        """
        _format_dict = self.content.get('format-dict')
        if not _format_dict:
            return {}

        fdict = {}
        for k, v in _format_dict.items():
            if PropertyCacheRefResolver.is_valid_cache_ref(v):
                # save for later parsing/extraction
                fdict[k] = v
                continue

            # process now since there is no cache to resolve
            path, _, func = v.partition(':')
            value = self.get_import(path)
            if func:
                value = PropertyCacheRefResolver.apply_renderer(value, func)

            fdict[k] = value

        return fdict

    @cached_property
    def type(self):
        """ Name of core.issues.IssueTypeBase object and will be used to raise
        an issue or bug using message as argument. """
        _type = "hotsos.core.issues.{}".format(self.content['type'])
        return self.get_cls(_type)


class DecisionBase():

    def get_check_item(self, name):
        checks = self.context.checks  # pylint: disable=E1101
        try:
            log.debug("%s: get_check_item() %s", self.__class__.__name__,
                      name)
            return checks[name]
        except KeyError:
            log.exception("check '%s' not found in %s", name, checks)


class DecisionLogicalGrouping(DecisionBase, PTreeLogicalGrouping):
    _override_autoregister = False

    def get_items(self):
        items = []
        for item in super().get_items():
            if isinstance(item, PTreeOverrideLiteralType):
                item = self.get_check_item(str(item))

            items.append(item)

        log.debug("%s: items: %s", self.__class__.__name__, items)
        return items


class YPropertyDecision(DecisionBase, YPropertyMappedOverrideBase):
    _override_keys = ['decision']
    # no members, we are using a mapping to get a custom PTreeLogicalGrouping
    _override_members = []
    _override_logical_grouping_type = DecisionLogicalGrouping

    @property
    def result(self):
        results = []
        try:
            stop_executon = False
            for member in self.members:
                for item in member:
                    if isinstance(item, PTreeOverrideLiteralType):
                        item = self.get_check_item(str(item))

                    result = item.result
                    results.append(result)
                    if DecisionLogicalGrouping.is_exit_condition_met('and',
                                                                     result):
                        stop_executon = True
                        break

                if stop_executon:
                    break

            result = all(results)
            log.debug("decision: %s result=%s", results, result)
            return result
        except Exception:
            log.exception("something went wrong when executing decision")
            raise


class YPropertyConclusion(YPropertyMappedOverrideBase):
    _override_keys = ['conclusion']
    _override_members = [YPropertyPriority, YPropertyDecision, YPropertyRaises]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.issue = None
        # Use this to add any context to the issue. This context
        # will be retrievable as machine readable output.
        self.issue_context = IssueContext()

    @property
    def name(self):
        if hasattr(self, 'conclusion_name'):
            return getattr(self, 'conclusion_name')

    def reached(self, checks):
        """
        Return True/False result of this conclusion and prepare issue info.
        """
        log.debug("running conclusion %s", self.name)
        log.debug("decision:start")
        result = self.decision.result
        log.debug("decision:end")
        if not result:
            return False

        cve_id = self.raises.cve_id
        bug_id = self.raises.bug_id
        bug_type = self.raises.type.ISSUE_TYPE
        is_bug_type = bug_type in ('bug', 'cve')
        if cve_id or bug_id or is_bug_type:
            if not (all([bug_id, bug_type == 'bug']) or
                    all([cve_id, bug_type == 'cve'])):
                msg = ("both cve-id/bug-id (current={}) and bug type "
                       "(current={}) required in order to raise a bug".
                       format(bug_id or cve_id, bug_type))
                raise ScenarioException(msg)

        message = self.raises.message_formatted(checks=checks)
        if is_bug_type:
            self.issue = self.raises.type(bug_id or cve_id, message)
        else:
            self.issue = self.raises.type(message)

        return result


class YPropertyConclusions(YPropertyOverrideBase):
    _override_keys = ['conclusions']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._initialised = False
        self.conclusion_context = YDefsContext()

    def initialise(self, ypvars, checks):
        """
        Perform initialisation tasks for this set of conclusions.
        """
        self.conclusion_context.update({'vars': ypvars, 'checks': checks})
        self._initialised = True

    @cached_property
    def _conclusions(self):
        log.debug("parsing conclusions section")
        if not self._initialised:
            raise Exception("conclusions not yet initialised")

        resolved = []
        for name, content in self.content.items():
            s = YDefsSection(self._override_name,
                             {name: {'conclusion': content}},
                             override_handlers=self.root.override_handlers,
                             resolve_path=self._override_path,
                             context=self.conclusion_context)
            for c in s.leaf_sections:
                c.conclusion.conclusion_name = c.name
                resolved.append(c.conclusion)

        return resolved

    def __iter__(self):
        log.debug("iterating over conclusions")
        for c in self._conclusions:
            log.debug("returning conclusion %s", c.name)
            yield c
