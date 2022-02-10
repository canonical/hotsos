# Copyright 2017-2021 Canonical Ltd
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import collections
import glob
import itertools
import json
import os
import pyudev
import random
import re
import socket
import subprocess
import sys
import time
import uuid
import functools

from contextlib import contextmanager
from datetime import datetime

from charmhelpers.core import hookenv
from charmhelpers.core import templating
from charmhelpers.core.host import (
    chownr,
    cmp_pkgrevno,
    lsb_release,
    mkdir,
    owner,
    service_restart,
    service_start,
    service_stop,
    CompareHostReleases,
    write_file,
    is_container,
)
from charmhelpers.core.hookenv import (
    cached,
    config,
    log,
    status_set,
    DEBUG,
    ERROR,
    WARNING,
    storage_get,
    storage_list,
)
from charmhelpers.fetch import (
    add_source,
    apt_install,
    apt_purge,
    apt_update,
    filter_missing_packages,
    get_installed_version
)
from charmhelpers.contrib.storage.linux.ceph import (
    get_mon_map,
    monitor_key_set,
    monitor_key_exists,
    monitor_key_get,
)
from charmhelpers.contrib.storage.linux.utils import (
    is_block_device,
    is_device_mounted,
)
from charmhelpers.contrib.openstack.utils import (
    get_os_codename_install_source,
)
from charmhelpers.contrib.storage.linux import lvm
from charmhelpers.core.unitdata import kv

CEPH_BASE_DIR = os.path.join(os.sep, 'var', 'lib', 'ceph')
OSD_BASE_DIR = os.path.join(CEPH_BASE_DIR, 'osd')
HDPARM_FILE = os.path.join(os.sep, 'etc', 'hdparm.conf')

LEADER = 'leader'
PEON = 'peon'
QUORUM = [LEADER, PEON]

PACKAGES = ['ceph', 'gdisk',
            'radosgw', 'xfsprogs',
            'lvm2', 'parted', 'smartmontools']

REMOVE_PACKAGES = []
CHRONY_PACKAGE = 'chrony'

CEPH_KEY_MANAGER = 'ceph'
VAULT_KEY_MANAGER = 'vault'
KEY_MANAGERS = [
    CEPH_KEY_MANAGER,
    VAULT_KEY_MANAGER,
]

LinkSpeed = {
    "BASE_10": 10,
    "BASE_100": 100,
    "BASE_1000": 1000,
    "GBASE_10": 10000,
    "GBASE_40": 40000,
    "GBASE_100": 100000,
    "UNKNOWN": None
}

# Mapping of adapter speed to sysctl settings
NETWORK_ADAPTER_SYSCTLS = {
    # 10Gb
    LinkSpeed["GBASE_10"]: {
        'net.core.rmem_default': 524287,
        'net.core.wmem_default': 524287,
        'net.core.rmem_max': 524287,
        'net.core.wmem_max': 524287,
        'net.core.optmem_max': 524287,
        'net.core.netdev_max_backlog': 300000,
        'net.ipv4.tcp_rmem': '10000000 10000000 10000000',
        'net.ipv4.tcp_wmem': '10000000 10000000 10000000',
        'net.ipv4.tcp_mem': '10000000 10000000 10000000'
    },
    # Mellanox 10/40Gb
    LinkSpeed["GBASE_40"]: {
        'net.ipv4.tcp_timestamps': 0,
        'net.ipv4.tcp_sack': 1,
        'net.core.netdev_max_backlog': 250000,
        'net.core.rmem_max': 4194304,
        'net.core.wmem_max': 4194304,
        'net.core.rmem_default': 4194304,
        'net.core.wmem_default': 4194304,
        'net.core.optmem_max': 4194304,
        'net.ipv4.tcp_rmem': '4096 87380 4194304',
        'net.ipv4.tcp_wmem': '4096 65536 4194304',
        'net.ipv4.tcp_low_latency': 1,
        'net.ipv4.tcp_adv_win_scale': 1
    }
}


class Partition(object):
    def __init__(self, name, number, size, start, end, sectors, uuid):
        """A block device partition.

        :param name: Name of block device
        :param number: Partition number
        :param size: Capacity of the device
        :param start: Starting block
        :param end: Ending block
        :param sectors: Number of blocks
        :param uuid: UUID of the partition
        """
        self.name = name,
        self.number = number
        self.size = size
        self.start = start
        self.end = end
        self.sectors = sectors
        self.uuid = uuid

    def __str__(self):
        return "number: {} start: {} end: {} sectors: {} size: {} " \
               "name: {} uuid: {}".format(self.number, self.start,
                                          self.end,
                                          self.sectors, self.size,
                                          self.name, self.uuid)

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.__dict__ == other.__dict__
        return False

    def __ne__(self, other):
        return not self.__eq__(other)


def unmounted_disks():
    """List of unmounted block devices on the current host."""
    disks = []
    context = pyudev.Context()
    for device in context.list_devices(DEVTYPE='disk'):
        if device['SUBSYSTEM'] == 'block':
            if device.device_node is None:
                continue

            matched = False
            for block_type in [u'dm-', u'loop', u'ram', u'nbd']:
                if block_type in device.device_node:
                    matched = True
            if matched:
                continue

            disks.append(device.device_node)
    log("Found disks: {}".format(disks))
    return [disk for disk in disks if not is_device_mounted(disk)]


def save_sysctls(sysctl_dict, save_location):
    """Persist the sysctls to the hard drive.

    :param sysctl_dict: dict
    :param save_location: path to save the settings to
    :raises: IOError if anything goes wrong with writing.
    """
    try:
        # Persist the settings for reboots
        with open(save_location, "w") as fd:
            for key, value in sysctl_dict.items():
                fd.write("{}={}\n".format(key, value))

    except IOError as e:
        log("Unable to persist sysctl settings to {}. Error {}".format(
            save_location, e), level=ERROR)
        raise


def tune_nic(network_interface):
    """This will set optimal sysctls for the particular network adapter.

    :param network_interface: string The network adapter name.
    """
    speed = get_link_speed(network_interface)
    if speed in NETWORK_ADAPTER_SYSCTLS:
        status_set('maintenance', 'Tuning device {}'.format(
            network_interface))
        sysctl_file = os.path.join(
            os.sep,
            'etc',
            'sysctl.d',
            '51-ceph-osd-charm-{}.conf'.format(network_interface))
        try:
            log("Saving sysctl_file: {} values: {}".format(
                sysctl_file, NETWORK_ADAPTER_SYSCTLS[speed]),
                level=DEBUG)
            save_sysctls(sysctl_dict=NETWORK_ADAPTER_SYSCTLS[speed],
                         save_location=sysctl_file)
        except IOError as e:
            log("Write to /etc/sysctl.d/51-ceph-osd-charm-{} "
                "failed. {}".format(network_interface, e),
                level=ERROR)

        try:
            # Apply the settings
            log("Applying sysctl settings", level=DEBUG)
            subprocess.check_output(["sysctl", "-p", sysctl_file])
        except subprocess.CalledProcessError as err:
            log('sysctl -p {} failed with error {}'.format(sysctl_file,
                                                           err.output),
                level=ERROR)
    else:
        log("No settings found for network adapter: {}".format(
            network_interface), level=DEBUG)


def get_link_speed(network_interface):
    """This will find the link speed for a given network device. Returns None
    if an error occurs.
    :param network_interface: string The network adapter interface.
    :returns: LinkSpeed
    """
    speed_path = os.path.join(os.sep, 'sys', 'class', 'net',
                              network_interface, 'speed')
    # I'm not sure where else we'd check if this doesn't exist
    if not os.path.exists(speed_path):
        return LinkSpeed["UNKNOWN"]

    try:
        with open(speed_path, 'r') as sysfs:
            nic_speed = sysfs.readlines()

            # Did we actually read anything?
            if not nic_speed:
                return LinkSpeed["UNKNOWN"]

            # Try to find a sysctl match for this particular speed
            for name, speed in LinkSpeed.items():
                if speed == int(nic_speed[0].strip()):
                    return speed
            # Default to UNKNOWN if we can't find a match
            return LinkSpeed["UNKNOWN"]
    except IOError as e:
        log("Unable to open {path} because of error: {error}".format(
            path=speed_path,
            error=e), level='error')
        return LinkSpeed["UNKNOWN"]


def persist_settings(settings_dict):
    # Write all settings to /etc/hdparm.conf
    """This will persist the hard drive settings to the /etc/hdparm.conf file

    The settings_dict should be in the form of {"uuid": {"key":"value"}}

    :param settings_dict: dict of settings to save
    """
    if not settings_dict:
        return

    try:
        templating.render(source='hdparm.conf', target=HDPARM_FILE,
                          context=settings_dict)
    except IOError as err:
        log("Unable to open {path} because of error: {error}".format(
            path=HDPARM_FILE, error=err), level=ERROR)
    except Exception as e:
        # The templating.render can raise a jinja2 exception if the
        # template is not found. Rather than polluting the import
        # space of this charm, simply catch Exception
        log('Unable to render {path} due to error: {error}'.format(
            path=HDPARM_FILE, error=e), level=ERROR)


def set_max_sectors_kb(dev_name, max_sectors_size):
    """This function sets the max_sectors_kb size of a given block device.

    :param dev_name: Name of the block device to query
    :param max_sectors_size: int of the max_sectors_size to save
    """
    max_sectors_kb_path = os.path.join('sys', 'block', dev_name, 'queue',
                                       'max_sectors_kb')
    try:
        with open(max_sectors_kb_path, 'w') as f:
            f.write(max_sectors_size)
    except IOError as e:
        log('Failed to write max_sectors_kb to {}. Error: {}'.format(
            max_sectors_kb_path, e), level=ERROR)


def get_max_sectors_kb(dev_name):
    """This function gets the max_sectors_kb size of a given block device.

    :param dev_name: Name of the block device to query
    :returns: int which is either the max_sectors_kb or 0 on error.
    """
    max_sectors_kb_path = os.path.join('sys', 'block', dev_name, 'queue',
                                       'max_sectors_kb')

    # Read in what Linux has set by default
    if os.path.exists(max_sectors_kb_path):
        try:
            with open(max_sectors_kb_path, 'r') as f:
                max_sectors_kb = f.read().strip()
                return int(max_sectors_kb)
        except IOError as e:
            log('Failed to read max_sectors_kb to {}. Error: {}'.format(
                max_sectors_kb_path, e), level=ERROR)
            # Bail.
            return 0
    return 0


def get_max_hw_sectors_kb(dev_name):
    """This function gets the max_hw_sectors_kb for a given block device.

    :param dev_name: Name of the block device to query
    :returns: int which is either the max_hw_sectors_kb or 0 on error.
    """
    max_hw_sectors_kb_path = os.path.join('sys', 'block', dev_name, 'queue',
                                          'max_hw_sectors_kb')
    # Read in what the hardware supports
    if os.path.exists(max_hw_sectors_kb_path):
        try:
            with open(max_hw_sectors_kb_path, 'r') as f:
                max_hw_sectors_kb = f.read().strip()
                return int(max_hw_sectors_kb)
        except IOError as e:
            log('Failed to read max_hw_sectors_kb to {}. Error: {}'.format(
                max_hw_sectors_kb_path, e), level=ERROR)
            return 0
    return 0


def set_hdd_read_ahead(dev_name, read_ahead_sectors=256):
    """This function sets the hard drive read ahead.

    :param dev_name: Name of the block device to set read ahead on.
    :param read_ahead_sectors: int How many sectors to read ahead.
    """
    try:
        # Set the read ahead sectors to 256
        log('Setting read ahead to {} for device {}'.format(
            read_ahead_sectors,
            dev_name))
        subprocess.check_output(['hdparm',
                                 '-a{}'.format(read_ahead_sectors),
                                 dev_name])
    except subprocess.CalledProcessError as e:
        log('hdparm failed with error: {}'.format(e.output),
            level=ERROR)


def get_block_uuid(block_dev):
    """This queries blkid to get the uuid for a block device.

    :param block_dev: Name of the block device to query.
    :returns: The UUID of the device or None on Error.
    """
    try:
        block_info = str(subprocess
                         .check_output(['blkid', '-o', 'export', block_dev])
                         .decode('UTF-8'))
        for tag in block_info.split('\n'):
            parts = tag.split('=')
            if parts[0] == 'UUID':
                return parts[1]
        return None
    except subprocess.CalledProcessError as err:
        log('get_block_uuid failed with error: {}'.format(err.output),
            level=ERROR)
        return None


def check_max_sectors(save_settings_dict,
                      block_dev,
                      uuid):
    """Tune the max_hw_sectors if needed.

    make sure that /sys/.../max_sectors_kb matches max_hw_sectors_kb or at
    least 1MB for spinning disks
    If the box has a RAID card with cache this could go much bigger.

    :param save_settings_dict: The dict used to persist settings
    :param block_dev: A block device name: Example: /dev/sda
    :param uuid: The uuid of the block device
    """
    dev_name = None
    path_parts = os.path.split(block_dev)
    if len(path_parts) == 2:
        dev_name = path_parts[1]
    else:
        log('Unable to determine the block device name from path: {}'.format(
            block_dev))
        # Play it safe and bail
        return
    max_sectors_kb = get_max_sectors_kb(dev_name=dev_name)
    max_hw_sectors_kb = get_max_hw_sectors_kb(dev_name=dev_name)

    if max_sectors_kb < max_hw_sectors_kb:
        # OK we have a situation where the hardware supports more than Linux is
        # currently requesting
        config_max_sectors_kb = hookenv.config('max-sectors-kb')
        if config_max_sectors_kb < max_hw_sectors_kb:
            # Set the max_sectors_kb to the config.yaml value if it is less
            # than the max_hw_sectors_kb
            log('Setting max_sectors_kb for device {} to {}'.format(
                dev_name, config_max_sectors_kb))
            save_settings_dict[
                "drive_settings"][uuid][
                "read_ahead_sect"] = config_max_sectors_kb
            set_max_sectors_kb(dev_name=dev_name,
                               max_sectors_size=config_max_sectors_kb)
        else:
            # Set to the max_hw_sectors_kb
            log('Setting max_sectors_kb for device {} to {}'.format(
                dev_name, max_hw_sectors_kb))
            save_settings_dict[
                "drive_settings"][uuid]['read_ahead_sect'] = max_hw_sectors_kb
            set_max_sectors_kb(dev_name=dev_name,
                               max_sectors_size=max_hw_sectors_kb)
    else:
        log('max_sectors_kb match max_hw_sectors_kb. No change needed for '
            'device: {}'.format(block_dev))


