import os
import glob

import re
import subprocess

from core.log import log
from core import constants
from core.cli_helpers import CLIHelper
from core.utils import sorted_dict

SVC_EXPR_TEMPLATES = {
    "absolute": r".+\S+bin/({})(?:\s+.+|$)",
    "snap": r".+\S+\d+/({})(?:\s+.+|$)",
    "relative": r".+\s({})(?:\s+.+|$)",
    }


class ConfigBase(object):

    def __init__(self, path):
        self.path = path

    @classmethod
    def squash_int_range(cls, ilist):
        """Takes a list of integers and squashes consecutive values into a
        string range. Returned list contains mix of strings and ints.
        """
        irange = []
        rstart = None
        rprev = None

        sorted(ilist)
        for i, value in enumerate(ilist):
            if rstart is None:
                if i == (len(ilist) - 1):
                    irange.append(value)
                    break

                rstart = value

            if rprev is not None:
                if rprev != (value - 1):
                    if rstart == rprev:
                        irange.append(rstart)
                    else:
                        irange.append("{}-{}".format(rstart, rprev))
                        if i == (len(ilist) - 1):
                            irange.append(value)

                    rstart = value
                elif i == (len(ilist) - 1):
                    irange.append("{}-{}".format(rstart, value))
                    break

            rprev = value

        return irange

    @classmethod
    def expand_value_ranges(cls, ranges):
        """
        Takes a string containing ranges of values such as 1-3 and 4,5,6,7 and
        expands them into a single list.
        """
        if not ranges:
            return ranges

        expanded = []
        ranges = ranges.split(',')
        for subrange in ranges:
            # expand ranges
            subrange = subrange.partition('-')
            if subrange[1] == '-':
                expanded += range(int(subrange[0]), int(subrange[2]) + 1)
            else:
                for val in subrange[0].split():
                    expanded.append(int(val))

        return sorted(expanded)

    @property
    def exists(self):
        if os.path.exists(self.path):
            return True

        return False

    def get(self, key, section=None, expand_to_list=False):
        raise NotImplementedError


