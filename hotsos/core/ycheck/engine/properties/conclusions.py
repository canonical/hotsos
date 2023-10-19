from hotsos.core.exceptions import ScenarioException
from hotsos.core.issues import IssueContext
from hotsos.core.log import log
from hotsos.core.ycheck.engine.properties.common import (
    cached_yproperty_attr,
    YPropertyOverrideBase,
    PropertyCacheRefResolver,
    YPropertyMappedOverrideBase,
    LogicalCollectionHandler,
    YDefsSection,
    add_to_property_catalog,
    YDefsContext,
)


@add_to_property_catalog
class YPropertyPriority(YPropertyOverrideBase):

    @classmethod
    def _override_keys(cls):
        return ['priority']

    @cached_yproperty_attr
    def value(self):
        return int(self.content or 1)


@add_to_property_catalog
class YPropertyRaises(YPropertyOverrideBase):

    @classmethod
    def _override_keys(cls):
        return ['raises']

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

        for key, value in fdict.items():  # pylint: disable=E1101
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

    @cached_yproperty_attr
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

    @cached_yproperty_attr
    def type(self):
        """ Name of core.issues.IssueTypeBase object and will be used to raise
        an issue or bug using message as argument. """
        _type = "hotsos.core.issues.{}".format(self.content['type'])
        return self.get_cls(_type)


class YPropertyDecisionBase(YPropertyMappedOverrideBase,
                            LogicalCollectionHandler):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.checks_instances = None

    @classmethod
    def _override_mapped_member_types(cls):
        return []

    def add_checks_instances(self, checks):
        self.checks_instances = checks

    def get_item_result_callback(self, item, grouped=False):
        name = str(item)
        if name not in self.checks_instances:
            raise Exception("no check found with name {}".format(name))

        return self.checks_instances[name].result


class YPropertyDecisionLogicalGroupsExtension(YPropertyDecisionBase):

    @classmethod
    def _override_keys(cls):
        return LogicalCollectionHandler.VALID_GROUP_KEYS


@add_to_property_catalog
class YPropertyDecision(YPropertyDecisionBase):

    @classmethod
    def _override_keys(cls):
        return ['decision']

    @classmethod
    def _override_mapped_member_types(cls):
        return super()._override_mapped_member_types() + \
                    [YPropertyDecisionLogicalGroupsExtension]


@add_to_property_catalog
class YPropertyConclusion(YPropertyMappedOverrideBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.issue = None
        # Use this to add any context to the issue. This context
        # will be retrievable as machine readable output.
        self.issue_context = IssueContext()

    @classmethod
    def _override_keys(cls):
        return ['conclusion']

    @classmethod
    def _override_mapped_member_types(cls):
        return [YPropertyPriority, YPropertyDecision, YPropertyRaises]

    @property
    def name(self):
        if hasattr(self, 'conclusion_name'):
            return getattr(self, 'conclusion_name')

    def reached(self, checks):
        """
        Return True/False result of this conclusion and prepare issue info.
        """
        log.debug("running conclusion %s", self.name)
        self.decision.add_checks_instances(checks)
        log.debug("decision:start")
        result = self.decision.run_collection()
        log.debug("decision:end")
        if not result:
            return False

        bug_id = self.raises.bug_id
        bug_type = self.raises.type.ISSUE_TYPE
        is_bug_type = bug_type == 'bug'
        if ((is_bug_type and bug_id is None) or
                (bug_id is not None and not is_bug_type)):
            msg = ("both bug-id (current={}) and bug type (current={}) "
                   "required in order to raise a bug".format(bug_id, bug_type))
            raise ScenarioException(msg)

        message = self.raises.message_formatted(checks=checks)
        if self.raises.type.ISSUE_TYPE == 'bug':
            self.issue = self.raises.type(self.raises.bug_id, message)
        else:
            self.issue = self.raises.type(message)

        return result


@add_to_property_catalog
class YPropertyConclusions(YPropertyOverrideBase):

    @classmethod
    def _override_keys(cls):
        return ['conclusions']

    def initialise(self, ypvars):
        """
        Perform initialisation tasks for this set of conclusions.

        * create conclusions context containing vars
        """
        self.conclusion_context = YDefsContext({'vars': ypvars})

    @cached_yproperty_attr
    def _conclusions(self):
        log.debug("parsing conclusions section")
        if not hasattr(self, 'conclusion_context'):
            raise Exception("conclusions not yet initialised")

        resolved = []
        for name, content in self.content.items():
            s = YDefsSection(self._override_name,
                             {name: {'conclusion': content}},
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