def tune_dev(block_dev):
    """Try to make some intelligent decisions with HDD tuning. Future work will
    include optimizing SSDs.

    This function will change the read ahead sectors and the max write
    sectors for each block device.

    :param block_dev: A block device name: Example: /dev/sda
    """
    uuid = get_block_uuid(block_dev)
    if uuid is None:
        log('block device {} uuid is None. Unable to save to '
            'hdparm.conf'.format(block_dev), level=DEBUG)
        return
    save_settings_dict = {}
    log('Tuning device {}'.format(block_dev))
    status_set('maintenance', 'Tuning device {}'.format(block_dev))
    set_hdd_read_ahead(block_dev)
    save_settings_dict["drive_settings"] = {}
    save_settings_dict["drive_settings"][uuid] = {}
    save_settings_dict["drive_settings"][uuid]['read_ahead_sect'] = 256

    check_max_sectors(block_dev=block_dev,
                      save_settings_dict=save_settings_dict,
                      uuid=uuid)

    persist_settings(settings_dict=save_settings_dict)
    status_set('maintenance', 'Finished tuning device {}'.format(block_dev))


def ceph_user():
    return 'ceph'


class CrushLocation(object):
    def __init__(self, identifier, name, osd="", host="", chassis="",
                 rack="", row="", pdu="", pod="", room="",
                 datacenter="", zone="", region="", root=""):
        self.identifier = identifier
        self.name = name
        self.osd = osd
        self.host = host
        self.chassis = chassis
        self.rack = rack
        self.row = row
        self.pdu = pdu
        self.pod = pod
        self.room = room
        self.datacenter = datacenter
        self.zone = zone
        self.region = region
        self.root = root

    def __str__(self):
        return "name: {} id: {} osd: {} host: {} chassis: {} rack: {} " \
               "row: {} pdu: {} pod: {} room: {} datacenter: {} zone: {} " \
               "region: {} root: {}".format(self.name, self.identifier,
                                            self.osd, self.host, self.chassis,
                                            self.rack, self.row, self.pdu,
                                            self.pod, self.room,
                                            self.datacenter, self.zone,
                                            self.region, self.root)

    def __eq__(self, other):
        return not self.name < other.name and not other.name < self.name

    def __ne__(self, other):
        return self.name < other.name or other.name < self.name

    def __gt__(self, other):
        return self.name > other.name

    def __ge__(self, other):
        return not self.name < other.name

    def __le__(self, other):
        return self.name < other.name


def get_osd_weight(osd_id):
    """Returns the weight of the specified OSD.

    :returns: Float
    :raises: ValueError if the monmap fails to parse.
    :raises: CalledProcessError if our Ceph command fails.
    """
    try:
        tree = str(subprocess
                   .check_output(['ceph', 'osd', 'tree', '--format=json'])
                   .decode('UTF-8'))
        try:
            json_tree = json.loads(tree)
            # Make sure children are present in the JSON
            if not json_tree['nodes']:
                return None
            for device in json_tree['nodes']:
                if device['type'] == 'osd' and device['name'] == osd_id:
                    return device['crush_weight']
        except ValueError as v:
            log("Unable to parse ceph tree json: {}. Error: {}".format(
                tree, v))
            raise
    except subprocess.CalledProcessError as e:
        log("ceph osd tree command failed with message: {}".format(
            e))
        raise


def _filter_nodes_and_set_attributes(node, node_lookup_map, lookup_type):
    """Get all nodes of the desired type, with all their attributes.

    These attributes can be direct or inherited from ancestors.
    """
    attribute_dict = {node['type']: node['name']}
    if node['type'] == lookup_type:
        attribute_dict['name'] = node['name']
        attribute_dict['identifier'] = node['id']
        return [attribute_dict]
    elif not node.get('children'):
        return [attribute_dict]
    else:
        descendant_attribute_dicts = [
            _filter_nodes_and_set_attributes(node_lookup_map[node_id],
                                             node_lookup_map, lookup_type)
            for node_id in node.get('children', [])
        ]
        return [dict(attribute_dict, **descendant_attribute_dict)
                for descendant_attribute_dict
                in itertools.chain.from_iterable(descendant_attribute_dicts)]


def _flatten_roots(nodes, lookup_type='host'):
    """Get a flattened list of nodes of the desired type.

    :param nodes: list of nodes defined as a dictionary of attributes and
                  children
    :type nodes: List[Dict[int, Any]]
    :param lookup_type: type of searched node
    :type lookup_type: str
    :returns: flattened list of nodes
    :rtype: List[Dict[str, Any]]
    """
    lookup_map = {node['id']: node for node in nodes}
    root_attributes_dicts = [_filter_nodes_and_set_attributes(node, lookup_map,
                                                              lookup_type)
                             for node in nodes if node['type'] == 'root']
    # get a flattened list of roots.
    return list(itertools.chain.from_iterable(root_attributes_dicts))


def get_osd_tree(service):
    """Returns the current OSD map in JSON.

    :returns: List.
    :rtype: List[CrushLocation]
    :raises: ValueError if the monmap fails to parse.
             Also raises CalledProcessError if our Ceph command fails
    """
    try:
        tree = str(subprocess
                   .check_output(['ceph', '--id', service,
                                  'osd', 'tree', '--format=json'])
                   .decode('UTF-8'))
        try:
            json_tree = json.loads(tree)
            roots = _flatten_roots(json_tree["nodes"])
            return [CrushLocation(**host) for host in roots]
        except ValueError as v:
            log("Unable to parse ceph tree json: {}. Error: {}".format(
                tree, v))
            raise
    except subprocess.CalledProcessError as e:
        log("ceph osd tree command failed with message: {}".format(e))
        raise


def _get_child_dirs(path):
    """Returns a list of directory names in the specified path.

    :param path: a full path listing of the parent directory to return child
                 directory names
    :returns: list. A list of child directories under the parent directory
    :raises: ValueError if the specified path does not exist or is not a
             directory,
             OSError if an error occurs reading the directory listing
    """
    if not os.path.exists(path):
        raise ValueError('Specified path "%s" does not exist' % path)
    if not os.path.isdir(path):
        raise ValueError('Specified path "%s" is not a directory' % path)

    files_in_dir = [os.path.join(path, f) for f in os.listdir(path)]
    return list(filter(os.path.isdir, files_in_dir))


def _get_osd_num_from_dirname(dirname):
    """Parses the dirname and returns the OSD id.

    Parses a string in the form of 'ceph-{osd#}' and returns the OSD number
    from the directory name.

    :param dirname: the directory name to return the OSD number from
    :return int: the OSD number the directory name corresponds to
    :raises ValueError: if the OSD number cannot be parsed from the provided
                        directory name.
    """
    match = re.search(r'ceph-(?P<osd_id>\d+)', dirname)
    if not match:
        raise ValueError("dirname not in correct format: {}".format(dirname))

    return match.group('osd_id')


def get_local_osd_ids():
    """This will list the /var/lib/ceph/osd/* directories and try
    to split the ID off of the directory name and return it in
    a list.

    :returns: list. A list of OSD identifiers
    :raises: OSError if something goes wrong with listing the directory.
    """
    osd_ids = []
    osd_path = os.path.join(os.sep, 'var', 'lib', 'ceph', 'osd')
    if os.path.exists(osd_path):
        try:
            dirs = os.listdir(osd_path)
            for osd_dir in dirs:
                osd_id = osd_dir.split('-')[1]
                if (_is_int(osd_id) and
                        filesystem_mounted(os.path.join(
                            os.sep, osd_path, osd_dir))):
                    osd_ids.append(osd_id)
        except OSError:
            raise
    return osd_ids


def get_local_mon_ids():
    """This will list the /var/lib/ceph/mon/* directories and try
    to split the ID off of the directory name and return it in
    a list.

    :returns: list. A list of monitor identifiers
    :raises: OSError if something goes wrong with listing the directory.
    """
    mon_ids = []
    mon_path = os.path.join(os.sep, 'var', 'lib', 'ceph', 'mon')
    if os.path.exists(mon_path):
        try:
            dirs = os.listdir(mon_path)
            for mon_dir in dirs:
                # Basically this takes everything after ceph- as the monitor ID
                match = re.search('ceph-(?P<mon_id>.*)', mon_dir)
                if match:
                    mon_ids.append(match.group('mon_id'))
        except OSError:
            raise
    return mon_ids


def _is_int(v):
    """Return True if the object v can be turned into an integer."""
    try:
        int(v)
        return True
    except ValueError:
        return False


def get_version():
    """Derive Ceph release from an installed package."""
    import apt_pkg as apt

    package = "ceph"

    current_ver = get_installed_version(package)
    if not current_ver:
        # package is known, but no version is currently installed.
        e = 'Could not determine version of uninstalled package: %s' % package
        error_out(e)

    vers = apt.upstream_version(current_ver.ver_str)

    # x.y match only for 20XX.X
    # and ignore patch level for other packages
    match = re.match(r'^(\d+)\.(\d+)', vers)

    if match:
        vers = match.group(0)
    return float(vers)


def error_out(msg):
    log("FATAL ERROR: {}".format(msg),
        level=ERROR)
    sys.exit(1)


def is_quorum():
    asok = "/var/run/ceph/ceph-mon.{}.asok".format(socket.gethostname())
    cmd = [
        "sudo",
        "-u",
        ceph_user(),
        "ceph",
        "--admin-daemon",
        asok,
        "mon_status"
    ]
    if os.path.exists(asok):
        try:
            result = json.loads(str(subprocess
                                    .check_output(cmd)
                                    .decode('UTF-8')))
        except subprocess.CalledProcessError:
            return False
        except ValueError:
            # Non JSON response from mon_status
            return False
        if result['state'] in QUORUM:
            return True
        else:
            return False
    else:
        return False


def is_leader():
    asok = "/var/run/ceph/ceph-mon.{}.asok".format(socket.gethostname())
    cmd = [
        "sudo",
        "-u",
        ceph_user(),
        "ceph",
        "--admin-daemon",
        asok,
        "mon_status"
    ]
    if os.path.exists(asok):
        try:
            result = json.loads(str(subprocess
                                    .check_output(cmd)
                                    .decode('UTF-8')))
        except subprocess.CalledProcessError:
            return False
        except ValueError:
            # Non JSON response from mon_status
            return False
        if result['state'] == LEADER:
            return True
        else:
            return False
    else:
        return False


def manager_available():
    # if manager daemon isn't on this release, just say it is Fine
    if cmp_pkgrevno('ceph', '11.0.0') < 0:
        return True
    cmd = ["sudo", "-u", "ceph", "ceph", "mgr", "dump", "-f", "json"]
    try:
        result = json.loads(subprocess.check_output(cmd).decode('UTF-8'))
        return result['available']
    except subprocess.CalledProcessError as e:
        log("'{}' failed: {}".format(" ".join(cmd), str(e)))
        return False
    except Exception:
        return False


def wait_for_quorum():
    while not is_quorum():
        log("Waiting for quorum to be reached")
        time.sleep(3)


def wait_for_manager():
    while not manager_available():
        log("Waiting for manager to be available")
        time.sleep(5)


def add_bootstrap_hint(peer):
    asok = "/var/run/ceph/ceph-mon.{}.asok".format(socket.gethostname())
    cmd = [
        "sudo",
        "-u",
        ceph_user(),
        "ceph",
        "--admin-daemon",
        asok,
        "add_bootstrap_peer_hint",
        peer
    ]
    if os.path.exists(asok):
        # Ignore any errors for this call
        subprocess.call(cmd)


DISK_FORMATS = [
    'xfs',
    'ext4',
    'btrfs'
]

CEPH_PARTITIONS = [
    '89C57F98-2FE5-4DC0-89C1-5EC00CEFF2BE',  # Ceph encrypted disk in creation
    '45B0969E-9B03-4F30-B4C6-5EC00CEFF106',  # Ceph encrypted journal
    '4FBD7E29-9D25-41B8-AFD0-5EC00CEFF05D',  # Ceph encrypted OSD data
    '4FBD7E29-9D25-41B8-AFD0-062C0CEFF05D',  # Ceph OSD data
    '45B0969E-9B03-4F30-B4C6-B4B80CEFF106',  # Ceph OSD journal
    '89C57F98-2FE5-4DC0-89C1-F3AD0CEFF2BE',  # Ceph disk in creation
]


def get_partition_list(dev):
    """Lists the partitions of a block device.

    :param dev: Path to a block device. ex: /dev/sda
    :returns: Returns a list of Partition objects.
    :raises: CalledProcessException if lsblk fails
    """
    partitions_list = []
    try:
        partitions = get_partitions(dev)
        # For each line of output
        for partition in partitions:
            parts = partition.split()
            try:
                partitions_list.append(
                    Partition(number=parts[0],
                              start=parts[1],
                              end=parts[2],
                              sectors=parts[3],
                              size=parts[4],
                              name=parts[5],
                              uuid=parts[6])
                )
            except IndexError:
                partitions_list.append(
                    Partition(number=parts[0],
                              start=parts[1],
                              end=parts[2],
                              sectors=parts[3],
                              size=parts[4],
                              name="",
                              uuid=parts[5])
                )

        return partitions_list
    except subprocess.CalledProcessError:
        raise