class SectionalConfigBase(ConfigBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._sections = {}
        # this provides an easy sectionless lookup but is prone to collisions.
        # always returns the last value for key found in config file.
        self._flattened_config = {}
        self._load()

    @property
    def all(self):
        return self._sections

    def get(self, key, section=None, expand_to_list=False):
        """ If section is None use flattened """
        if section is None:
            value = self._flattened_config.get(key)
        else:
            value = self._sections.get(section, {}).get(key)

        if expand_to_list:
            return self.expand_value_ranges(value)

        return value

    @property
    def dump(self):
        with open(self.path) as fd:
            return fd.read()

    def _load(self):
        if not self.exists:
            return

        current_section = None
        with open(self.path) as fd:
            for line in fd:
                if re.compile(r"^\s*#").search(line):
                    continue

                # section names are not expected to contain whitespace
                ret = re.compile(r"^\s*\[(\S+)].*").search(line)
                if ret:
                    current_section = ret.group(1)
                    self._sections[current_section] = {}
                    continue

                if current_section is None:
                    continue

                # key names may contain whitespace
                # values may contain whitespace
                expr = r"^\s*(\S+(?:\s+\S+)?)\s*=\s*(.+)\s*"
                ret = re.compile(expr).search(line)
                if ret:
                    key = ret.group(1)
                    val = constants.bool_str(ret.group(2))
                    if type(val) == str:
                        val = val.strip()
                        for char in ["'", '"']:
                            val = val.strip(char)

                    self._sections[current_section][key] = val
                    self._flattened_config[key] = val


class ServiceChecksBase(object):
    """This class should be used by any plugin that wants to identify
    and check the status of running services."""

    def __init__(self, service_exprs, *args, ps_allow_relative=True,
                 **kwargs):
        """
        @param service_exprs: list of python.re expressions used to match a
        service name.
        @param ps_allow_relative: whether to allow commands to be identified
                                  from ps as not run using an absolute binary
                                  path e.g. mycmd as opposed to /bin/mycmd.
        """
        super().__init__(*args, **kwargs)
        self.ps_allow_relative = ps_allow_relative
        self._processes = {}
        self._service_info = {}
        self.service_exprs = set(service_exprs)

    def _get_systemd_units(self, expr):
        """
        Search systemd unit instances.

        @param expr: expression used to match one or more units in --list-units
        """
        units = []
        for line in CLIHelper().systemctl_list_units():
            ret = re.compile(expr).match(line)
            if ret:
                units.append(ret.group(1))

        return units

    @property
    def services(self):
        """
        Return a dict of identified systemd services and their state.

        Services are represented as either direct or indirect units and
        typically use one or the other. We homongenise these to present state
        based on the one we think is being used. Enabled units are aggregated
        but masked units are not so that they can be identified and reported.
        """
        if self._service_info:
            return self._service_info

        svc_info = {}
        indirect_svc_info = {}
        for line in CLIHelper().systemctl_list_unit_files():
            for expr in self.service_exprs:
                # Add snap prefix/suffixes
                base_expr = r"(?:snap\.)?{}(?:\.daemon)?".format(expr)
                # NOTE: we include indirect services (ending with @) so that
                #       we can search for related units later.
                unit_expr = r'^\s*({}(?:@\S*)?)\.service'.format(base_expr)
                # match entries in systemctl list-unit-files
                unit_files_expr = r'{}\s+(\S+)'.format(unit_expr)

                ret = re.compile(unit_files_expr).match(line)
                if ret:
                    unit = ret.group(1)
                    state = ret.group(2)
                    if unit.endswith('@'):
                        # indirect or "template" units can have "instantiated"
                        # units where only the latter represents whether the
                        # unit is in use. If an indirect unit has instanciated
                        # units we use them to represent the state of the
                        # service.
                        unit_svc_expr = r"\s+({}\d*)".format(unit)
                        unit = unit.partition('@')[0]
                        if self._get_systemd_units(unit_svc_expr):
                            state = 'enabled'

                        indirect_svc_info[unit] = state
                    else:
                        svc_info[unit] = state

        if indirect_svc_info:
            # Allow indirect unit info to override given certain conditions
            for unit, state in indirect_svc_info.items():
                if unit in svc_info:
                    if state == 'disabled' or svc_info[unit] == 'enabled':
                        continue

                svc_info[unit] = state

        self._service_info = svc_info
        return self._service_info

    @property
    def masked_services(self):
        """ Returns a list of masked services. """
        if not self.services:
            return []

        return self.service_info.get('masked', [])

    def get_process_cmd_from_line(self, line, expr):
        for expr_type, expr_tmplt in SVC_EXPR_TEMPLATES.items():
            if expr_type == 'relative' and not self.ps_allow_relative:
                continue

            ret = re.compile(expr_tmplt.format(expr)).match(line)
            if ret:
                svc = ret.group(1)
                log.debug("matched process %s with %s expr", svc,
                          expr_type)
                return svc

    def get_services_expanded(self, name):
        _expanded = []
        for line in CLIHelper().systemctl_list_units():
            expr = r'^\s*({}(@\S*)?)\.service'.format(name)
            ret = re.compile(expr).match(line)
            if ret:
                _expanded.append(ret.group(1))

        if not _expanded:
            _expanded = [name]

        return _expanded

    @property
    def service_filtered_ps(self):
        ps_filtered = []
        path = os.path.join(constants.DATA_ROOT,
                            'sys/fs/cgroup/unified/system.slice')
        for svc in self.services:
            for svc in self.get_services_expanded(svc):
                _path = os.path.join(path, "{}.service".format(svc),
                                     'cgroup.procs')
                if not os.path.exists(_path):
                    _path = glob.glob(os.path.join(path, 'system-*.slice',
                                                   "{}.service".format(svc),
                                                   'cgroup.procs'))
                    if not _path or not os.path.exists(_path[0]):
                        continue

                    _path = _path[0]

                pids = []
                with open(_path) as fd:
                    for line in fd:
                        pids.append(int(line))

                for line in CLIHelper().ps():
                    for pid in pids:
                        if " {} ".format(pid) in line:
                            ps_filtered.append(line)

        return ps_filtered

    @property
    def processes(self):
        """
        Identify running processes from ps that are associated with identified
        systemd services. The same search pattern used for identifying systemd
        services is used here.

        Returns a dictionary of process names along with the number of each.
        """
        if self._processes:
            return self._processes

        for line in self.service_filtered_ps:
            for expr in self.service_exprs:
                """
                look for running process with this name.
                We need to account for different types of process binary e.g.

                /snap/<name>/1830/<svc>
                /usr/bin/<svc>

                and filter e.g.

                /var/lib/<svc> and /var/log/<svc>
                """
                cmd = self.get_process_cmd_from_line(line, expr)
                if cmd:
                    if cmd not in self._processes:
                        self._processes[cmd] = 0

                    self._processes[cmd] += 1

        return self._processes

    @property
    def service_info(self):
        """Return a dictionary of systemd services grouped by state. """
        info = {}
        for svc, state in sorted_dict(self.services).items():
            if state not in info:
                info[state] = []

            info[state].append(svc)

        return info

    @property
    def process_info(self):
        """Return a list of processes associated with services. """
        return ["{} ({})".format(name, count)
                for name, count in sorted_dict(self.processes).items()]


class DPKGVersionCompare(object):

    def __init__(self, a):
        self.a = a

    def _exec(self, op, b):
        try:
            subprocess.check_call(['dpkg', '--compare-versions',
                                   self.a, op, b])
        except subprocess.CalledProcessError as se:
            if se.returncode == 1:
                return False

            raise se

        return True

    def __eq__(self, b):
        return self._exec('eq', b)

    def __lt__(self, b):
        return not self._exec('ge', b)

    def __gt__(self, b):
        return not self._exec('le', b)

    def __le__(self, b):
        return self._exec('le', b)

    def __ge__(self, b):
        return self._exec('ge', b)


def dict_to_formatted_str_list(f):
    """
    Convert dict returned by function f to a list of strings of format
    '<name> <version>'.
    """
    def _dict_to_formatted_str_list(*args, **kwargs):
        ret = f(*args, **kwargs)
        if not ret:
            return []

        return ["{} {}".format(*e) for e in ret.items()]

    return _dict_to_formatted_str_list


class PackageChecksBase(object):

    def get_version(self, pkg):
        """
        Return version of package.
        """
        raise NotImplementedError

    def is_installed(self, pkg):
        """ Returns True if pkg is installed """
        raise NotImplementedError

    @property
    @dict_to_formatted_str_list
    def all_formatted(self):
        """
        Returns list of packages. Each entry in the list is an item
        looking like "<pkgname> <pkgver>".
        """
        return self.all

    @property
    def all(self):
        """ Returns results matched for all expressions. """
        raise NotImplementedError

    @property
    def core(self):
        """ Returns results matched for core expressions. """
        raise NotImplementedError


class DockerImageChecksBase(PackageChecksBase):

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
            return

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
        self.all
        return self._core_images


class APTPackageChecksBase(PackageChecksBase):

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

    def is_installed(self, pkg):
        if pkg in self.all:
            return True

        dpkg_l = self.cli.dpkg_l()
        if not dpkg_l:
            return

        cexpr = re.compile(r"^.i\s+{}\s+.+".format(pkg))
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
        self.all
        return self._core_packages


class SnapPackageChecksBase(PackageChecksBase):

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
        self._match_expr_template = \
            r"^ii\s+(python3?-)?({}[0-9a-z\-]*)\s+(\S+)\s+.+"
        self.snap_list_all = CLIHelper().snap_list_all()

    def get_version(self, snap):
        """ Return version of package. """
        if snap in self._all:
            return self._all[snap]

        if self.snap_list_all:
            for line in self.snap_list_all:
                name, version = self._get_snap_info_from_line(line, snap)
                if name:
                    return version

    def _get_snap_info_from_line(self, line, snap):
        """Returns snap name and version if found in line.

        @return: tuple of (name, version) or None, None
        """
        ret = re.compile(r"^({})\s+([\S]+)\s+.+".format(snap)).match(line)
        if ret:
            return (ret[1], ret[2])

        return None, None

    @property
    def _all(self):
        if self._all_snaps:
            return self._all_snaps

        if not self.snap_list_all:
            return {}

        _core = {}
        _other = {}
        all_exprs = self.core_snap_exprs + self.other_snap_exprs
        for line in self.snap_list_all:
            for snap in all_exprs:
                name, version = self._get_snap_info_from_line(line, snap)
                if not name:
                    continue

                # only show latest version installed
                if snap in self.core_snap_exprs:
                    if name in _core:
                        if version > _core[name]:
                            _core[name] = version
                    else:
                        _core[name] = version
                else:
                    if name in _other:
                        if version > _other[name]:
                            _other[name] = version
                    else:
                        _other[name] = version

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
    def core(self):
        """
        Only return results that matched from the "core" set of snaps.
        """
        if self._core_snaps:
            return self._core_snaps

        if self._other_snaps:
            return {}

        # go fetch
        self.all
        return self._core_snaps
