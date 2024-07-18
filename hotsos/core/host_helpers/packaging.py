import abc
import re
import subprocess
from dataclasses import dataclass

from hotsos.core.factory import FactoryBase
from hotsos.core.host_helpers.cli import CLIHelper
from hotsos.core.log import log
from hotsos.core.utils import sorted_dict


class DPKGBadVersionSyntax(Exception):
    """ Exception raised when an invalid version is provided in a check. """


class DPKGVersion():
    """ Helper for querying and comparing dpkg packaging versions. """
    def __init__(self, a):
        self.a = str(a)

    def _compare_impl(self, op, b):
        try:
            output = subprocess.check_output(['dpkg', '--compare-versions',
                                              self.a, op, b],
                                             stderr=subprocess.STDOUT)
            if re.search(b"dpkg: warning: version.*has bad syntax:.*", output):
                raise DPKGBadVersionSyntax(output)
        except subprocess.CalledProcessError as se:
            if se.returncode == 1:
                return False

            raise se

        return True

    def __repr__(self):
        return str(self)

    def __str__(self):
        return self.a

    def __eq__(self, b):
        return self._compare_impl('eq', str(b))

    def __lt__(self, b):
        return not self._compare_impl('ge', str(b))

    def __gt__(self, b):
        return not self._compare_impl('le', str(b))

    def __le__(self, b):
        return self._compare_impl('le', str(b))

    def __ge__(self, b):
        return self._compare_impl('ge', str(b))

    @staticmethod
    def normalize_version_criteria(version_criteria):
        """Normalize all the criterions in a criteria.

        Normalization does the following:
        - removes empty criteria
        - replaces old ops with the new ones
        - sorts each criterion(ascending) and criteria(descending)
        - adds upper/lower bounds to criteria, where needed

        @param version_criteria: List of version ranges to normalize
        @return: Normalized list of version ranges
        """

        # Step 0: Ensure that all version values are DPKGVersion type
        for idx, version_criterion in enumerate(version_criteria):
            for k, v in version_criterion.items():
                version_criterion.update({k: DPKGVersion(v)})

        # Step 1: Remove empty criteria
        version_criteria = [x for x in version_criteria if len(x) > 0]

        # Step 2: Replace legacy ops with the new ones
        legacy_ops = {"min": "ge", "max": "le"}
        for idx, version_criterion in enumerate(version_criteria):
            for lop, nop in legacy_ops.items():
                if lop in version_criterion:
                    version_criterion[nop] = version_criterion[lop]
                    del version_criterion[lop]

        # Step 3: Sort each criterion in itself, so the smallest version
        # appears first
        for idx, version_criterion in enumerate(version_criteria):
            version_criterion = dict(sorted(version_criterion.items(),
                                     key=lambda a: a[1]))
            version_criteria[idx] = version_criterion

        # Step 4: Sort all criteria by the first element in the criterion
        version_criteria = sorted(version_criteria,
                                  key=lambda a: list(a.values())[0])

        # Step 5: Add the implicit upper/lower bounds where needed
        lower_bound_ops = ["gt", "ge", "eq"]  # ops that define a lower bound
        upper_bound_ops = ["lt", "le", "eq"]  # ops that define an upper bound
        equal_compr_ops = ["eq", "ge", "le"]  # ops that compare for equality
        for idx, version_criterion in enumerate(version_criteria):
            log.debug("\tchecking criterion %s", str(version_criterion))

            has_lower_bound = any(x in lower_bound_ops
                                  for x in version_criterion)
            has_upper_bound = any(x in upper_bound_ops
                                  for x in version_criterion)
            is_the_last_item = idx == (len(version_criteria) - 1)
            is_the_first_item = idx == 0

            log.debug("\t\tcriterion %s has lower bound?"
                      "%s has upper bound? %s", str(version_criterion),
                      has_lower_bound, has_upper_bound)

            if not has_upper_bound and not is_the_last_item:
                op = "le"  # default
                next_criterion = version_criteria[idx + 1]
                next_op, next_val = list(next_criterion.items())[0]
                # If the next criterion op compares for equality, then the
                # implicit op added to this criterion should not compare for
                # equality.
                if next_op in equal_compr_ops:
                    op = "lt"
                log.debug("\t\tadding implicit upper bound %s:%s to %s", op,
                          next_val, version_criterion)
                version_criterion[op] = next_val
            elif not has_lower_bound and not is_the_first_item:
                op = "ge"  # default
                prev_criterion = version_criteria[idx - 1]
                prev_op, prev_val = list(prev_criterion.items())[-1]
                # If the previous criterion op compares for equality, then the
                # implicit op added to this criterion should not compare for
                # equality.
                if prev_op in equal_compr_ops:
                    op = "gt"
                log.debug("\t\tadding implicit lower bound %s:%s to %s", op,
                          prev_val, version_criterion)
                version_criterion[op] = prev_val

            # Re-sort and overwrite the criterion
            version_criteria[idx] = dict(
                sorted(version_criterion.items(),
                       key=lambda a: a[1]))

        # Step 6: Sort by descending order so the largest version range
        # appears first
        version_criteria = sorted(version_criteria,
                                  key=lambda a: list(a.values())[0],
                                  reverse=True)

        log.debug("final criteria: %s", str(version_criteria))
        return version_criteria

    @staticmethod
    def is_version_within_ranges(version, version_criteria):
        """Check if pkg's version satisfies any criterion listed in
        the version_criteria.

        @param version: Version
        @param version_criteria: Criteria to check version against

        @return: True if ver(pkg) satisfies any criterion, false otherwise.
        """
        result = True

        # Supported operations for defining version ranges
        ops = {
            "eq": lambda lhs, rhs: lhs == DPKGVersion(rhs),
            "lt": lambda lhs, rhs: lhs < DPKGVersion(rhs),
            "le": lambda lhs, rhs: lhs <= DPKGVersion(rhs),
            "gt": lambda lhs, rhs: lhs > DPKGVersion(rhs),
            "ge": lambda lhs, rhs: lhs >= DPKGVersion(rhs),
            # Here, it's necessary to use lambda. It defers the
            # "ops" access to runtime, so ops["ge"] exists when
            # this is executed.
            # pylint: disable-next=unnecessary-lambda
            "min": lambda lhs, rhs: ops["ge"](lhs, rhs),
            # pylint: disable-next=unnecessary-lambda
            "max": lambda lhs, rhs: ops["le"](lhs, rhs),
        }

        version_criteria = DPKGVersion.normalize_version_criteria(
            version_criteria)

        for version_criterion in version_criteria:
            if not version_criterion.keys() <= ops.keys():
                raise NameError(
                    "Unrecognized comparison operator name(s):"
                    f"{version_criterion.keys()-ops.keys()}")
            # Each criterion is evaluated on its own
            # so if any of the criteria is true, then
            # the check is also true.
            for op_name, op_fn in ops.items():
                if op_name in version_criterion:
                    cversion = str(version_criterion[op_name])
                    # Check if the criterion is satisfied or not
                    if not op_fn(str(version), cversion):
                        break
            else:
                # Loop is not exited by a break which means
                # all ops in the criterion are satisfied.
                result = True
                log.debug("version criterion %s satisfied by %s",
                          version_criterion, version)
                # Break the outer loop
                break
            result = False

        log.debug("version %s within version ranges %s "
                  "(result=%s)", version, version_criteria, result)
        return result