def is_pristine_disk(dev):
    """
    Read first 2048 bytes (LBA 0 - 3) of block device to determine whether it
    is actually all zeros and safe for us to use.

    Existing partitioning tools does not discern between a failure to read from
    block device, failure to understand a partition table and the fact that a
    block device has no partition table.  Since we need to be positive about
    which is which we need to read the device directly and confirm ourselves.

    :param dev: Path to block device
    :type dev: str
    :returns: True all 2048 bytes == 0x0, False if not
    :rtype: bool
    """
    want_bytes = 2048

    try:
        f = open(dev, 'rb')
    except OSError as e:
        log(e)
        return False

    data = f.read(want_bytes)
    read_bytes = len(data)
    if read_bytes != want_bytes:
        log('{}: short read, got {} bytes expected {}.'
            .format(dev, read_bytes, want_bytes), level=WARNING)
        return False

    return all(byte == 0x0 for byte in data)


def is_osd_disk(dev):
    db = kv()
    osd_devices = db.get('osd-devices', [])
    if dev in osd_devices:
        log('Device {} already processed by charm,'
            ' skipping'.format(dev))
        return True

    partitions = get_partition_list(dev)
    for partition in partitions:
        try:
            info = str(subprocess
                       .check_output(['sgdisk', '-i', partition.number, dev])
                       .decode('UTF-8'))
            info = info.split("\n")  # IGNORE:E1103
            for line in info:
                for ptype in CEPH_PARTITIONS:
                    sig = 'Partition GUID code: {}'.format(ptype)
                    if line.startswith(sig):
                        return True
        except subprocess.CalledProcessError as e:
            log("sgdisk inspection of partition {} on {} failed with "
                "error: {}. Skipping".format(partition.minor, dev, e),
                level=ERROR)
    return False


def start_osds(devices):
    # Scan for Ceph block devices
    rescan_osd_devices()
    if (cmp_pkgrevno('ceph', '0.56.6') >= 0 and
            cmp_pkgrevno('ceph', '14.2.0') < 0):
        # Use ceph-disk activate for directory based OSD's
        for dev_or_path in devices:
            if os.path.exists(dev_or_path) and os.path.isdir(dev_or_path):
                subprocess.check_call(
                    ['ceph-disk', 'activate', dev_or_path])


def udevadm_settle():
    cmd = ['udevadm', 'settle']
    subprocess.call(cmd)


def rescan_osd_devices():
    cmd = [
        'udevadm', 'trigger',
        '--subsystem-match=block', '--action=add'
    ]

    subprocess.call(cmd)

    udevadm_settle()


_client_admin_keyring = '/etc/ceph/ceph.client.admin.keyring'


def is_bootstrapped():
    return os.path.exists(
        '/var/lib/ceph/mon/ceph-{}/done'.format(socket.gethostname()))


def wait_for_bootstrap():
    while not is_bootstrapped():
        time.sleep(3)


def generate_monitor_secret():
    cmd = [
        'ceph-authtool',
        '/dev/stdout',
        '--name=mon.',
        '--gen-key'
    ]
    res = str(subprocess.check_output(cmd).decode('UTF-8'))

    return "{}==".format(res.split('=')[1].strip())


# OSD caps taken from ceph-create-keys
_osd_bootstrap_caps = {
    'mon': [
        'allow command osd create ...',
        'allow command osd crush set ...',
        r'allow command auth add * osd allow\ * mon allow\ rwx',
        'allow command mon getmap'
    ]
}

_osd_bootstrap_caps_profile = {
    'mon': [
        'allow profile bootstrap-osd'
    ]
}


def parse_key(raw_key):
    # get-or-create appears to have different output depending
    # on whether its 'get' or 'create'
    # 'create' just returns the key, 'get' is more verbose and
    # needs parsing
    key = None
    if len(raw_key.splitlines()) == 1:
        key = raw_key
    else:
        for element in raw_key.splitlines():
            if 'key' in element:
                return element.split(' = ')[1].strip()  # IGNORE:E1103
    return key


def get_osd_bootstrap_key():
    try:
        # Attempt to get/create a key using the OSD bootstrap profile first
        key = get_named_key('bootstrap-osd',
                            _osd_bootstrap_caps_profile)
    except Exception:
        # If that fails try with the older style permissions
        key = get_named_key('bootstrap-osd',
                            _osd_bootstrap_caps)
    return key


_radosgw_keyring = "/etc/ceph/keyring.rados.gateway"


def import_radosgw_key(key):
    if not os.path.exists(_radosgw_keyring):
        cmd = [
            "sudo",
            "-u",
            ceph_user(),
            'ceph-authtool',
            _radosgw_keyring,
            '--create-keyring',
            '--name=client.radosgw.gateway',
            '--add-key={}'.format(key)
        ]
        subprocess.check_call(cmd)


# OSD caps taken from ceph-create-keys
_radosgw_caps = {
    'mon': ['allow rw'],
    'osd': ['allow rwx']
}
_upgrade_caps = {
    'mon': ['allow rwx']
}


def get_radosgw_key(pool_list=None, name=None):
    return get_named_key(name=name or 'radosgw.gateway',
                         caps=_radosgw_caps,
                         pool_list=pool_list)


def get_mds_key(name):
    return create_named_keyring(entity='mds',
                                name=name,
                                caps=mds_caps)


_mds_bootstrap_caps_profile = {
    'mon': [
        'allow profile bootstrap-mds'
    ]
}


def get_mds_bootstrap_key():
    return get_named_key('bootstrap-mds',
                         _mds_bootstrap_caps_profile)


_default_caps = collections.OrderedDict([
    ('mon', ['allow r',
             'allow command "osd blacklist"']),
    ('osd', ['allow rwx']),
])

admin_caps = collections.OrderedDict([
    ('mds', ['allow *']),
    ('mgr', ['allow *']),
    ('mon', ['allow *']),
    ('osd', ['allow *'])
])

mds_caps = collections.OrderedDict([
    ('osd', ['allow *']),
    ('mds', ['allow']),
    ('mon', ['allow rwx']),
])

osd_upgrade_caps = collections.OrderedDict([
    ('mon', ['allow command "config-key"',
             'allow command "osd tree"',
             'allow command "config-key list"',
             'allow command "config-key put"',
             'allow command "config-key get"',
             'allow command "config-key exists"',
             'allow command "osd out"',
             'allow command "osd in"',
             'allow command "osd rm"',
             'allow command "auth del"',
             ])
])

rbd_mirror_caps = collections.OrderedDict([
    ('mon', ['profile rbd; allow r']),
    ('osd', ['profile rbd']),
    ('mgr', ['allow r']),
])


def get_rbd_mirror_key(name):
    return get_named_key(name=name, caps=rbd_mirror_caps)


def create_named_keyring(entity, name, caps=None):
    caps = caps or _default_caps
    cmd = [
        "sudo",
        "-u",
        ceph_user(),
        'ceph',
        '--name', 'mon.',
        '--keyring',
        '/var/lib/ceph/mon/ceph-{}/keyring'.format(
            socket.gethostname()
        ),
        'auth', 'get-or-create', '{entity}.{name}'.format(entity=entity,
                                                          name=name),
    ]
    for subsystem, subcaps in caps.items():
        cmd.extend([subsystem, '; '.join(subcaps)])
    log("Calling check_output: {}".format(cmd), level=DEBUG)
    return (parse_key(str(subprocess
                          .check_output(cmd)
                          .decode('UTF-8'))
                      .strip()))  # IGNORE:E1103


def get_upgrade_key():
    return get_named_key('upgrade-osd', _upgrade_caps)


def get_named_key(name, caps=None, pool_list=None):
    """Retrieve a specific named cephx key.

    :param name: String Name of key to get.
    :param pool_list: The list of pools to give access to
    :param caps: dict of cephx capabilities
    :returns: Returns a cephx key
    """
    key_name = 'client.{}'.format(name)
    try:
        # Does the key already exist?
        output = str(subprocess.check_output(
            [
                'sudo',
                '-u', ceph_user(),
                'ceph',
                '--name', 'mon.',
                '--keyring',
                '/var/lib/ceph/mon/ceph-{}/keyring'.format(
                    socket.gethostname()
                ),
                'auth',
                'get',
                key_name,
            ]).decode('UTF-8')).strip()
        return parse_key(output)
    except subprocess.CalledProcessError:
        # Couldn't get the key, time to create it!
        log("Creating new key for {}".format(name), level=DEBUG)
    caps = caps or _default_caps
    cmd = [
        "sudo",
        "-u",
        ceph_user(),
        'ceph',
        '--name', 'mon.',
        '--keyring',
        '/var/lib/ceph/mon/ceph-{}/keyring'.format(
            socket.gethostname()
        ),
        'auth', 'get-or-create', key_name,
    ]
    # Add capabilities
    for subsystem, subcaps in caps.items():
        if subsystem == 'osd':
            if pool_list:
                # This will output a string similar to:
                # "pool=rgw pool=rbd pool=something"
                pools = " ".join(['pool={0}'.format(i) for i in pool_list])
                subcaps[0] = subcaps[0] + " " + pools
        cmd.extend([subsystem, '; '.join(subcaps)])

    log("Calling check_output: {}".format(cmd), level=DEBUG)
    return parse_key(str(subprocess
                         .check_output(cmd)
                         .decode('UTF-8'))
                     .strip())  # IGNORE:E1103


def upgrade_key_caps(key, caps, pool_list=None):
    """Upgrade key to have capabilities caps"""
    if not is_leader():
        # Not the MON leader OR not clustered
        return
    cmd = [
        "sudo", "-u", ceph_user(), 'ceph', 'auth', 'caps', key
    ]
    for subsystem, subcaps in caps.items():
        if subsystem == 'osd':
            if pool_list:
                # This will output a string similar to:
                # "pool=rgw pool=rbd pool=something"
                pools = " ".join(['pool={0}'.format(i) for i in pool_list])
                subcaps[0] = subcaps[0] + " " + pools
        cmd.extend([subsystem, '; '.join(subcaps)])
    subprocess.check_call(cmd)


@cached
def systemd():
    return CompareHostReleases(lsb_release()['DISTRIB_CODENAME']) >= 'vivid'


def use_bluestore():
    """Determine whether bluestore should be used for OSD's

    :returns: whether bluestore disk format should be used
    :rtype: bool"""
    if cmp_pkgrevno('ceph', '12.2.0') < 0:
        return False
    return config('bluestore')


def bootstrap_monitor_cluster(secret):
    """Bootstrap local Ceph mon into the Ceph cluster

    :param secret: cephx secret to use for monitor authentication
    :type secret: str
    :raises: Exception if Ceph mon cannot be bootstrapped
    """
    hostname = socket.gethostname()
    path = '/var/lib/ceph/mon/ceph-{}'.format(hostname)
    done = '{}/done'.format(path)
    if systemd():
        init_marker = '{}/systemd'.format(path)
    else:
        init_marker = '{}/upstart'.format(path)

    keyring = '/var/lib/ceph/tmp/{}.mon.keyring'.format(hostname)

    if os.path.exists(done):
        log('bootstrap_monitor_cluster: mon already initialized.')
    else:
        # Ceph >= 0.61.3 needs this for ceph-mon fs creation
        mkdir('/var/run/ceph', owner=ceph_user(),
              group=ceph_user(), perms=0o755)
        mkdir(path, owner=ceph_user(), group=ceph_user(),
              perms=0o755)
        # end changes for Ceph >= 0.61.3
        try:
            _create_monitor(keyring,
                            secret,
                            hostname,
                            path,
                            done,
                            init_marker)
        except Exception:
            raise
        finally:
            os.unlink(keyring)


def _create_monitor(keyring, secret, hostname, path, done, init_marker):
    """Create monitor filesystem and enable and start ceph-mon process

    :param keyring: path to temporary keyring on disk
    :type keyring: str
    :param secret: cephx secret to use for monitor authentication
    :type: secret: str
    :param hostname: hostname of the local unit
    :type hostname: str
    :param path: full path to Ceph mon directory
    :type path: str
    :param done: full path to 'done' marker for Ceph mon
    :type done: str
    :param init_marker: full path to 'init' marker for Ceph mon
    :type init_marker: str
    """
    subprocess.check_call(['ceph-authtool', keyring,
                           '--create-keyring', '--name=mon.',
                           '--add-key={}'.format(secret),
                           '--cap', 'mon', 'allow *'])
    subprocess.check_call(['ceph-mon', '--mkfs',
                           '-i', hostname,
                           '--keyring', keyring])
    chownr('/var/log/ceph', ceph_user(), ceph_user())
    chownr(path, ceph_user(), ceph_user())
    with open(done, 'w'):
        pass
    with open(init_marker, 'w'):
        pass

    if systemd():
        if cmp_pkgrevno('ceph', '14.0.0') >= 0:
            systemd_unit = 'ceph-mon@{}'.format(socket.gethostname())
        else:
            systemd_unit = 'ceph-mon'
        subprocess.check_call(['systemctl', 'enable', systemd_unit])
        service_restart(systemd_unit)
    else:
        service_restart('ceph-mon-all')


