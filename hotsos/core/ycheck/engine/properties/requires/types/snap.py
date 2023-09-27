from functools import cached_property

from hotsos.core.host_helpers import SnapPackageHelper
from hotsos.core.log import log
from hotsos.core.ycheck.engine.properties.requires import (
    intercept_exception,
    YRequirementTypeBase,
    PackageCheckItemsBase,
)


class SnapCheckItems(PackageCheckItemsBase):

    # NOTE: the following pylint disable can be removed when we move to newer
    #       pylint.
    @cached_property
    def packaging_helper(self):  # pylint: disable=W0236
        return SnapPackageHelper(core_snaps=self.packages_to_check)

    @cached_property
    def installed_revisions(self):
        _revisions = []
        for p in self.installed:
            _revisions.append(self.packaging_helper.get_revision(p))

        return _revisions

    @cached_property
    def installed_channels(self):
        _channels = []
        for p in self.installed:
            _channels.append(self.packaging_helper.get_channel(p))

        return _channels

    def package_info_matches(self, pkg, pkg_info):
        """
        If snap package has revisions and/or channels we check them here.

        @param pkg: name of package
        @param pkg_info: list of {min: x, max: y, channel: z}
        """
        result = False

        # Ranges must be specified as min:max
        if any((i.get('min') is None and i.get('max') is not None) or
               (i.get('max') is None and i.get('min') is not None)
                for i in pkg_info):
            raise Exception("revision ranges for snap package '{}' contain "
                            "one or more range with a missing min or max "
                            "value".format(pkg))

        _channel_to_check = None
        if any(i.get('min') is not None for i in pkg_info):
            revision = int(self.packaging_helper.get_revision(pkg))
            # compare revisions for the time being
            for item in sorted(pkg_info, key=lambda i: i['max'],
                               reverse=True):
                r_max = int(item['max'])
                r_min = int(item['min'])
                if r_min <= revision <= r_max:
                    if 'channel' in item:
                        _channel_to_check = item['channel']
                        break

                    log.debug("match snap revision within range %s:%s", r_min,
                              r_max)
                    return True

        if not all(i.get('channel') is None for i in pkg_info):
            channel = self.packaging_helper.get_channel(pkg)
            if _channel_to_check is not None:
                if _channel_to_check == channel:
                    result = True
            else:
                for item in pkg_info:
                    if item['channel'] == channel:
                        result = True
                        log.debug("match snap channel %s", channel)
                        break

        return result


class YRequirementTypeSnap(YRequirementTypeBase):
    """ Provides logic to perform checks on snap packages. """

    @classmethod
    def _override_keys(cls):
        return ['snap']

    @property
    def channel(self):
        return self.content.get('channel')

    @property
    @intercept_exception
    def _result(self):
        _result = True
        items = SnapCheckItems(self.content)
        # bail on first fail i.e. if any not installed
        if not items.not_installed:
            for pkg, info in items:
                if not info:
                    continue

                _result = items.package_info_matches(pkg, info)
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
        self.cache.set('channel', ', '.join(items.installed_channels))
        return _result
