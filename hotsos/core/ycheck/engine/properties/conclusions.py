import builtins

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
    def message(self):
        """ Optional """
        return self.content.get('message')

    def message_with_format_dict_applied(self, property=None, checks=None):
        """
        If a format-dict is provided this will resolve any cache references
        then format the message. Returns formatted message.

        Either property or checks must be provided (but not both).

        @params property: optional YPropertyOverride object.
        @params checks: optional dict of YPropertyChecks objects.
        """
        fdict = self.format_dict
        if not fdict:
            return self.message

        for key, value in fdict.items():
            if PropertyCacheRefResolver.is_valid_cache_ref(value):
                rvalue = PropertyCacheRefResolver(value, property=property,
                                                  checks=checks).resolve()
                log.debug("updating format-dict key=%s with cached %s (%s)",
                          key, value, rvalue)
                fdict[key] = rvalue

        message = self.message
        if message is not None:
            message = str(message).format(**fdict)

        return message

    def message_with_format_list_applied(self, searchresult):
        """
        If format-groups have been provided this will extract their
        corresponding values from searchresult and use them to format the
        message. Returns formatted message.

        @param searchresult: a searchtools.SearchResult object.
        """
        if not self.format_groups:
            return self.message

        format_list = []
        for idx in self.format_groups:
            format_list.append(searchresult.get(idx))

        message = self.message
        if message is not None:
            message = str(message).format(*format_list)

        return message

    def apply_renderer_function(self, value, func):
        if not func:
            return value

        if func == "comma_join":
            # needless to say this will only work with lists, dicts etc.
            return ', '.join(value)

        return getattr(builtins, func)(value)

    @cached_yproperty_attr
    def format_dict(self):
        """
        Optional dict of key/val pairs used to format the message string.

        Keys that start with @ are used as references to properties allowing
        us to extract cached values.
        """
        _format_dict = self.content.get('format-dict')
        if not _format_dict:
            return {}

        fdict = {}
        for k, v in _format_dict.items():
            if PropertyCacheRefResolver.is_valid_cache_ref(v):
                # save string for later parsing/extraction
                fdict[k] = v
            else:
                func = v.partition(':')[2]
                v = v.partition(':')[0]
                fdict[k] = self.apply_renderer_function(self.get_import(v),
                                                        func)

        return fdict

    @cached_yproperty_attr
    def format_groups(self):
        """ Optional """
        return self.content.get('search-result-format-groups')

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

    def get_item_result_callback(self, item):
        name = str(item)
        if name not in self.checks_instances:
            raise Exception("no check found with name {}".format(name))

        return self.checks_instances[name].result

    def run_single(self, item):
        final_results = []
        for checkname in item:
            final_results.append(self.get_item_result_callback(checkname))

        return final_results


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


class YPropertyConclusion(object):

    def __init__(self, name, priority, decision=None, raises=None):
        self.name = name
        self.priority = priority
        self.decision = decision
        self.raises = raises
        self.issue = None
        # Use this to add any context to the issue. This context
        # will be retrievable as machine readable output.
        self.context = IssueContext()

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

        search_results = None
        for check in checks.values():
            if check.search and check.search.cache.results:
                search_results = check.search.cache.results
                if search_results:
                    # Save some context for the issue
                    self.context.set(**{r.source: r.linenumber
                                        for r in search_results})
            elif check.requires:
                # Dump the requires cache into the context. We improve this
                # later by addign more info.
                self.context.set(**check.requires.cache.cache)

        if self.raises.format_groups:
            if search_results:
                # we only use the first result
                message = self.raises.message_with_format_list_applied(
                                                             search_results[0])
            else:
                message = self.raises.message
                log.warning("no search results found so not applying format "
                            "groups")
        else:
            message = self.raises.message_with_format_dict_applied(
                                                                 checks=checks)

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

    def __iter__(self):
        section = YDefsSection(self._override_name, self.content)
        for c in section.leaf_sections:
            yield YPropertyConclusion(c.name, c.priority, decision=c.decision,
                                      raises=c.raises)