class PackageHelperBase(abc.ABC):
    """ Base class for packaging helpers. """
    def get_version(self, pkg):
        """
        Return version of package.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def is_installed(self, pkg):
        """ Returns True if pkg is installed """

    @property
    def all_formatted(self):
        """
        Returns list of packages. Each entry in the list is an item
        looking like "<pkgname> <pkgver>".

        Converts dict to a list of strings of format '<name> <version>'.
        """

        _all = self.all
        if not _all:
            return []

        return [f"{e[0]} {e[1]}" for e in _all.items()]

    @property
    def all(self):
        """ Returns results matched for all expressions. """
        raise NotImplementedError

    @property
    def core(self):
        """ Returns results matched for core expressions. """
        raise NotImplementedError


class DockerImageHelper(PackageHelperBase):
    """ Helpers for analysing docker images. """
    def __init__(self, core_pkgs, other_pkgs=None):
        """
        @param core_pkgs:
        package names.
        @param other_pkg_exprs:
        """
        self.core_image_exprs = core_pkgs
        self.other_image_exprs = other_pkgs or []
        self._core_images = {}
        self._other_images = {}
        self._all_images = {}
        # The following expression muct match any package name.
        self._match_expr_template = \
            r"^(\S+/(\S+))\s+([\d\.]+)\s+(\S+)\s+.+"
        self.cli = CLIHelper()

    def is_installed(self, pkg):
        return pkg in self.all

    def _match_image(self, image, entry):
        expr = self._match_expr_template.format(image)
        ret = re.compile(expr).match(entry)
        if ret:
            return ret[1], ret[2], ret[3]

        return None, None, None

    def get_container_images(self):
        images = []
        for line in self.cli.docker_ps():
            ret = re.compile(r"^\S+\s+(\S+):(\S+)\s+.+").match(line)
            if not ret:
                continue

            images.append((ret[1], ret[2]))

        return images

    @property
    def _all(self):
        """ Returns dict of all packages matched. """
        if self._all_images:
            return self._all_images

        used_images = self.get_container_images()
        image_list = self.cli.docker_images()
        if not image_list:
            return None

        all_exprs = self.core_image_exprs + self.other_image_exprs
        for line in image_list:
            for image in all_exprs:
                fullname, shortname, version = self._match_image(image, line)
                if shortname is None:
                    continue

                if (fullname, version) not in used_images:
                    continue

                if image in self.core_image_exprs:
                    self._core_images[shortname] = version
                else:
                    self._other_images[shortname] = version

        # ensure sorted
        self._core_images = sorted_dict(self._core_images)
        self._other_images = sorted_dict(self._other_images)
        combined = {}
        combined.update(self._core_images)
        combined.update(self._other_images)
        self._all_images = sorted_dict(combined)

        return self._all_images

    @property
    def all(self):
        """
        Returns list of all images matched.
        """
        return self._all

    @property
    def core(self):
        """
        Only return results that matched from the "core" set of images.
        """
        if self._core_images:
            return self._core_images

        if self._other_images:
            return {}

        # go fetch
        _ = self.all
        return self._core_images


class APTPackageHelper(PackageHelperBase):
    """ Helpers for analysing apt packages. """
    def __init__(self, core_pkgs, other_pkgs=None):
        """
        @param core_pkgs: list of python.re expressions used to match
        package names.
        @param other_pkg_exprs: optional list of python.re expressions used to
        match packages that are not considered part of the core set. This can
        be used to distinguish between core and non-core packages.
        """
        self.core_pkg_exprs = core_pkgs
        self.other_pkg_exprs = other_pkgs or []
        self._core_packages = {}
        self._other_packages = {}
        self._all_packages = {}
        # Match any installed package status
        self._match_expr_template = r"^.i\s+({}[0-9a-z\-]*)\s+(\S+)\s+.+"
        self.cli = CLIHelper()

    def is_installed(self, pkg, allow_full_search=False):
        """
        Check if package is installed and return True/False. By default only
        checks against packages matched using main expression.

        @param pkg: name of package we want to check
        @param allow_full_search: if True will do a full dpkg search for the
                                  package of not found matches from the main
                                  expression.
        """
        if pkg in self.all:
            return True

        if not allow_full_search:
            return False

        dpkg_l = self.cli.dpkg_l()
        if not dpkg_l:
            return False

        cexpr = re.compile(rf"^.i\s+{pkg}\s+.+")
        for line in dpkg_l:
            # See https://man7.org/linux/man-pages/man1/dpkg-query.1.html for
            # package states.
            # Here we check package status not desired action.
            if cexpr.search(line):
                return True

        return False

    def get_version(self, pkg):
        """ Return version of package. """
        if pkg in self._all:
            return self._all[pkg]

        dpkg_l = self.cli.dpkg_l()
        if dpkg_l:
            for line in dpkg_l:
                name, version = self._match_package(pkg, line)
                if name:
                    return version

        return None

    def _match_package(self, pkg, entry):
        """ Returns tuple of (package name, version) """
        expr = self._match_expr_template.format(pkg)
        ret = re.compile(expr).match(entry)
        if ret:
            return ret[1], ret[2]

        return None, None

    @property
    def _all(self):
        """ Returns dict of all packages matched. """
        if self._all_packages:
            return self._all_packages

        dpkg_l = self.cli.dpkg_l()
        if not dpkg_l:
            return self._all_packages
        all_exprs = self.core_pkg_exprs + self.other_pkg_exprs
        for line in dpkg_l:
            for pkg in all_exprs:
                name, version = self._match_package(pkg, line)
                if name is None:
                    continue
                if pkg in self.core_pkg_exprs:
                    self._core_packages[name] = version
                else:
                    self._other_packages[name] = version

        # ensure sorted
        self._core_packages = sorted_dict(self._core_packages)
        self._other_packages = sorted_dict(self._other_packages)
        combined = {}
        combined.update(self._core_packages)
        combined.update(self._other_packages)
        self._all_packages = sorted_dict(combined)

        return self._all_packages

    @property
    def all(self):
        """
        Returns list of all packages matched. Each entry in the list is an item
        looking like "<pkgname> <pkgver>".
        """
        return self._all

    @property
    def core(self):
        """
        Only return results that matched from the "core" set of packages.
        """
        if self._core_packages:
            return self._core_packages

        # If _other_packages has contents it implies that we have already
        # collected and there are no core packages so return empty.
        if self._other_packages:
            return self._core_packages

        # go fetch
        _ = self.all
        return self._core_packages


@dataclass(frozen=True)
class AptPackage:
    """ Representation of an APT package.  """
    name: str
    version: str


class AptFactory(FactoryBase):
    """
    Factory to dynamically get package versions.

    AptPackage object is returned when a getattr() is done on this object
    using the name of package.
    """

    def __getattr__(self, name):
        log.debug("creating AptPackage object for %s", name)
        helper = APTPackageHelper([name])
        if name in helper.all:
            return AptPackage(name, helper.all[name])

        return None


class SnapPackageHelper(PackageHelperBase):
    """ Helpers for analysing snap packages. """
    def __init__(self, core_snaps, other_snaps=None):
        """
        @param core_snaps: list of python.re expressions used to match
        snap names.
        @param other_snap_exprs: optional list of python.re expressions used to
        match snap names for snaps that are not considered part of the
        core set.
        """
        self.core_snap_exprs = core_snaps
        self.other_snap_exprs = other_snaps or []
        self._core_snaps = {}
        self._other_snaps = {}
        self._all_snaps = {}
        self._match_expr_template = r"^({})\s+([\S]+)\s+([\d]+)\s+(\S+)\s+.+"
        self.snap_list_all = CLIHelper().snap_list_all()

    def is_installed(self, pkg):
        return pkg in self.all

    @staticmethod
    def _get_snap_info_from_line(line, cexpr):
        """ Returns snap name and info if found in line. """
        ret = re.match(cexpr, line)
        if ret:
            return {'name': ret.group(1),
                    'version': ret.group(2),
                    'revision': ret.group(3),
                    'channel': ret.group(4),
                    }

        return None

    def get_revision(self, snap):
        """ Return revision of package.
        """
        info = self._get_snap_info(snap)
        if info:
            return info[0]['revision']

        return None

    def get_version(self, pkg):
        """ Return version of snap package.

        Assumes only one snap will be matched.
        """
        info = self._get_snap_info(pkg)
        if info:
            return info[0]['version']

        return None

    def get_channel(self, pkg):
        """ Return channel of snap package.

        Assumes only one snap will be matched.
        """
        info = self._get_snap_info(pkg)
        if info:
            return info[0]['channel']

        return None

    def _get_snap_info(self, snap_name_expr):
        """
        Return a list of info for snaps matched using the expression.

        @param snap_name_expr: is a regular expression that can match one or
                               more snaps.
        @return: a list of snaps and their info.
        """
        if not self.snap_list_all:
            return None

        info = []
        cexpr = re.compile(self._match_expr_template.format(snap_name_expr))
        for line in self.snap_list_all:
            snap_info = self._get_snap_info_from_line(line, cexpr)
            if snap_info:
                info.append(snap_info)

        return info

    @property
    def _all(self):
        if self._all_snaps:
            return self._all_snaps

        if not self.snap_list_all:
            return {}

        _core = {}
        _other = {}
        all_exprs = self.core_snap_exprs + self.other_snap_exprs
        for snap in all_exprs:
            for snap_info in self._get_snap_info(snap):
                name = snap_info['name']
                version = snap_info['version']
                channel = snap_info['channel']
                # only show latest version installed
                if snap in self.core_snap_exprs:
                    if name in _core:
                        if version > _core[name]['version']:
                            _core[name]['version'] = version
                            _core[name]['channel'] = channel
                    else:
                        _core[name] = {'version': version,
                                       'channel': channel}
                else:
                    if name in _other:
                        if version > _other[name]['version']:
                            _other[name]['version'] = version
                            _other[name]['channel'] = channel
                    else:
                        _other[name] = {'version': version,
                                        'channel': channel}

        # ensure sorted
        self._core_snaps = sorted_dict(_core)
        self._other_snaps = sorted_dict(_other)
        combined = {}
        combined.update(_core)
        combined.update(_other)
        self._all_snaps = sorted_dict(combined)

        return self._all_snaps

    @property
    def all(self):
        """
        Return results that matched from the all/any set of snaps.
        """
        return self._all

    @property
    def all_formatted(self):
        _all = self.all
        if not _all:
            return []

        return [f"{name} {info['version']}" for name, info in _all.items()]

    @property
    def core(self):
        """
        Only return results that matched from the "core" set of snaps.
        """
        if self._core_snaps:
            return self._core_snaps

        if self._other_snaps:
            return {}

        # go fetch
        _ = self.all
        return self._core_snaps
