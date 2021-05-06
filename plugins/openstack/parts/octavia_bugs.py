#!/usr/bin/python3

import glob
import os
import subprocess
import tempfile

import git

from git.exc import GitCommandError
from gitdb.exc import BadName

from common import (
    constants,
    cli_helpers,
    utils,
)
from common.known_bugs_utils import (
    add_known_bug,
)


GIT_NEUTRON_OVS = "https://opendev.org/openstack/charm-neutron-openvswitch"
JUJU_LIB_PATH = os.path.join(constants.DATA_ROOT, "var/lib/juju")


def _find_neutron_openvswitch_charmdir():
    for d in glob.glob(os.path.join(JUJU_LIB_PATH, "agents",
                                    "unit-neutron-openvswitch-*",
                                    "charm")):
        return d


def _find_systemd_version():
    dpkg_l = cli_helpers.get_dpkg_l()

    for line in dpkg_l:
        if not line.startswith('ii '):
            continue

        tokens = line.split()
        if tokens[1] != "systemd":
            continue

        return tokens[2]


def _clone_neutron_openvswitch_charm(dst_dir):

    repo = git.Repo.clone_from(GIT_NEUTRON_OVS,
                               os.path.join(dst_dir, "neutron-openvswitch"))
    return repo


@utils.suppress(GitCommandError)
def detect_lp1906280():
    neutron_ovs_charmdir = _find_neutron_openvswitch_charmdir()

    if not neutron_ovs_charmdir:
        # neutron-openvswitch was not found in this sosreport.
        return None

    version_file = os.path.join(neutron_ovs_charmdir, "version")
    if not version_file:
        # version file not found.
        return None

    with open(version_file, 'r') as f:
        commit_id = f.read()

    with tempfile.TemporaryDirectory() as tmpdir:
        repo = _clone_neutron_openvswitch_charm(tmpdir)
        try:
            repo.commit(commit_id)
        except BadName:
            # this happens when charm was built with non-upstreamed commits.
            return

        output = repo.git.branch('-r', '--contains', commit_id)

    branches = [line.strip() for line in output.split('\n')]

    try:
        branches.remove('origin/HEAD -> origin/master')
        branches.remove('origin/master')
    except ValueError:
        pass

    branches.sort()
    oldest_branch = branches.pop(0)

    systemd_version = _find_systemd_version()

    exit_code = subprocess.call(['dpkg', '--compare-versions', systemd_version,
                                 'ge', '237-3ubuntu10.43'])
    if exit_code == 0 and not oldest_branch > 'origin/stable/21.01':
        add_known_bug(1906280)


if __name__ == "__main__":
    detect_lp1906280()