def create_keyrings():
    """Create keyrings for operation of ceph-mon units

    NOTE: The quorum should be done before to execute this function.

    :raises: Exception if keyrings cannot be created
    """
    if cmp_pkgrevno('ceph', '14.0.0') >= 0:
        # NOTE(jamespage): At Nautilus, keys are created by the
        #                  monitors automatically and just need
        #                  exporting.
        output = str(subprocess.check_output(
            [
                'sudo',
                '-u', ceph_user(),
                'ceph',
                '--name', 'mon.',
                '--keyring',
                '/var/lib/ceph/mon/ceph-{}/keyring'.format(
                    socket.gethostname()
                ),
                'auth', 'get', 'client.admin',
            ]).decode('UTF-8')).strip()
        if not output:
            # NOTE: key not yet created, raise exception and retry
            raise Exception
        # NOTE: octopus wants newline at end of file LP: #1864706
        output += '\n'
        write_file(_client_admin_keyring, output,
                   owner=ceph_user(), group=ceph_user(),
                   perms=0o400)
    else:
        # NOTE(jamespage): Later Ceph releases require explicit
        #                  call to ceph-create-keys to setup the
        #                  admin keys for the cluster; this command
        #                  will wait for quorum in the cluster before
        #                  returning.
        # NOTE(fnordahl): Explicitly run `ceph-create-keys` for older
        #                 Ceph releases too.  This improves bootstrap
        #                 resilience as the charm will wait for
        #                 presence of peer units before attempting
        #                 to bootstrap.  Note that charms deploying
        #                 ceph-mon service should disable running of
        #                 `ceph-create-keys` service in init system.
        cmd = ['ceph-create-keys', '--id', socket.gethostname()]
        if cmp_pkgrevno('ceph', '12.0.0') >= 0:
            # NOTE(fnordahl): The default timeout in ceph-create-keys of 600
            #                 seconds is not adequate.  Increase timeout when
            #                 timeout parameter available.  For older releases
            #                 we rely on retry_on_exception decorator.
            #                 LP#1719436
            cmd.extend(['--timeout', '1800'])
        subprocess.check_call(cmd)
        osstat = os.stat(_client_admin_keyring)
        if not osstat.st_size:
            # NOTE(fnordahl): Retry will fail as long as this file exists.
            #                 LP#1719436
            os.remove(_client_admin_keyring)
            raise Exception


def update_monfs():
    hostname = socket.gethostname()
    monfs = '/var/lib/ceph/mon/ceph-{}'.format(hostname)
    if systemd():
        init_marker = '{}/systemd'.format(monfs)
    else:
        init_marker = '{}/upstart'.format(monfs)
    if os.path.exists(monfs) and not os.path.exists(init_marker):
        # Mark mon as managed by upstart so that
        # it gets start correctly on reboots
        with open(init_marker, 'w'):
            pass


def get_partitions(dev):
    cmd = ['partx', '--raw', '--noheadings', dev]
    try:
        out = str(subprocess.check_output(cmd).decode('UTF-8')).splitlines()
        log("get partitions: {}".format(out), level=DEBUG)
        return out
    except subprocess.CalledProcessError as e:
        log("Can't get info for {0}: {1}".format(dev, e.output))
        return []


def get_lvs(dev):
    """
    List logical volumes for the provided block device

    :param: dev: Full path to block device.
    :raises subprocess.CalledProcessError: in the event that any supporting
                                           operation failed.
    :returns: list: List of logical volumes provided by the block device
    """
    if not lvm.is_lvm_physical_volume(dev):
        return []
    vg_name = lvm.list_lvm_volume_group(dev)
    return lvm.list_logical_volumes('vg_name={}'.format(vg_name))


def find_least_used_utility_device(utility_devices, lvs=False):
    """
    Find a utility device which has the smallest number of partitions
    among other devices in the supplied list.

    :utility_devices: A list of devices to be used for filestore journal
    or bluestore wal or db.
    :lvs: flag to indicate whether inspection should be based on LVM LV's
    :return: string device name
    """
    if lvs:
        usages = map(lambda a: (len(get_lvs(a)), a), utility_devices)
    else:
        usages = map(lambda a: (len(get_partitions(a)), a), utility_devices)
    least = min(usages, key=lambda t: t[0])
    return least[1]


def get_devices(name):
    """Merge config and Juju storage based devices

    :name: The name of the device type, e.g.: wal, osd, journal
    :returns: Set(device names), which are strings
    """
    if config(name):
        devices = [dev.strip() for dev in config(name).split(' ')]
    else:
        devices = []
    storage_ids = storage_list(name)
    devices.extend((storage_get('location', sid) for sid in storage_ids))
    devices = filter(os.path.exists, devices)

    return set(devices)


def osdize(dev, osd_format, osd_journal, ignore_errors=False, encrypt=False,
           bluestore=False, key_manager=CEPH_KEY_MANAGER):
    if dev.startswith('/dev'):
        osdize_dev(dev, osd_format, osd_journal,
                   ignore_errors, encrypt,
                   bluestore, key_manager)
    else:
        if cmp_pkgrevno('ceph', '14.0.0') >= 0:
            log("Directory backed OSDs can not be created on Nautilus",
                level=WARNING)
            return
        osdize_dir(dev, encrypt, bluestore)


def osdize_dev(dev, osd_format, osd_journal, ignore_errors=False,
               encrypt=False, bluestore=False, key_manager=CEPH_KEY_MANAGER):
    """
    Prepare a block device for use as a Ceph OSD

    A block device will only be prepared once during the lifetime
    of the calling charm unit; future executions will be skipped.

    :param: dev: Full path to block device to use
    :param: osd_format: Format for OSD filesystem
    :param: osd_journal: List of block devices to use for OSD journals
    :param: ignore_errors: Don't fail in the event of any errors during
                           processing
    :param: encrypt: Encrypt block devices using 'key_manager'
    :param: bluestore: Use bluestore native Ceph block device format
    :param: key_manager: Key management approach for encryption keys
    :raises subprocess.CalledProcessError: in the event that any supporting
                                           subprocess operation failed
    :raises ValueError: if an invalid key_manager is provided
    """
    if key_manager not in KEY_MANAGERS:
        raise ValueError('Unsupported key manager: {}'.format(key_manager))

    db = kv()
    osd_devices = db.get('osd-devices', [])
    try:
        if dev in osd_devices:
            log('Device {} already processed by charm,'
                ' skipping'.format(dev))
            return

        if not os.path.exists(dev):
            log('Path {} does not exist - bailing'.format(dev))
            return

        if not is_block_device(dev):
            log('Path {} is not a block device - bailing'.format(dev))
            return

        if is_osd_disk(dev):
            log('Looks like {} is already an'
                ' OSD data or journal, skipping.'.format(dev))
            if is_device_mounted(dev):
                osd_devices.append(dev)
            return

        if is_device_mounted(dev):
            log('Looks like {} is in use, skipping.'.format(dev))
            return

        if is_active_bluestore_device(dev):
            log('{} is in use as an active bluestore block device,'
                ' skipping.'.format(dev))
            osd_devices.append(dev)
            return

        if is_mapped_luks_device(dev):
            log('{} is a mapped LUKS device,'
                ' skipping.'.format(dev))
            return

        if cmp_pkgrevno('ceph', '12.2.4') >= 0:
            cmd = _ceph_volume(dev,
                               osd_journal,
                               encrypt,
                               bluestore,
                               key_manager)
        else:
            cmd = _ceph_disk(dev,
                             osd_format,
                             osd_journal,
                             encrypt,
                             bluestore)

        try:
            status_set('maintenance', 'Initializing device {}'.format(dev))
            log("osdize cmd: {}".format(cmd))
            subprocess.check_call(cmd)
        except subprocess.CalledProcessError:
            try:
                lsblk_output = subprocess.check_output(
                    ['lsblk', '-P']).decode('UTF-8')
            except subprocess.CalledProcessError as e:
                log("Couldn't get lsblk output: {}".format(e), ERROR)
            if ignore_errors:
                log('Unable to initialize device: {}'.format(dev), WARNING)
                if lsblk_output:
                    log('lsblk output: {}'.format(lsblk_output), DEBUG)
            else:
                log('Unable to initialize device: {}'.format(dev), ERROR)
                if lsblk_output:
                    log('lsblk output: {}'.format(lsblk_output), WARNING)
                raise

        # NOTE: Record processing of device only on success to ensure that
        #       the charm only tries to initialize a device of OSD usage
        #       once during its lifetime.
        osd_devices.append(dev)
    finally:
        db.set('osd-devices', osd_devices)
        db.flush()


def _ceph_disk(dev, osd_format, osd_journal, encrypt=False, bluestore=False):
    """
    Prepare a device for usage as a Ceph OSD using ceph-disk

    :param: dev: Full path to use for OSD block device setup,
                 The function looks up realpath of the device
    :param: osd_journal: List of block devices to use for OSD journals
    :param: encrypt: Use block device encryption (unsupported)
    :param: bluestore: Use bluestore storage for OSD
    :returns: list. 'ceph-disk' command and required parameters for
                    execution by check_call
    """
    cmd = ['ceph-disk', 'prepare']

    if encrypt:
        cmd.append('--dmcrypt')

    if osd_format and not bluestore:
        cmd.append('--fs-type')
        cmd.append(osd_format)

    # NOTE(jamespage): enable experimental bluestore support
    if use_bluestore():
        cmd.append('--bluestore')
        wal = get_devices('bluestore-wal')
        if wal:
            cmd.append('--block.wal')
            least_used_wal = find_least_used_utility_device(wal)
            cmd.append(least_used_wal)
        db = get_devices('bluestore-db')
        if db:
            cmd.append('--block.db')
            least_used_db = find_least_used_utility_device(db)
            cmd.append(least_used_db)
    elif cmp_pkgrevno('ceph', '12.1.0') >= 0 and not bluestore:
        cmd.append('--filestore')

    cmd.append(os.path.realpath(dev))

    if osd_journal:
        least_used = find_least_used_utility_device(osd_journal)
        cmd.append(least_used)

    return cmd


def _ceph_volume(dev, osd_journal, encrypt=False, bluestore=False,
                 key_manager=CEPH_KEY_MANAGER):
    """
    Prepare and activate a device for usage as a Ceph OSD using ceph-volume.

    This also includes creation of all PV's, VG's and LV's required to
    support the initialization of the OSD.

    :param: dev: Full path to use for OSD block device setup
    :param: osd_journal: List of block devices to use for OSD journals
    :param: encrypt: Use block device encryption
    :param: bluestore: Use bluestore storage for OSD
    :param: key_manager: dm-crypt Key Manager to use
    :raises subprocess.CalledProcessError: in the event that any supporting
                                           LVM operation failed.
    :returns: list. 'ceph-volume' command and required parameters for
                    execution by check_call
    """
    cmd = ['ceph-volume', 'lvm', 'create']

    osd_fsid = str(uuid.uuid4())
    cmd.append('--osd-fsid')
    cmd.append(osd_fsid)

    if bluestore:
        cmd.append('--bluestore')
        main_device_type = 'block'
    else:
        cmd.append('--filestore')
        main_device_type = 'data'

    if encrypt and key_manager == CEPH_KEY_MANAGER:
        cmd.append('--dmcrypt')

    # On-disk journal volume creation
    if not osd_journal and not bluestore:
        journal_lv_type = 'journal'
        cmd.append('--journal')
        cmd.append(_allocate_logical_volume(
            dev=dev,
            lv_type=journal_lv_type,
            osd_fsid=osd_fsid,
            size='{}M'.format(calculate_volume_size('journal')),
            encrypt=encrypt,
            key_manager=key_manager)
        )

    cmd.append('--data')
    cmd.append(_allocate_logical_volume(dev=dev,
                                        lv_type=main_device_type,
                                        osd_fsid=osd_fsid,
                                        encrypt=encrypt,
                                        key_manager=key_manager))

    if bluestore:
        for extra_volume in ('wal', 'db'):
            devices = get_devices('bluestore-{}'.format(extra_volume))
            if devices:
                cmd.append('--block.{}'.format(extra_volume))
                least_used = find_least_used_utility_device(devices,
                                                            lvs=True)
                cmd.append(_allocate_logical_volume(
                    dev=least_used,
                    lv_type=extra_volume,
                    osd_fsid=osd_fsid,
                    size='{}M'.format(calculate_volume_size(extra_volume)),
                    shared=True,
                    encrypt=encrypt,
                    key_manager=key_manager)
                )

    elif osd_journal:
        cmd.append('--journal')
        least_used = find_least_used_utility_device(osd_journal,
                                                    lvs=True)
        cmd.append(_allocate_logical_volume(
            dev=least_used,
            lv_type='journal',
            osd_fsid=osd_fsid,
            size='{}M'.format(calculate_volume_size('journal')),
            shared=True,
            encrypt=encrypt,
            key_manager=key_manager)
        )

    return cmd


def _partition_name(dev):
    """
    Derive the first partition name for a block device

    :param: dev: Full path to block device.
    :returns: str: Full path to first partition on block device.
    """
    if dev[-1].isdigit():
        return '{}p1'.format(dev)
    else:
        return '{}1'.format(dev)


def is_active_bluestore_device(dev):
    """
    Determine whether provided device is part of an active
    bluestore based OSD (as its block component).

    :param: dev: Full path to block device to check for Bluestore usage.
    :returns: boolean: indicating whether device is in active use.
    """
    if not lvm.is_lvm_physical_volume(dev):
        return False

    vg_name = lvm.list_lvm_volume_group(dev)
    try:
        lv_name = lvm.list_logical_volumes('vg_name={}'.format(vg_name))[0]
    except IndexError:
        return False

    block_symlinks = glob.glob('/var/lib/ceph/osd/ceph-*/block')
    for block_candidate in block_symlinks:
        if os.path.islink(block_candidate):
            target = os.readlink(block_candidate)
            if target.endswith(lv_name):
                return True

    return False


def is_luks_device(dev):
    """
    Determine if dev is a LUKS-formatted block device.

    :param: dev: A full path to a block device to check for LUKS header
    presence
    :returns: boolean: indicates whether a device is used based on LUKS header.
    """
    return True if _luks_uuid(dev) else False


