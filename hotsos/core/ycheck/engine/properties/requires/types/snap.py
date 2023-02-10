from hotsos.core.log import log
from hotsos.core.utils import cached_property
from hotsos.core.host_helpers import SnapPackageHelper
from hotsos.core.ycheck.engine.properties.requires import (
    intercept_exception,
    YRequirementTypeBase,
    PackageCheckItemsBase,
)


class SnapCheckItems(PackageCheckItemsBase):

    @cached_property
    def packaging_helper(self):
        return SnapPackageHelper(core_snaps=self.packages_to_check)

    @cached_property
    def installed_revisions(self):
        _revisions = []
        for p in self.installed:
            _revisions.append(self.packaging_helper.get_revision(p))
        return _revisions

    def package_revision_within_ranges(self, pkg, ranges):
        result = False
        revision = int(self.packaging_helper.get_revision(pkg))
        # compare revisions for the time being
        for item in sorted(ranges, key=lambda i: i['max'],
                           reverse=True):
            r_max = int(item['max'])
            r_min = int(item['min'])
            if r_min <= revision <= r_max:
                result = True
        return result


class YRequirementTypeSnap(YRequirementTypeBase):
    """ Provides logic to perform checks on snap packages. """

    @classmethod
    def _override_keys(cls):
        return ['snap']

    @property
    @intercept_exception
    def _result(self):
        _result = True
        items = SnapCheckItems(self.content)
        # bail on first fail i.e. if any not installed
        if not items.not_installed:
            for pkg, versions in items:
                if not versions:
                    continue
                _result = items.package_revision_within_ranges(pkg, versions)
                # bail at first failure
                if not _result:
                    break
        else:
            log.debug("one or more packages not installed so returning False "
                      "- %s", ', '.join(items.not_installed))
            _result = False

        log.debug('requirement check: snap(s) %s (result=%s)',
                  ', '.join(items.installed), _result)
        self.cache.set('package', ', '.join(items.installed))
        self.cache.set('revision', ', '.join(items.installed_revisions))
        return _result
