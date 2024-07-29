from propertree.propertree2 import PTreeLogicalGrouping
from hotsos.core.log import log
from hotsos.core.ycheck.engine.properties.common import (
    YPropertyMappedOverrideBase,
)
from hotsos.core.ycheck.engine.properties.requires.types import (
    apt,
    binary,
    snap,
    config,
    pebble,
    systemd,
    property as rproperty,
    path,
    varops,
)

CACHE_CHECK_KEY = '__PREVIOUSLY_CACHED_PROPERTY_TYPE'


def cache_result(cache, item, result, grouped=False):
    """
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
    will be that from 'apt: foo'. If both exist then it will be the result of
    'apt: bar'.

    @param item: YRequirementType object
    @param grouped: If True, item is part of a (logical) group of one or
                    more items or a list with more than one item to which
                    to default logical operator (AND) will be applied.
    @return: boolean result i.e. True or False
    """
    previously_cached = getattr(cache, CACHE_CHECK_KEY)
    req_prop_type = item.__class__.__name__
    if not grouped or (result and
                       previously_cached in (None, req_prop_type)):
        if previously_cached is None:
            cache.set(CACHE_CHECK_KEY, req_prop_type)

        log.debug("merging item (type=%s) cache id=%s into cache id=%s",
                  req_prop_type, item.cache.id, cache.id)
        cache.merge(item.cache)


class RequiresLogicalGrouping(PTreeLogicalGrouping):
    """ Logical grouping support for requires property. """
    override_autoregister = False

    @property
    def _parent_cache(self):
        """
        Get parent cache since we will want to link it to descendants.
        """
        return self.override_parent.cache

    def fetch_item_result(self, item):  # pylint: disable=arguments-differ
        """
        Override this method but make it an instance method hence the pylint
        disable.
        """
        if isinstance(item, RequiresLogicalGrouping):
            item.cache = self._parent_cache

        result = super().fetch_item_result(item)
        if isinstance(item, RequiresLogicalGrouping):
            cache_result(self._parent_cache, item, result, True)

        return result


class YPropertyRequires(YPropertyMappedOverrideBase):
    """
    Requires property. This is a mapped property that needs one or more of its
    member properties to be defined.
    """
    override_keys = ['requires']
    override_members = [apt.YRequirementTypeAPT,
                        binary.YRequirementTypeBinary,
                        snap.YRequirementTypeSnap,
                        config.YRequirementTypeConfig,
                        pebble.YRequirementTypePebble,
                        systemd.YRequirementTypeSystemd,
                        rproperty.YRequirementTypeProperty,
                        path.YRequirementTypePath,
                        varops.YPropertyVarOps]
    # We want to be able to use this property both on its own and as a member
    # of other mapping properties e.g. Checks. The following setting enables
    # this.
    override_auto_implicit_member = False
    override_logical_grouping_type = RequiresLogicalGrouping

    @property
    def result(self):
        """
        Content can either be a single requirement, dict of requirement groups
        or list of requirements. List may contain individual requirements or
        groups.
        """
        # pylint: disable=duplicate-code
        log.debug("running requirement")
        try:
            results = []
            stop_executon = False
            for member in self.members:
                for item in member:
                    result = item.result
                    if not isinstance(item, RequiresLogicalGrouping):
                        cache_result(self.cache, item, result, grouped=False)

                    results.append(result)
                    if RequiresLogicalGrouping.is_exit_condition_met('and',
                                                                     result):
                        stop_executon = True
                        break

                if stop_executon:
                    break

            log.debug("%s results=%s", self.__class__.__name__, results)
            result = all(results)
            self.cache.set('passes', result)
            return result
        except Exception as exc:
            log.error("caught exception when running requirement: %s", exc)
            raise