def is_mapped_luks_device(dev):
    """
    Determine if dev is a mapped LUKS device
    :param: dev: A full path to a block device to be checked
    :returns: boolean: indicates whether a device is mapped
    """
    _, dirs, _ = next(os.walk(
        '/sys/class/block/{}/holders/'
        .format(os.path.basename(os.path.realpath(dev))))
    )
    is_held = len(dirs) > 0
    return is_held and is_luks_device(dev)


def get_conf(variable):
    """
    Get the value of the given configuration variable from the
    cluster.

    :param variable: Ceph configuration variable
    :returns: str. configured value for provided variable

    """
    return subprocess.check_output([
        'ceph-osd',
        '--show-config-value={}'.format(variable),
        '--no-mon-config',
    ]).strip()


def calculate_volume_size(lv_type):
    """
    Determine the configured size for Bluestore DB/WAL or
    Filestore Journal devices

    :param lv_type: volume type (db, wal or journal)
    :raises KeyError: if invalid lv_type is supplied
    :returns: int. Configured size in megabytes for volume type
    """
    # lv_type -> Ceph configuration option
    _config_map = {
        'db': 'bluestore_block_db_size',
        'wal': 'bluestore_block_wal_size',
        'journal': 'osd_journal_size',
    }

    # default sizes in MB
    _default_size = {
        'db': 1024,
        'wal': 576,
        'journal': 1024,
    }

    # conversion of Ceph config units to MB
    _units = {
        'db': 1048576,  # Bytes -> MB
        'wal': 1048576,  # Bytes -> MB
        'journal': 1,  # Already in MB
    }

    configured_size = get_conf(_config_map[lv_type])

    if configured_size is None or int(configured_size) == 0:
        return _default_size[lv_type]
    else:
        return int(configured_size) / _units[lv_type]


def _luks_uuid(dev):
    """
    Check to see if dev is a LUKS encrypted volume, returning the UUID
    of volume if it is.

    :param: dev: path to block device to check.
    :returns: str. UUID of LUKS device or None if not a LUKS device
    """
    try:
        cmd = ['cryptsetup', 'luksUUID', dev]
        return subprocess.check_output(cmd).decode('UTF-8').strip()
    except subprocess.CalledProcessError:
        return None


def _initialize_disk(dev, dev_uuid, encrypt=False,
                     key_manager=CEPH_KEY_MANAGER):
    """
    Initialize a raw block device consuming 100% of the available
    disk space.

    Function assumes that block device has already been wiped.

    :param: dev: path to block device to initialize
    :param: dev_uuid: UUID to use for any dm-crypt operations
    :param: encrypt: Encrypt OSD devices using dm-crypt
    :param: key_manager: Key management approach for dm-crypt keys
    :raises: subprocess.CalledProcessError: if any parted calls fail
    :returns: str: Full path to new partition.
    """
    use_vaultlocker = encrypt and key_manager == VAULT_KEY_MANAGER

    if use_vaultlocker:
        # NOTE(jamespage): Check to see if already initialized as a LUKS
        #                  volume, which indicates this is a shared block
        #                  device for journal, db or wal volumes.
        luks_uuid = _luks_uuid(dev)
        if luks_uuid:
            return '/dev/mapper/crypt-{}'.format(luks_uuid)

    dm_crypt = '/dev/mapper/crypt-{}'.format(dev_uuid)

    if use_vaultlocker and not os.path.exists(dm_crypt):
        subprocess.check_call([
            'vaultlocker',
            'encrypt',
            '--uuid', dev_uuid,
            dev,
        ])
        subprocess.check_call([
            'dd',
            'if=/dev/zero',
            'of={}'.format(dm_crypt),
            'bs=512',
            'count=1',
        ])

    if use_vaultlocker:
        return dm_crypt
    else:
        return dev


def _allocate_logical_volume(dev, lv_type, osd_fsid,
                             size=None, shared=False,
                             encrypt=False,
                             key_manager=CEPH_KEY_MANAGER):
    """
    Allocate a logical volume from a block device, ensuring any
    required initialization and setup of PV's and VG's to support
    the LV.

    :param: dev: path to block device to allocate from.
    :param: lv_type: logical volume type to create
                     (data, block, journal, wal, db)
    :param: osd_fsid: UUID of the OSD associate with the LV
    :param: size: Size in LVM format for the device;
                  if unset 100% of VG
    :param: shared: Shared volume group (journal, wal, db)
    :param: encrypt: Encrypt OSD devices using dm-crypt
    :param: key_manager: dm-crypt Key Manager to use
    :raises subprocess.CalledProcessError: in the event that any supporting
                                           LVM or parted operation fails.
    :returns: str: String in the format 'vg_name/lv_name'.
    """
    lv_name = "osd-{}-{}".format(lv_type, osd_fsid)
    current_volumes = lvm.list_logical_volumes()
    if shared:
        dev_uuid = str(uuid.uuid4())
    else:
        dev_uuid = osd_fsid
    pv_dev = _initialize_disk(dev, dev_uuid, encrypt, key_manager)

    vg_name = None
    if not lvm.is_lvm_physical_volume(pv_dev):
        lvm.create_lvm_physical_volume(pv_dev)
        if not os.path.exists(pv_dev):
            # NOTE: trigger rescan to work around bug 1878752
            rescan_osd_devices()
        if shared:
            vg_name = 'ceph-{}-{}'.format(lv_type,
                                          str(uuid.uuid4()))
        else:
            vg_name = 'ceph-{}'.format(osd_fsid)
        lvm.create_lvm_volume_group(vg_name, pv_dev)
    else:
        vg_name = lvm.list_lvm_volume_group(pv_dev)

    if lv_name not in current_volumes:
        lvm.create_logical_volume(lv_name, vg_name, size)

    return "{}/{}".format(vg_name, lv_name)


def osdize_dir(path, encrypt=False, bluestore=False):
    """Ask ceph-disk to prepare a directory to become an OSD.

    :param path: str. The directory to osdize
    :param encrypt: bool. Should the OSD directory be encrypted at rest
    :returns: None
    """

    db = kv()
    osd_devices = db.get('osd-devices', [])
    if path in osd_devices:
        log('Device {} already processed by charm,'
            ' skipping'.format(path))
        return

    for t in ['upstart', 'systemd']:
        if os.path.exists(os.path.join(path, t)):
            log('Path {} is already used as an OSD dir - bailing'.format(path))
            return

    if cmp_pkgrevno('ceph', "0.56.6") < 0:
        log('Unable to use directories for OSDs with ceph < 0.56.6',
            level=ERROR)
        return

    mkdir(path, owner=ceph_user(), group=ceph_user(), perms=0o755)
    chownr('/var/lib/ceph', ceph_user(), ceph_user())
    cmd = [
        'sudo', '-u', ceph_user(),
        'ceph-disk',
        'prepare',
        '--data-dir',
        path
    ]
    if cmp_pkgrevno('ceph', '0.60') >= 0:
        if encrypt:
            cmd.append('--dmcrypt')

    # NOTE(icey): enable experimental bluestore support
    if cmp_pkgrevno('ceph', '10.2.0') >= 0 and bluestore:
        cmd.append('--bluestore')
    elif cmp_pkgrevno('ceph', '12.1.0') >= 0 and not bluestore:
        cmd.append('--filestore')
    log("osdize dir cmd: {}".format(cmd))
    subprocess.check_call(cmd)

    # NOTE: Record processing of device only on success to ensure that
    #       the charm only tries to initialize a device of OSD usage
    #       once during its lifetime.
    osd_devices.append(path)
    db.set('osd-devices', osd_devices)
    db.flush()


def filesystem_mounted(fs):
    return subprocess.call(['grep', '-wqs', fs, '/proc/mounts']) == 0


def get_running_osds():
    """Returns a list of the pids of the current running OSD daemons"""
    cmd = ['pgrep', 'ceph-osd']
    try:
        result = str(subprocess.check_output(cmd).decode('UTF-8'))
        return result.split()
    except subprocess.CalledProcessError:
        return []


def get_cephfs(service):
    """List the Ceph Filesystems that exist.

    :param service: The service name to run the Ceph command under
    :returns: list. Returns a list of the Ceph filesystems
    """
    if get_version() < 0.86:
        # This command wasn't introduced until 0.86 Ceph
        return []
    try:
        output = str(subprocess
                     .check_output(["ceph", '--id', service, "fs", "ls"])
                     .decode('UTF-8'))
        if not output:
            return []
        """
        Example subprocess output:
        'name: ip-172-31-23-165, metadata pool: ip-172-31-23-165_metadata,
         data pools: [ip-172-31-23-165_data ]\n'
        output: filesystems: ['ip-172-31-23-165']
        """
        filesystems = []
        for line in output.splitlines():
            parts = line.split(',')
            for part in parts:
                if "name" in part:
                    filesystems.append(part.split(' ')[1])
    except subprocess.CalledProcessError:
        return []


def wait_for_all_monitors_to_upgrade(new_version, upgrade_key):
    """Fairly self explanatory name. This function will wait
    for all monitors in the cluster to upgrade or it will
    return after a timeout period has expired.

    :param new_version: str of the version to watch
    :param upgrade_key: the cephx key name to use
    """
    done = False
    start_time = time.time()
    monitor_list = []

    mon_map = get_mon_map('admin')
    if mon_map['monmap']['mons']:
        for mon in mon_map['monmap']['mons']:
            monitor_list.append(mon['name'])
    while not done:
        try:
            done = all(monitor_key_exists(upgrade_key, "{}_{}_{}_done".format(
                "mon", mon, new_version
            )) for mon in monitor_list)
            current_time = time.time()
            if current_time > (start_time + 10 * 60):
                raise Exception
            else:
                # Wait 30 seconds and test again if all monitors are upgraded
                time.sleep(30)
        except subprocess.CalledProcessError:
            raise


# Edge cases:
# 1. Previous node dies on upgrade, can we retry?
def roll_monitor_cluster(new_version, upgrade_key):
    """This is tricky to get right so here's what we're going to do.

    There's 2 possible cases: Either I'm first in line or not.
    If I'm not first in line I'll wait a random time between 5-30 seconds
    and test to see if the previous monitor is upgraded yet.

    :param new_version: str of the version to upgrade to
    :param upgrade_key: the cephx key name to use when upgrading
    """
    log('roll_monitor_cluster called with {}'.format(new_version))
    my_name = socket.gethostname()
    monitor_list = []
    mon_map = get_mon_map('admin')
    if mon_map['monmap']['mons']:
        for mon in mon_map['monmap']['mons']:
            monitor_list.append(mon['name'])
    else:
        status_set('blocked', 'Unable to get monitor cluster information')
        sys.exit(1)
    log('monitor_list: {}'.format(monitor_list))

    # A sorted list of OSD unit names
    mon_sorted_list = sorted(monitor_list)

    # Install packages immediately but defer restarts to when it's our time.
    upgrade_monitor(new_version, restart_daemons=False)
    try:
        position = mon_sorted_list.index(my_name)
        log("upgrade position: {}".format(position))
        if position == 0:
            # I'm first!  Roll
            # First set a key to inform others I'm about to roll
            lock_and_roll(upgrade_key=upgrade_key,
                          service='mon',
                          my_name=my_name,
                          version=new_version)
        else:
            # Check if the previous node has finished
            status_set('waiting',
                       'Waiting on {} to finish upgrading'.format(
                           mon_sorted_list[position - 1]))
            wait_on_previous_node(upgrade_key=upgrade_key,
                                  service='mon',
                                  previous_node=mon_sorted_list[position - 1],
                                  version=new_version)
            lock_and_roll(upgrade_key=upgrade_key,
                          service='mon',
                          my_name=my_name,
                          version=new_version)
        # NOTE(jamespage):
        # Wait until all monitors have upgraded before bootstrapping
        # the ceph-mgr daemons due to use of new mgr keyring profiles
        if new_version == 'luminous':
            wait_for_all_monitors_to_upgrade(new_version=new_version,
                                             upgrade_key=upgrade_key)
            bootstrap_manager()
    except ValueError:
        log("Failed to find {} in list {}.".format(
            my_name, mon_sorted_list))
        status_set('blocked', 'failed to upgrade monitor')


# For E731 we can't assign a lambda, therefore, instead pass this.
def noop():
    pass


def upgrade_monitor(new_version, kick_function=None, restart_daemons=True):
    """Upgrade the current Ceph monitor to the new version

    :param new_version: String version to upgrade to.
    """
    if kick_function is None:
        kick_function = noop
    current_version = get_version()
    status_set("maintenance", "Upgrading monitor")
    log("Current Ceph version is {}".format(current_version))
    log("Upgrading to: {}".format(new_version))

    # Needed to determine if whether to stop/start ceph-mgr
    luminous_or_later = cmp_pkgrevno('ceph-common', '12.2.0') >= 0

    kick_function()
    try:
        add_source(config('source'), config('key'))
        apt_update(fatal=True)
    except subprocess.CalledProcessError as err:
        log("Adding the Ceph source failed with message: {}".format(
            err))
        status_set("blocked", "Upgrade to {} failed".format(new_version))
        sys.exit(1)
    kick_function()

    try:
        apt_install(packages=determine_packages(), fatal=True)
        rm_packages = determine_packages_to_remove()
        if rm_packages:
            apt_purge(packages=rm_packages, fatal=True)
    except subprocess.CalledProcessError as err:
        log("Upgrading packages failed "
            "with message: {}".format(err))
        status_set("blocked", "Upgrade to {} failed".format(new_version))
        sys.exit(1)

    if not restart_daemons:
        log("Packages upgraded but not restarting daemons yet.")
        return

    try:
        if systemd():
            service_stop('ceph-mon')
            log("restarting ceph-mgr.target maybe: {}"
                .format(luminous_or_later))
            if luminous_or_later:
                service_stop('ceph-mgr.target')
        else:
            service_stop('ceph-mon-all')

        kick_function()

        owner = ceph_user()

        # Ensure the files and directories under /var/lib/ceph is chowned
        # properly as part of the move to the Jewel release, which moved the
        # ceph daemons to running as ceph:ceph instead of root:root.
        if new_version == 'jewel':
            # Ensure the ownership of Ceph's directories is correct
            chownr(path=os.path.join(os.sep, "var", "lib", "ceph"),
                   owner=owner,
                   group=owner,
                   follow_links=True)

        kick_function()

        # Ensure that mon directory is user writable
        hostname = socket.gethostname()
        path = '/var/lib/ceph/mon/ceph-{}'.format(hostname)
        mkdir(path, owner=ceph_user(), group=ceph_user(),
              perms=0o755)

        if systemd():
            service_restart('ceph-mon')
            log("starting ceph-mgr.target maybe: {}".format(luminous_or_later))
            if luminous_or_later:
                # due to BUG: #1849874 we have to force a restart to get it to
                # drop the previous version of ceph-manager and start the new
                # one.
                service_restart('ceph-mgr.target')
        else:
            service_start('ceph-mon-all')
    except subprocess.CalledProcessError as err:
        log("Stopping ceph and upgrading packages failed "
            "with message: {}".format(err))
        status_set("blocked", "Upgrade to {} failed".format(new_version))
        sys.exit(1)


