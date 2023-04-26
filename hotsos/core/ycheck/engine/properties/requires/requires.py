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

    def get_item_result_callback(self, item, is_default_group=False):
        result = item()
        # if its a single group we can cache the results but otherwise it wont
        # make sense since all will conflict.
        if is_default_group:
            log.debug("merging item (type=%s) cache id=%s into cache id=%s",
                      item.__class__.__name__, item.cache.id, self.cache.id)
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
