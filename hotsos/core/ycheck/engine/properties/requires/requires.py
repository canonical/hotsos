from hotsos.core.log import log
from hotsos.core.ycheck.engine.properties.common import (
    YPropertyMappedOverrideBase,
    LogicalCollectionHandler,
    add_to_property_catalog,
)
from hotsos.core.ycheck.engine.properties.requires.types import (
    apt,
    snap,
    config,
    pebble,
    systemd,
    property as rproperty,
    path,
    varops,
)


class YPropertyRequiresBase(YPropertyMappedOverrideBase,
                            LogicalCollectionHandler):
    CACHE_CHECK_KEY = '__PREVIOUSLY_CACHED_PROPERTY_TYPE'

    @classmethod
    def _override_mapped_member_types(cls):
        return [apt.YRequirementTypeAPT,
                snap.YRequirementTypeSnap,
                config.YRequirementTypeConfig,
                pebble.YRequirementTypePebble,
                systemd.YRequirementTypeSystemd,
                rproperty.YRequirementTypeProperty,
                path.YRequirementTypePath,
                varops.YPropertyVarOps]

    def get_item_result_callback(self, item, grouped=False):
        """
        Evaluate item and return its result.

        Also copy the cache of the item into the local cache. If part of a
        logical group whereby more than one item is being evaluated to get
        a final results, we only copy the cache data if the result is True
        and  either (a) it is the first to be saved or (b) it has the same type
        as the previous one to be saved.

        For example with the following group:

        or:
          - apt: foo
          - apt: bar

        If package foo exists and bar does not, the final contents of the group
        will that from 'apt: foo'. If both exists then it will be the result of
        'apt: bar'.

        @param item: YRequirementType object
        @param grouped: If True, item is part of a (logical) group of one or
                        more items or a list with more than one item to which
                        to default logical operator (AND) will be applied.
        @return: boolean result i.e. True or False
        """
        result = item()
        previously_cached = getattr(self.cache, self.CACHE_CHECK_KEY)
        req_prop_type = item.__class__.__name__
        if not grouped or (result and
                           previously_cached in (None, req_prop_type)):
            if previously_cached is None:
                self.cache.set(self.CACHE_CHECK_KEY, req_prop_type)

            log.debug("merging item (type=%s) cache id=%s into cache id=%s",
                      req_prop_type, item.cache.id, self.cache.id)
            self.cache.merge(item.cache)

        return result

    @property
    def passes(self):
        """
        Content can either be a single requirement, dict of requirement groups
        or list of requirements. List may contain individual requirements or
        groups.
        """
        log.debug("running requirement")
        try:
            result = self.run_collection()
        except Exception:
            log.exception("exception caught during run_collection:")
            raise

        self.cache.set('passes', result)
        return result


class YPropertyRequiresLogicalGroupsExtension(YPropertyRequiresBase):

    @classmethod
    def _override_keys(cls):
        return LogicalCollectionHandler.VALID_GROUP_KEYS


@add_to_property_catalog
class YPropertyRequires(YPropertyRequiresBase):

    @classmethod
    def _override_keys(cls):
        return ['requires']

    @classmethod
    def _override_mapped_member_types(cls):
        return super()._override_mapped_member_types() + \
                    [YPropertyRequiresLogicalGroupsExtension]