def lock_and_roll(upgrade_key, service, my_name, version):
    """Create a lock on the Ceph monitor cluster and upgrade.

    :param upgrade_key: str. The cephx key to use
    :param service: str. The cephx id to use
    :param my_name: str. The current hostname
    :param version: str. The version we are upgrading to
    """
    start_timestamp = time.time()

    log('monitor_key_set {}_{}_{}_start {}'.format(
        service,
        my_name,
        version,
        start_timestamp))
    monitor_key_set(upgrade_key, "{}_{}_{}_start".format(
        service, my_name, version), start_timestamp)

    # alive indication:
    alive_function = (
        lambda: monitor_key_set(
            upgrade_key, "{}_{}_{}_alive"
            .format(service, my_name, version), time.time()))
    dog = WatchDog(kick_interval=3 * 60,
                   kick_function=alive_function)

    log("Rolling")

    # This should be quick
    if service == 'osd':
        upgrade_osd(version, kick_function=dog.kick_the_dog)
    elif service == 'mon':
        upgrade_monitor(version, kick_function=dog.kick_the_dog)
    else:
        log("Unknown service {}. Unable to upgrade".format(service),
            level=ERROR)
    log("Done")

    stop_timestamp = time.time()
    # Set a key to inform others I am finished
    log('monitor_key_set {}_{}_{}_done {}'.format(service,
                                                  my_name,
                                                  version,
                                                  stop_timestamp))
    status_set('maintenance', 'Finishing upgrade')
    monitor_key_set(upgrade_key, "{}_{}_{}_done".format(service,
                                                        my_name,
                                                        version),
                    stop_timestamp)


def wait_on_previous_node(upgrade_key, service, previous_node, version):
    """A lock that sleeps the current thread while waiting for the previous
    node to finish upgrading.

    :param upgrade_key:
    :param service: str. the cephx id to use
    :param previous_node: str. The name of the previous node to wait on
    :param version: str. The version we are upgrading to
    :returns: None
    """
    log("Previous node is: {}".format(previous_node))

    previous_node_started_f = (
        lambda: monitor_key_exists(
            upgrade_key,
            "{}_{}_{}_start".format(service, previous_node, version)))
    previous_node_finished_f = (
        lambda: monitor_key_exists(
            upgrade_key,
            "{}_{}_{}_done".format(service, previous_node, version)))
    previous_node_alive_time_f = (
        lambda: monitor_key_get(
            upgrade_key,
            "{}_{}_{}_alive".format(service, previous_node, version)))

    # wait for 30 minutes until the previous node starts.  We don't proceed
    # unless we get a start condition.
    try:
        WatchDog.wait_until(previous_node_started_f, timeout=30 * 60)
    except WatchDog.WatchDogTimeoutException:
        log("Waited for previous node to start for 30 minutes. "
            "It didn't start, so may have a serious issue. Continuing with "
            "upgrade of this node.",
            level=WARNING)
        return

    # keep the time it started from this nodes' perspective.
    previous_node_started_at = time.time()
    log("Detected that previous node {} has started.  Time now: {}"
        .format(previous_node, previous_node_started_at))

    # Now wait for the node to complete.  The node may optionally be kicking
    # with the *_alive key, which allows this node to wait longer as it 'knows'
    # the other node is proceeding.
    try:
        WatchDog.timed_wait(kicked_at_function=previous_node_alive_time_f,
                            complete_function=previous_node_finished_f,
                            wait_time=30 * 60,
                            compatibility_wait_time=10 * 60,
                            max_kick_interval=5 * 60)
    except WatchDog.WatchDogDeadException:
        # previous node was kicking, but timed out; log this condition and move
        # on.
        now = time.time()
        waited = int((now - previous_node_started_at) / 60)
        log("Previous node started, but has now not ticked for 5 minutes. "
            "Waited total of {} mins on node {}. current time: {} > "
            "previous node start time: {}. "
            "Continuing with upgrade of this node."
            .format(waited, previous_node, now, previous_node_started_at),
            level=WARNING)
    except WatchDog.WatchDogTimeoutException:
        # previous node never kicked, or simply took too long; log this
        # condition and move on.
        now = time.time()
        waited = int((now - previous_node_started_at) / 60)
        log("Previous node is taking too long; assuming it has died."
            "Waited {} mins on node {}. current time: {} > "
            "previous node start time: {}. "
            "Continuing with upgrade of this node."
            .format(waited, previous_node, now, previous_node_started_at),
            level=WARNING)


class WatchDog(object):
    """Watch a dog; basically a kickable timer with a timeout between two async
    units.

    The idea is that you have an overall timeout and then can kick that timeout
    with intermediary hits, with a max time between those kicks allowed.

    Note that this watchdog doesn't rely on the clock of the other side; just
    roughly when it detects when the other side started.  All timings are based
    on the local clock.

    The kicker will not 'kick' more often than a set interval, regardless of
    how often the kick_the_dog() function is called.  The kicker provides a
    function (lambda: -> None) that is called when the kick interval is
    reached.

    The waiter calls the static method with a check function
    (lambda: -> Boolean) that indicates when the wait should be over and the
    maximum interval to wait.  e.g. 30 minutes with a 5 minute kick interval.

    So the waiter calls wait(f, 30, 3) and the kicker sets up a 3 minute kick
    interval, or however long it is expected for the key to propagate and to
    allow for other delays.

    There is a compatibility mode where if the otherside never kicks, then it
    simply waits for the compatibility timer.
    """

    class WatchDogDeadException(Exception):
        pass

    class WatchDogTimeoutException(Exception):
        pass

    def __init__(self, kick_interval=3 * 60, kick_function=None):
        """Initialise a new WatchDog

        :param kick_interval: the interval when this side kicks the other in
            seconds.
        :type kick_interval: Int
        :param kick_function: The function to call that does the kick.
        :type kick_function: Callable[]
        """
        self.start_time = time.time()
        self.last_run_func = None
        self.last_kick_at = None
        self.kick_interval = kick_interval
        self.kick_f = kick_function

    def kick_the_dog(self):
        """Might call the kick_function if it's time.

        This function can be called as frequently as needed, but will run the
        self.kick_function after kick_interval seconds have passed.
        """
        now = time.time()
        if (self.last_run_func is None or
                (now - self.last_run_func > self.kick_interval)):
            if self.kick_f is not None:
                self.kick_f()
            self.last_run_func = now
        self.last_kick_at = now

    @staticmethod
    def wait_until(wait_f, timeout=10 * 60):
        """Wait for timeout seconds until the passed function return True.

        :param wait_f: The function to call that will end the wait.
        :type wait_f: Callable[[], Boolean]
        :param timeout: The time to wait in seconds.
        :type timeout: int
        """
        start_time = time.time()
        while(not wait_f()):
            now = time.time()
            if now > start_time + timeout:
                raise WatchDog.WatchDogTimeoutException()
            wait_time = random.randrange(5, 30)
            log('wait_until: waiting for {} seconds'.format(wait_time))
            time.sleep(wait_time)

    @staticmethod
    def timed_wait(kicked_at_function,
                   complete_function,
                   wait_time=30 * 60,
                   compatibility_wait_time=10 * 60,
                   max_kick_interval=5 * 60):
        """Wait a maximum time with an intermediate 'kick' time.

        This function will wait for max_kick_interval seconds unless the
        kicked_at_function() call returns a time that is not older that
        max_kick_interval (in seconds).  i.e. the other side can signal that it
        is still doing things during the max_kick_interval as long as it kicks
        at least every max_kick_interval seconds.

        The maximum wait is "wait_time", but the otherside must keep kicking
        during this period.

        The "compatibility_wait_time" is used if the other side never kicks
        (i.e. the kicked_at_function() always returns None.  In this case the
        function wait up to "compatibility_wait_time".

        Note that the type of the return from the kicked_at_function is an
        Optional[str], not a Float.  The function will coerce this to a float
        for the comparison.  This represents the return value of
        time.time() at the "other side".  It's a string to simplify the
        function obtaining the time value from the other side.

        The function raises WatchDogTimeoutException if either the
        compatibility_wait_time or the wait_time are exceeded.

        The function raises WatchDogDeadException if the max_kick_interval is
        exceeded.

        Note that it is possible that the first kick interval is extended to
        compatibility_wait_time if the "other side" doesn't kick immediately.
        The best solution is for the other side to kick early and often.

        :param kicked_at_function: The function to call to retrieve the time
            that the other side 'kicked' at.  None if the other side hasn't
            kicked.
        :type kicked_at_function: Callable[[], Optional[str]]
        :param complete_function: The callable that returns True when done.
        :type complete_function: Callable[[], Boolean]
        :param wait_time: the maximum time to wait, even with kicks, in
            seconds.
        :type wait_time: int
        :param compatibility_wait_time: The time to wait if no kicks are
            received, in seconds.
        :type compatibility_wait_time: int
        :param max_kick_interval: The maximum time allowed between kicks before
            the wait is over, in seconds:
        :type max_kick_interval: int
        :raises: WatchDog.WatchDogTimeoutException,
                 WatchDog.WatchDogDeadException
        """
        start_time = time.time()
        while True:
            if complete_function():
                break
            # the time when the waiting for unit last kicked.
            kicked_at = kicked_at_function()
            now = time.time()
            if kicked_at is None:
                # assume other end doesn't do alive kicks
                if (now - start_time > compatibility_wait_time):
                    raise WatchDog.WatchDogTimeoutException()
            else:
                # other side is participating in kicks; must kick at least
                # every 'max_kick_interval' to stay alive.
                if (now - float(kicked_at) > max_kick_interval):
                    raise WatchDog.WatchDogDeadException()
            if (now - start_time > wait_time):
                raise WatchDog.WatchDogTimeoutException()
            delay_time = random.randrange(5, 30)
            log('waiting for {} seconds'.format(delay_time))
            time.sleep(delay_time)


def get_upgrade_position(osd_sorted_list, match_name):
    """Return the upgrade position for the given OSD.

    :param osd_sorted_list: OSDs sorted
    :type osd_sorted_list: [str]
    :param match_name: The OSD name to match
    :type match_name: str
    :returns: The position of the name
    :rtype: int
    :raises: ValueError if name is not found
    """
    for index, item in enumerate(osd_sorted_list):
        if item.name == match_name:
            return index
    raise ValueError("OSD name '{}' not found in get_upgrade_position list"
                     .format(match_name))


# Edge cases:
# 1. Previous node dies on upgrade, can we retry?
# 2. This assumes that the OSD failure domain is not set to OSD.
#    It rolls an entire server at a time.
def roll_osd_cluster(new_version, upgrade_key):
    """This is tricky to get right so here's what we're going to do.

    There's 2 possible cases: Either I'm first in line or not.
    If I'm not first in line I'll wait a random time between 5-30 seconds
    and test to see if the previous OSD is upgraded yet.

    TODO: If you're not in the same failure domain it's safe to upgrade
     1. Examine all pools and adopt the most strict failure domain policy
        Example: Pool 1: Failure domain = rack
        Pool 2: Failure domain = host
        Pool 3: Failure domain = row

        outcome: Failure domain = host

    :param new_version: str of the version to upgrade to
    :param upgrade_key: the cephx key name to use when upgrading
    """
    log('roll_osd_cluster called with {}'.format(new_version))
    my_name = socket.gethostname()
    osd_tree = get_osd_tree(service=upgrade_key)
    # A sorted list of OSD unit names
    osd_sorted_list = sorted(osd_tree)
    log("osd_sorted_list: {}".format(osd_sorted_list))

    try:
        position = get_upgrade_position(osd_sorted_list, my_name)
        log("upgrade position: {}".format(position))
        if position == 0:
            # I'm first!  Roll
            # First set a key to inform others I'm about to roll
            lock_and_roll(upgrade_key=upgrade_key,
                          service='osd',
                          my_name=my_name,
                          version=new_version)
        else:
            # Check if the previous node has finished
            status_set('waiting',
                       'Waiting on {} to finish upgrading'.format(
                           osd_sorted_list[position - 1].name))
            wait_on_previous_node(
                upgrade_key=upgrade_key,
                service='osd',
                previous_node=osd_sorted_list[position - 1].name,
                version=new_version)
            lock_and_roll(upgrade_key=upgrade_key,
                          service='osd',
                          my_name=my_name,
                          version=new_version)
    except ValueError:
        log("Failed to find name {} in list {}".format(
            my_name, osd_sorted_list))
        status_set('blocked', 'failed to upgrade osd')


