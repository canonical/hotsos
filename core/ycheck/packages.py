from core import constants
from core.log import log
from core.checks import DPKGVersionCompare
from core.known_bugs_utils import add_known_bug
from core.ycheck import (
    YDefsLoader,
    AutoChecksBase,
    YDefsSection,
)


class PackageReleaseCheckObj(object):
    def __init__(self, package_name, context):
        self.package_name = package_name
        self.context = context
        self.bugs = {}

    def add_bug_check(self, id, release, minbroken, minfixed,
                      message):
        bug = {'id': id, 'minbroken': minbroken, 'minfixed': minfixed,
               'message': message}
        if release in self.bugs:
            self.bugs[release].append(bug)
        else:
            self.bugs[release] = [bug]


class YPackageChecker(AutoChecksBase):
    """
    This is used to check if the version of installed packages contain
    known bugs and report them if found. See defs/plugin_bug_checks.yaml.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._checks = []

    def load(self):
        """ Load bug search definitions from yaml """
        plugin_checks = YDefsLoader('package_bug_checks').load_plugin_defs()
        if not plugin_checks:
            return

        group = YDefsSection(constants.PLUGIN_NAME, plugin_checks,
                             checks_handler=self)
        log.debug("sections=%s, checks=%s",
                  len(group.branch_sections),
                  len(group.leaf_sections))

        for bug_check in group.leaf_sections:
            pkg_name = bug_check.parent.name
            p = PackageReleaseCheckObj(pkg_name, bug_check.context)
            bug = bug_check.name
            message = str(bug_check.message)
            for rel, info in dict(bug_check.settings).items():
                p.add_bug_check(bug, rel,
                                info['min-broken'],
                                info['min-fixed'], message)

            self._checks.append(p)

    def run(self):
        for check in self._checks:
            pkg = check.package_name
            apt_info = check.context.apt_all
            # if installed do check
            if pkg not in apt_info:
                log.debug("pkg %s not installed - skipping check", pkg)
                return

            pkgver = apt_info[pkg]
            for release, bugs in check.bugs.items():
                if release != check.context.release:
                    log.debug("releases do not match %s:%s", release,
                              check.context.release)
                    continue

                for bug in bugs:
                    minbroken = bug['minbroken']
                    minfixed = bug['minfixed']
                    log.debug(pkgver)
                    if (not pkgver < DPKGVersionCompare(minbroken) and
                            pkgver < DPKGVersionCompare(minfixed)):
                        log.debug("bug identified for package=%s release=%s "
                                  "version=%s", pkg, release, pkgver)
                        message_format_kwargs = {'package_name': pkg,
                                                 'version_current': pkgver,
                                                 'version_fixed': minfixed}

                        message = bug.get('message')
                        if not message:
                            # generic message
                            message = ("package {package_name} with version "
                                       "{version_current} contains a known "
                                       "bug and should be upgraded to >= "
                                       "{version_fixed}")

                        add_known_bug(bug['id'],
                                      message.format(**message_format_kwargs))
