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
    systemd,
    property as rproperty,
    path,
)


class YPropertyRequiresBase(YPropertyMappedOverrideBase,
                            LogicalCollectionHandler):

    @classmethod
    def _override_mapped_member_types(cls):
        return [apt.YRequirementTypeAPT,
                snap.YRequirementTypeSnap,
                config.YRequirementTypeConfig,
                systemd.YRequirementTypeSystemd,
                rproperty.YRequirementTypeProperty,
                path.YRequirementTypePath]

    def get_item_result_callback(self, item, copy_cache=False):
        result = item()
        if copy_cache:
            log.debug("merging cache with item of type %s",
                      item.__class__.__name__)
            self.cache.merge(item.cache)

        return result

    def run_single(self, item):
        final_results = []
        for rtype in item:
            for entry in rtype:
                result = self.get_item_result_callback(entry,
                                                       copy_cache=True)
                final_results.append(result)

        return final_results

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
