from functools import cached_property

from hotsos.core.log import log
from hotsos.core.host_helpers import (
    APTPackageHelper,
    DPKGVersion,
)
from hotsos.core.ycheck.engine.properties.requires import (
    intercept_exception,
    YRequirementTypeBase,
    PackageCheckItemsBase,
)


class APTCheckItems(PackageCheckItemsBase):

    @cached_property
    def packaging_helper(self):
        return APTPackageHelper(self.packages_to_check)

    @cached_property
    def installed_versions(self):
        _versions = []
        for p in self.installed:
            _versions.append(self.packaging_helper.get_version(p))

        return _versions

    def normalize_version_criteria(self, version_criteria):
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

    def package_version_within_ranges(self, pkg, version_criteria):
        """Check if pkg's version satisfies any criterion listed in
        the version_criteria.

        @param pkg: The name of the apt package
        @param version_criteria: List of version ranges to normalize

        @return: True if ver(pkg) satisfies any criterion, false otherwise.
        """
        result = True
        pkg_version = self.packaging_helper.get_version(pkg)

        # Supported operations for defining version ranges
        ops = {
            "eq": lambda lhs, rhs: lhs == DPKGVersion(rhs),
            "lt": lambda lhs, rhs: lhs < DPKGVersion(rhs),
            "le": lambda lhs, rhs: lhs <= DPKGVersion(rhs),
            "gt": lambda lhs, rhs: lhs > DPKGVersion(rhs),
            "ge": lambda lhs, rhs: lhs >= DPKGVersion(rhs),
            "min": lambda lhs, rhs: ops["ge"](lhs, rhs),
            "max": lambda lhs, rhs: ops["le"](lhs, rhs),
        }

        version_criteria = self.normalize_version_criteria(version_criteria)

        for version_criterion in version_criteria:
            # Each criterion is evaluated on its own
            # so if any of the criteria is true, then
            # the check is also true.
            for op_name, op_fn in ops.items():
                if op_name in version_criterion:
                    version = str(version_criterion[op_name])
                    # Check if the criterion is satisfied or not
                    if not op_fn(str(pkg_version), version):
                        break
            else:
                # Loop is not exited by a break which means
                # all ops in the criterion are satisfied.
                result = True
                # Break the outer loop
                break
            result = False

        log.debug("package %s=%s within version ranges %s "
            "(result=%s)", pkg, pkg_version, version_criteria, result)
        return result


class YRequirementTypeAPT(YRequirementTypeBase):
    """ Provides logic to perform checks on APT packages. """
    _override_keys = ['apt']
    _overrride_autoregister = True

    @property
    @intercept_exception
    def _result(self):
        _result = True
        items = APTCheckItems(self.content)

        # bail on first fail i.e. if any not installed
        if not items.not_installed:
            for pkg, versions in items:
                log.debug("package %s installed=%s", pkg, _result)
                if not versions:
                    continue
                _result = items.package_version_within_ranges(pkg, versions)
                # bail at first failure
                if not _result:
                    break
        else:
            log.debug("one or more packages not installed so returning False "
                      "- %s", ', '.join(items.not_installed))
            # bail on first fail i.e. if any not installed
            _result = False

        self.cache.set('package', ', '.join(items.installed))
        self.cache.set('version', ', '.join([
            str(x) for x in items.installed_versions]))
        log.debug('requirement check: apt %s (result=%s)',
                  ', '.join(items.packages_to_check), _result)
        return _result
