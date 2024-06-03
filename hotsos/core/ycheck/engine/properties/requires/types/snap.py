from functools import cached_property

from hotsos.core.host_helpers import (
    SnapPackageHelper,
    DPKGVersion
)
from hotsos.core.log import log
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
        return [self.packaging_helper.get_revision(p) for p in self.installed]

    @cached_property
    def installed_versions(self):
        return [self.packaging_helper.get_version(p) for p in self.installed]

    @cached_property
    def installed_channels(self):
        return [self.packaging_helper.get_channel(p) for p in self.installed]

    def package_info_matches(self, pkg, pkg_infos):
        """
        If snap package has revisions and/or channels we check them here.

        @param pkg: name of package
        @param pkg_info: list of {min: x, max: y, channel: z}
        """
        log.debug("checking snap package %s against %s",
                  str(pkg), str(pkg_infos))
        valid_keys = {"revision", "version", "channel"}

        for pkg_info in pkg_infos:
            # Check if there are unrecognized keys.
            if not pkg_info.keys() <= valid_keys:
                raise Exception(f"Unrecognized key name {pkg_info.keys()}."
                                f"Valid key names are {valid_keys}")

            if "revision" in pkg_info:
                sub = pkg_info["revision"]
                log.debug("revision criteria: %s", str(sub))
                # We're leveraging DPKG's version comparison algorithm
                # for the revisions as well.
                revision = self.packaging_helper.get_revision(pkg)
                result = DPKGVersion.is_version_within_ranges(revision, [sub])
                if not result:
                    continue
                log.debug("revision %s satisifies %s", str(revision), str(sub))

            if "version" in pkg_info:
                sub = pkg_info["version"]
                log.debug("version criteria: %s", str(sub))
                version = self.packaging_helper.get_version(pkg)
                result = DPKGVersion.is_version_within_ranges(version, [sub])
                if not result:
                    continue
                log.debug("version %s satisifies %s", str(version), str(sub))

            if "channel" in pkg_info:
                channel_v = pkg_info["channel"]
                log.debug("channel criteria: %s", str(channel_v))
                pkg_channel = self.packaging_helper.get_channel(pkg)
                if channel_v != pkg_channel:
                    continue
                log.debug("channel %s satisifies %s", pkg_channel, channel_v)

            # Package satisfies all criteria.
            return True
        # All checks failed.
        return False


class YRequirementTypeSnap(YRequirementTypeBase):
    """ Provides logic to perform checks on snap packages. """
    _override_keys = ['snap']
    _overrride_autoregister = True

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
        self.cache.set('version', ', '.join(items.installed_versions))
        return _result