def upgrade_osd(new_version, kick_function=None):
    """Upgrades the current OSD

    :param new_version: str. The new version to upgrade to
    """
    if kick_function is None:
        kick_function = noop

    current_version = get_version()
    status_set("maintenance", "Upgrading OSD")
    log("Current Ceph version is {}".format(current_version))
    log("Upgrading to: {}".format(new_version))

    try:
        add_source(config('source'), config('key'))
        apt_update(fatal=True)
    except subprocess.CalledProcessError as err:
        log("Adding the Ceph sources failed with message: {}".format(
            err))
        status_set("blocked", "Upgrade to {} failed".format(new_version))
        sys.exit(1)

    kick_function()

    try:
        # Upgrade the packages before restarting the daemons.
        status_set('maintenance', 'Upgrading packages to %s' % new_version)
        apt_install(packages=determine_packages(), fatal=True)
        kick_function()

        # If the upgrade does not need an ownership update of any of the
        # directories in the OSD service directory, then simply restart
        # all of the OSDs at the same time as this will be the fastest
        # way to update the code on the node.
        if not dirs_need_ownership_update('osd'):
            log('Restarting all OSDs to load new binaries', DEBUG)
            with maintain_all_osd_states():
                if systemd():
                    service_restart('ceph-osd.target')
                else:
                    service_restart('ceph-osd-all')
            return

        # Need to change the ownership of all directories which are not OSD
        # directories as well.
        # TODO - this should probably be moved to the general upgrade function
        #        and done before mon/OSD.
        update_owner(CEPH_BASE_DIR, recurse_dirs=False)
        non_osd_dirs = filter(lambda x: not x == 'osd',
                              os.listdir(CEPH_BASE_DIR))
        non_osd_dirs = map(lambda x: os.path.join(CEPH_BASE_DIR, x),
                           non_osd_dirs)
        for i, path in enumerate(non_osd_dirs):
            if i % 100 == 0:
                kick_function()
            update_owner(path)

        # Fast service restart wasn't an option because each of the OSD
        # directories need the ownership updated for all the files on
        # the OSD. Walk through the OSDs one-by-one upgrading the OSD.
        for osd_dir in _get_child_dirs(OSD_BASE_DIR):
            kick_function()
            try:
                osd_num = _get_osd_num_from_dirname(osd_dir)
                _upgrade_single_osd(osd_num, osd_dir)
            except ValueError as ex:
                # Directory could not be parsed - junk directory?
                log('Could not parse OSD directory %s: %s' % (osd_dir, ex),
                    WARNING)
                continue

    except (subprocess.CalledProcessError, IOError) as err:
        log("Stopping Ceph and upgrading packages failed "
            "with message: {}".format(err))
        status_set("blocked", "Upgrade to {} failed".format(new_version))
        sys.exit(1)


def _upgrade_single_osd(osd_num, osd_dir):
    """Upgrades the single OSD directory.

    :param osd_num: the num of the OSD
    :param osd_dir: the directory of the OSD to upgrade
    :raises CalledProcessError: if an error occurs in a command issued as part
                                of the upgrade process
    :raises IOError: if an error occurs reading/writing to a file as part
                     of the upgrade process
    """
    with maintain_osd_state(osd_num):
        stop_osd(osd_num)
        disable_osd(osd_num)
        update_owner(osd_dir)
        enable_osd(osd_num)
        start_osd(osd_num)


def stop_osd(osd_num):
    """Stops the specified OSD number.

    :param osd_num: the OSD number to stop
    """
    if systemd():
        service_stop('ceph-osd@{}'.format(osd_num))
    else:
        service_stop('ceph-osd', id=osd_num)


def start_osd(osd_num):
    """Starts the specified OSD number.

    :param osd_num: the OSD number to start.
    """
    if systemd():
        service_start('ceph-osd@{}'.format(osd_num))
    else:
        service_start('ceph-osd', id=osd_num)


def disable_osd(osd_num):
    """Disables the specified OSD number.

    Ensures that the specified OSD will not be automatically started at the
    next reboot of the system. Due to differences between init systems,
    this method cannot make any guarantees that the specified OSD cannot be
    started manually.

    :param osd_num: the OSD id which should be disabled.
    :raises CalledProcessError: if an error occurs invoking the systemd cmd
                                to disable the OSD
    :raises IOError, OSError: if the attempt to read/remove the ready file in
                              an upstart enabled system fails
    """
    if systemd():
        # When running under systemd, the individual ceph-osd daemons run as
        # templated units and can be directly addressed by referring to the
        # templated service name ceph-osd@<osd_num>. Additionally, systemd
        # allows one to disable a specific templated unit by running the
        # 'systemctl disable ceph-osd@<osd_num>' command. When disabled, the
        # OSD should remain disabled until re-enabled via systemd.
        # Note: disabling an already disabled service in systemd returns 0, so
        # no need to check whether it is enabled or not.
        cmd = ['systemctl', 'disable', 'ceph-osd@{}'.format(osd_num)]
        subprocess.check_call(cmd)
    else:
        # Neither upstart nor the ceph-osd upstart script provides for
        # disabling the starting of an OSD automatically. The specific OSD
        # cannot be prevented from running manually, however it can be
        # prevented from running automatically on reboot by removing the
        # 'ready' file in the OSD's root directory. This is due to the
        # ceph-osd-all upstart script checking for the presence of this file
        # before starting the OSD.
        ready_file = os.path.join(OSD_BASE_DIR, 'ceph-{}'.format(osd_num),
                                  'ready')
        if os.path.exists(ready_file):
            os.unlink(ready_file)


def enable_osd(osd_num):
    """Enables the specified OSD number.

    Ensures that the specified osd_num will be enabled and ready to start
    automatically in the event of a reboot.

    :param osd_num: the osd id which should be enabled.
    :raises CalledProcessError: if the call to the systemd command issued
                                fails when enabling the service
    :raises IOError: if the attempt to write the ready file in an upstart
                     enabled system fails
    """
    if systemd():
        cmd = ['systemctl', 'enable', 'ceph-osd@{}'.format(osd_num)]
        subprocess.check_call(cmd)
    else:
        # When running on upstart, the OSDs are started via the ceph-osd-all
        # upstart script which will only start the OSD if it has a 'ready'
        # file. Make sure that file exists.
        ready_file = os.path.join(OSD_BASE_DIR, 'ceph-{}'.format(osd_num),
                                  'ready')
        with open(ready_file, 'w') as f:
            f.write('ready')

        # Make sure the correct user owns the file. It shouldn't be necessary
        # as the upstart script should run with root privileges, but its better
        # to have all the files matching ownership.
        update_owner(ready_file)


def update_owner(path, recurse_dirs=True):
    """Changes the ownership of the specified path.

    Changes the ownership of the specified path to the new ceph daemon user
    using the system's native chown functionality. This may take awhile,
    so this method will issue a set_status for any changes of ownership which
    recurses into directory structures.

    :param path: the path to recursively change ownership for
    :param recurse_dirs: boolean indicating whether to recursively change the
                         ownership of all the files in a path's subtree or to
                         simply change the ownership of the path.
    :raises CalledProcessError: if an error occurs issuing the chown system
                                command
    """
    user = ceph_user()
    user_group = '{ceph_user}:{ceph_user}'.format(ceph_user=user)
    cmd = ['chown', user_group, path]
    if os.path.isdir(path) and recurse_dirs:
        status_set('maintenance', ('Updating ownership of %s to %s' %
                                   (path, user)))
        cmd.insert(1, '-R')

    log('Changing ownership of {path} to {user}'.format(
        path=path, user=user_group), DEBUG)
    start = datetime.now()
    subprocess.check_call(cmd)
    elapsed_time = (datetime.now() - start)

    log('Took {secs} seconds to change the ownership of path: {path}'.format(
        secs=elapsed_time.total_seconds(), path=path), DEBUG)


def get_osd_state(osd_num, osd_goal_state=None):
    """Get OSD state or loop until OSD state matches OSD goal state.

    If osd_goal_state is None, just return the current OSD state.
    If osd_goal_state is not None, loop until the current OSD state matches
    the OSD goal state.

    :param osd_num: the OSD id to get state for
    :param osd_goal_state: (Optional) string indicating state to wait for
                           Defaults to None
    :returns: Returns a str, the OSD state.
    :rtype: str
    """
    while True:
        asok = "/var/run/ceph/ceph-osd.{}.asok".format(osd_num)
        cmd = [
            'ceph',
            'daemon',
            asok,
            'status'
        ]
        try:
            result = json.loads(str(subprocess
                                    .check_output(cmd)
                                    .decode('UTF-8')))
        except (subprocess.CalledProcessError, ValueError) as e:
            log("{}".format(e), level=DEBUG)
            continue
        osd_state = result['state']
        log("OSD {} state: {}, goal state: {}".format(
            osd_num, osd_state, osd_goal_state), level=DEBUG)
        if not osd_goal_state:
            return osd_state
        if osd_state == osd_goal_state:
            return osd_state
        time.sleep(3)


def get_all_osd_states(osd_goal_states=None):
    """Get all OSD states or loop until all OSD states match OSD goal states.

    If osd_goal_states is None, just return a dictionary of current OSD states.
    If osd_goal_states is not None, loop until the current OSD states match
    the OSD goal states.

    :param osd_goal_states: (Optional) dict indicating states to wait for
                            Defaults to None
    :returns: Returns a dictionary of current OSD states.
    :rtype: dict
    """
    osd_states = {}
    for osd_num in get_local_osd_ids():
        if not osd_goal_states:
            osd_states[osd_num] = get_osd_state(osd_num)
        else:
            osd_states[osd_num] = get_osd_state(
                osd_num,
                osd_goal_state=osd_goal_states[osd_num])
    return osd_states


@contextmanager
def maintain_osd_state(osd_num):
    """Ensure the state of an OSD is maintained.

    Ensures the state of an OSD is the same at the end of a block nested
    in a with statement as it was at the beginning of the block.

    :param osd_num: the OSD id to maintain state for
    """
    osd_state = get_osd_state(osd_num)
    try:
        yield
    finally:
        get_osd_state(osd_num, osd_goal_state=osd_state)


@contextmanager
def maintain_all_osd_states():
    """Ensure all local OSD states are maintained.

    Ensures the states of all local OSDs are the same at the end of a
    block nested in a with statement as they were at the beginning of
    the block.
    """
    osd_states = get_all_osd_states()
    try:
        yield
    finally:
        get_all_osd_states(osd_goal_states=osd_states)


def list_pools(client='admin'):
    """This will list the current pools that Ceph has

    :param client: (Optional) client id for Ceph key to use
                   Defaults to ``admin``
    :type client: str
    :returns: Returns a list of available pools.
    :rtype: list
    :raises: subprocess.CalledProcessError if the subprocess fails to run.
    """
    try:
        pool_list = []
        pools = subprocess.check_output(['rados', '--id', client, 'lspools'],
                                        universal_newlines=True,
                                        stderr=subprocess.STDOUT)
        for pool in pools.splitlines():
            pool_list.append(pool)
        return pool_list
    except subprocess.CalledProcessError as err:
        log("rados lspools failed with error: {}".format(err.output))
        raise


def get_pool_param(pool, param, client='admin'):
    """Get parameter from pool.

    :param pool: Name of pool to get variable from
    :type pool: str
    :param param: Name of variable to get
    :type param: str
    :param client: (Optional) client id for Ceph key to use
                   Defaults to ``admin``
    :type client: str
    :returns: Value of variable on pool or None
    :rtype: str or None
    :raises: subprocess.CalledProcessError
    """
    try:
        output = subprocess.check_output(
            ['ceph', '--id', client, 'osd', 'pool', 'get', pool, param],
            universal_newlines=True, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as cp:
        if cp.returncode == 2 and 'ENOENT: option' in cp.output:
            return None
        raise
    if ':' in output:
        return output.split(':')[1].lstrip().rstrip()


def get_pool_erasure_profile(pool, client='admin'):
    """Get erasure code profile for pool.

    :param pool: Name of pool to get variable from
    :type pool: str
    :param client: (Optional) client id for Ceph key to use
                   Defaults to ``admin``
    :type client: str
    :returns: Erasure code profile of pool or None
    :rtype: str or None
    :raises: subprocess.CalledProcessError
    """
    try:
        return get_pool_param(pool, 'erasure_code_profile', client=client)
    except subprocess.CalledProcessError as cp:
        if cp.returncode == 13 and 'EACCES: pool' in cp.output:
            # Not a Erasure coded pool
            return None
        raise


def get_pool_quota(pool, client='admin'):
    """Get pool quota.

    :param pool: Name of pool to get variable from
    :type pool: str
    :param client: (Optional) client id for Ceph key to use
                   Defaults to ``admin``
    :type client: str
    :returns: Dictionary with quota variables
    :rtype: dict
    :raises: subprocess.CalledProcessError
    """
    output = subprocess.check_output(
        ['ceph', '--id', client, 'osd', 'pool', 'get-quota', pool],
        universal_newlines=True, stderr=subprocess.STDOUT)
    rc = re.compile(r'\s+max\s+(\S+)\s*:\s+(\d+)')
    result = {}
    for line in output.splitlines():
        m = rc.match(line)
        if m:
            result.update({'max_{}'.format(m.group(1)): m.group(2)})
    return result


def get_pool_applications(pool='', client='admin'):
    """Get pool applications.

    :param pool: (Optional) Name of pool to get applications for
                 Defaults to get for all pools
    :type pool: str
    :param client: (Optional) client id for Ceph key to use
                   Defaults to ``admin``
    :type client: str
    :returns: Dictionary with pool name as key
    :rtype: dict
    :raises: subprocess.CalledProcessError
    """

    cmd = ['ceph', '--id', client, 'osd', 'pool', 'application', 'get']
    if pool:
        cmd.append(pool)
    try:
        output = subprocess.check_output(cmd,
                                         universal_newlines=True,
                                         stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as cp:
        if cp.returncode == 2 and 'ENOENT' in cp.output:
            return {}
        raise
    return json.loads(output)


def list_pools_detail():
    """Get detailed information about pools.

    Structure:
    {'pool_name_1': {'applications': {'application': {}},
                     'parameters': {'pg_num': '42', 'size': '42'},
                     'quota': {'max_bytes': '1000',
                               'max_objects': '10'},
                     },
     'pool_name_2': ...
     }

    :returns: Dictionary with detailed pool information.
    :rtype: dict
    :raises: subproces.CalledProcessError
    """
    get_params = ['pg_num', 'size']
    result = {}
    applications = get_pool_applications()
    for pool in list_pools():
        result[pool] = {
            'applications': applications.get(pool, {}),
            'parameters': {},
            'quota': get_pool_quota(pool),
        }
        for param in get_params:
            result[pool]['parameters'].update({
                param: get_pool_param(pool, param)})
        erasure_profile = get_pool_erasure_profile(pool)
        if erasure_profile:
            result[pool]['parameters'].update({
                'erasure_code_profile': erasure_profile})
    return result


def dirs_need_ownership_update(service):
    """Determines if directories still need change of ownership.

    Examines the set of directories under the /var/lib/ceph/{service} directory
    and determines if they have the correct ownership or not. This is
    necessary due to the upgrade from Hammer to Jewel where the daemon user
    changes from root: to ceph:.

    :param service: the name of the service folder to check (e.g. OSD, mon)
    :returns: boolean. True if the directories need a change of ownership,
             False otherwise.
    :raises IOError: if an error occurs reading the file stats from one of
                     the child directories.
    :raises OSError: if the specified path does not exist or some other error
    """
    expected_owner = expected_group = ceph_user()
    path = os.path.join(CEPH_BASE_DIR, service)
    for child in _get_child_dirs(path):
        curr_owner, curr_group = owner(child)

        if (curr_owner == expected_owner) and (curr_group == expected_group):
            continue

        # NOTE(lathiat): when config_changed runs on reboot, the OSD might not
        # yet be mounted or started, and the underlying directory the OSD is
        # mounted to is expected to be owned by root. So skip the check. This
        # may also happen for OSD directories for OSDs that were removed.
        if (service == 'osd' and
                not os.path.exists(os.path.join(child, 'magic'))):
            continue

        log('Directory "%s" needs its ownership updated' % child, DEBUG)
        return True

    # All child directories had the expected ownership
    return False


# A dict of valid Ceph upgrade paths. Mapping is old -> new
UPGRADE_PATHS = collections.OrderedDict([
    ('firefly', 'hammer'),
    ('hammer', 'jewel'),
    ('jewel', 'luminous'),
    ('luminous', 'mimic'),
    ('mimic', 'nautilus'),
    ('nautilus', 'octopus'),
    ('octopus', 'pacific'),
    ('pacific', 'quincy'),
])

# Map UCA codenames to Ceph codenames
UCA_CODENAME_MAP = {
    'icehouse': 'firefly',
    'juno': 'firefly',
    'kilo': 'hammer',
    'liberty': 'hammer',
    'mitaka': 'jewel',
    'newton': 'jewel',
    'ocata': 'jewel',
    'pike': 'luminous',
    'queens': 'luminous',
    'rocky': 'mimic',
    'stein': 'mimic',
    'train': 'nautilus',
    'ussuri': 'octopus',
    'victoria': 'octopus',
    'wallaby': 'pacific',
    'xena': 'pacific',
    'yoga': 'quincy',
}


def pretty_print_upgrade_paths():
    """Pretty print supported upgrade paths for Ceph"""
    return ["{} -> {}".format(key, value)
            for key, value in UPGRADE_PATHS.items()]


def resolve_ceph_version(source):
    """Resolves a version of Ceph based on source configuration
    based on Ubuntu Cloud Archive pockets.

    @param: source: source configuration option of charm
    :returns: Ceph release codename or None if not resolvable
    """
    os_release = get_os_codename_install_source(source)
    return UCA_CODENAME_MAP.get(os_release)


def get_ceph_pg_stat():
    """Returns the result of 'ceph pg stat'.

    :returns: dict
    """
    try:
        tree = str(subprocess
                   .check_output(['ceph', 'pg', 'stat', '--format=json'])
                   .decode('UTF-8'))
        try:
            json_tree = json.loads(tree)
            if not json_tree['num_pg_by_state']:
                return None
            return json_tree
        except ValueError as v:
            log("Unable to parse ceph pg stat json: {}. Error: {}".format(
                tree, v))
            raise
    except subprocess.CalledProcessError as e:
        log("ceph pg stat command failed with message: {}".format(e))
        raise


def get_ceph_health():
    """Returns the health of the cluster from a 'ceph status'

    :returns: dict tree of ceph status
    :raises: CalledProcessError if our ceph command fails to get the overall
             status, use get_ceph_health()['overall_status'].
    """
    try:
        tree = str(subprocess
                   .check_output(['ceph', 'status', '--format=json'])
                   .decode('UTF-8'))
        try:
            json_tree = json.loads(tree)
            # Make sure children are present in the JSON
            if not json_tree['overall_status']:
                return None

            return json_tree
        except ValueError as v:
            log("Unable to parse ceph tree json: {}. Error: {}".format(
                tree, v))
            raise
    except subprocess.CalledProcessError as e:
        log("ceph status command failed with message: {}".format(e))
        raise


def reweight_osd(osd_num, new_weight):
    """Changes the crush weight of an OSD to the value specified.

    :param osd_num: the OSD id which should be changed
    :param new_weight: the new weight for the OSD
    :returns: bool. True if output looks right, else false.
    :raises CalledProcessError: if an error occurs invoking the systemd cmd
    """
    try:
        cmd_result = str(subprocess
                         .check_output(['ceph', 'osd', 'crush',
                                        'reweight', "osd.{}".format(osd_num),
                                        new_weight],
                                       stderr=subprocess.STDOUT)
                         .decode('UTF-8'))
        expected_result = "reweighted item id {ID} name \'osd.{ID}\'".format(
                          ID=osd_num) + " to {}".format(new_weight)
        log(cmd_result)
        if expected_result in cmd_result:
            return True
        return False
    except subprocess.CalledProcessError as e:
        log("ceph osd crush reweight command failed"
            " with message: {}".format(e))
        raise


def determine_packages():
    """Determines packages for installation.

    :returns: list of Ceph packages
    """
    packages = PACKAGES.copy()
    if CompareHostReleases(lsb_release()['DISTRIB_CODENAME']) >= 'eoan':
        btrfs_package = 'btrfs-progs'
    else:
        btrfs_package = 'btrfs-tools'
    packages.append(btrfs_package)
    return packages


def determine_packages_to_remove():
    """Determines packages for removal

    Note: if in a container, then the CHRONY_PACKAGE is removed.

    :returns: list of packages to be removed
    :rtype: List[str]
    """
    rm_packages = REMOVE_PACKAGES.copy()
    if is_container():
        rm_packages.extend(filter_missing_packages([CHRONY_PACKAGE]))
    return rm_packages


def bootstrap_manager():
    hostname = socket.gethostname()
    path = '/var/lib/ceph/mgr/ceph-{}'.format(hostname)
    keyring = os.path.join(path, 'keyring')

    if os.path.exists(keyring):
        log('bootstrap_manager: mgr already initialized.')
    else:
        mkdir(path, owner=ceph_user(), group=ceph_user())
        subprocess.check_call(['ceph', 'auth', 'get-or-create',
                               'mgr.{}'.format(hostname), 'mon',
                               'allow profile mgr', 'osd', 'allow *',
                               'mds', 'allow *', '--out-file',
                               keyring])
        chownr(path, ceph_user(), ceph_user())

        unit = 'ceph-mgr@{}'.format(hostname)
        subprocess.check_call(['systemctl', 'enable', unit])
        service_restart(unit)


def osd_noout(enable):
    """Sets or unsets 'noout'

    :param enable: bool. True to set noout, False to unset.
    :returns: bool. True if output looks right.
    :raises CalledProcessError: if an error occurs invoking the systemd cmd
    """
    operation = {
        True: 'set',
        False: 'unset',
    }
    try:
        subprocess.check_call(['ceph', '--id', 'admin',
                               'osd', operation[enable],
                               'noout'])
        log('running ceph osd {} noout'.format(operation[enable]))
        return True
    except subprocess.CalledProcessError as e:
        log(e)
        raise


class OSDConfigSetError(Exception):
    """Error occurred applying OSD settings."""
    pass


def apply_osd_settings(settings):
    """Applies the provided OSD settings

    Apply the provided settings to all local OSD unless settings are already
    present. Settings stop being applied on encountering an error.

    :param settings: dict. Dictionary of settings to apply.
    :returns: bool. True if commands ran successfully.
    :raises: OSDConfigSetError
    """
    current_settings = {}
    base_cmd = 'ceph daemon osd.{osd_id} config --format=json'
    get_cmd = base_cmd + ' get {key}'
    set_cmd = base_cmd + ' set {key} {value}'

    def _get_cli_key(key):
        return(key.replace(' ', '_'))
    # Retrieve the current values to check keys are correct and to make this a
    # noop if setting are already applied.
    for osd_id in get_local_osd_ids():
        for key, value in sorted(settings.items()):
            cli_key = _get_cli_key(key)
            cmd = get_cmd.format(osd_id=osd_id, key=cli_key)
            out = json.loads(
                subprocess.check_output(cmd.split()).decode('UTF-8'))
            if 'error' in out:
                log("Error retrieving OSD setting: {}".format(out['error']),
                    level=ERROR)
                return False
            current_settings[key] = out[cli_key]
        settings_diff = {
            k: v
            for k, v in settings.items()
            if str(v) != str(current_settings[k])}
        for key, value in sorted(settings_diff.items()):
            log("Setting {} to {}".format(key, value), level=DEBUG)
            cmd = set_cmd.format(
                osd_id=osd_id,
                key=_get_cli_key(key),
                value=value)
            out = json.loads(
                subprocess.check_output(cmd.split()).decode('UTF-8'))
            if 'error' in out:
                log("Error applying OSD setting: {}".format(out['error']),
                    level=ERROR)
                raise OSDConfigSetError
    return True


def enabled_manager_modules():
    """Return a list of enabled manager modules.

    :rtype: List[str]
    """
    cmd = ['ceph', 'mgr', 'module', 'ls']
    try:
        modules = subprocess.check_output(cmd).decode('UTF-8')
    except subprocess.CalledProcessError as e:
        log("Failed to list ceph modules: {}".format(e), WARNING)
        return []
    modules = json.loads(modules)
    return modules['enabled_modules']


def is_mgr_module_enabled(module):
    """Is a given manager module enabled.

    :param module:
    :type module: str
    :returns: Whether the named module is enabled
    :rtype: bool
    """
    return module in enabled_manager_modules()


is_dashboard_enabled = functools.partial(is_mgr_module_enabled, 'dashboard')


def mgr_enable_module(module):
    """Enable a Ceph Manager Module.

    :param module: The module name to enable
    :type module: str

    :raises: subprocess.CalledProcessError
    """
    if not is_mgr_module_enabled(module):
        subprocess.check_call(['ceph', 'mgr', 'module', 'enable', module])
        return True
    return False


mgr_enable_dashboard = functools.partial(mgr_enable_module, 'dashboard')


def mgr_disable_module(module):
    """Enable a Ceph Manager Module.

    :param module: The module name to enable
    :type module: str

    :raises: subprocess.CalledProcessError
    """
    if is_mgr_module_enabled(module):
        subprocess.check_call(['ceph', 'mgr', 'module', 'disable', module])
        return True
    return False


mgr_disable_dashboard = functools.partial(mgr_disable_module, 'dashboard')


def ceph_config_set(name, value, who):
    """Set a Ceph config option

    :param name: key to set
    :type name: str
    :param value: value corresponding to key
    :type value: str
    :param who: Config area the key is associated with (e.g. 'dashboard')
    :type who: str

    :raises: subprocess.CalledProcessError
    """
    subprocess.check_call(['ceph', 'config', 'set', who, name, value])


mgr_config_set = functools.partial(ceph_config_set, who='mgr')


def ceph_config_get(name, who):
    """Retrieve the value of a Ceph config option

    :param name: key to lookup
    :type name: str
    :param who: Config area the key is associated with (e.g. 'dashboard')
    :type who: str
    :returns: Value associated with key
    :rtype: str
    :raises: subprocess.CalledProcessError
    """
    return subprocess.check_output(
        ['ceph', 'config', 'get', who, name]).decode('UTF-8')


mgr_config_get = functools.partial(ceph_config_get, who='mgr')


def _dashboard_set_ssl_artifact(path, artifact_name, hostname=None):
    """Set SSL dashboard config option.

    :param path: Path to file
    :type path: str
    :param artifact_name: Option name for setting the artifact
    :type artifact_name: str
    :param hostname: If hostname is set artifact will only be associated with
                     the dashboard on that host.
    :type hostname: str
    :raises: subprocess.CalledProcessError
    """
    cmd = ['ceph', 'dashboard', artifact_name]
    if hostname:
        cmd.append(hostname)
    cmd.extend(['-i', path])
    log(cmd, level=DEBUG)
    subprocess.check_call(cmd)


dashboard_set_ssl_certificate = functools.partial(
    _dashboard_set_ssl_artifact,
    artifact_name='set-ssl-certificate')


dashboard_set_ssl_certificate_key = functools.partial(
    _dashboard_set_ssl_artifact,
    artifact_name='set-ssl-certificate-key')
