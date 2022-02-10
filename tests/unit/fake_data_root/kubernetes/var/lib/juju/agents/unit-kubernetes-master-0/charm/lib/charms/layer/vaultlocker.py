import json
from pathlib import Path
from subprocess import check_call, check_output, CalledProcessError
from uuid import uuid4

from charms.reactive import set_flag
from charmhelpers.core import hookenv
from charmhelpers.core import host
from charmhelpers.core import unitdata
from charmhelpers.contrib.openstack.vaultlocker import (  # noqa
    retrieve_secret_id,
    write_vaultlocker_conf,
)
from charmhelpers.contrib.storage.linux.utils import (
    is_block_device,
    is_device_mounted,
    mkfs_xfs,
)


LOOP_ENVS = Path('/etc/vaultlocker/loop-envs')


class VaultLockerError(Exception):
    """
    Wrapper for exceptions raised when configuring VaultLocker.
    """
    def __init__(self, msg, *args, **kwargs):
        super().__init__(msg.format(*args, **kwargs))


def encrypt_storage(storage_name, mountbase=None):
    """
    Set up encryption for the given Juju storage entry, and optionally create
    and mount XFS filesystems on the encrypted storage entry location(s).

    Note that the storage entry **must** be defined with ``type: block``.

    If ``mountbase`` is not given, the location(s) will not be formatted or
    mounted.  When interacting with or mounting the location(s) manually, the
    name returned by :func:`decrypted_device` called on the storage entry's
    location should be used in place of the raw location.

    If the storage is defined as ``multiple``, the individual locations
    will be mounted at ``{mountbase}/{storage_name}/{num}`` where ``{num}``
    is based on the storage ID.  Otherwise, the storage will mounted at
    ``{mountbase}/{storage_name}``.
    """
    metadata = hookenv.metadata()
    storage_metadata = metadata['storage'][storage_name]
    if storage_metadata['type'] != 'block':
        raise VaultLockerError('Cannot encrypt non-block storage: {}',
                               storage_name)
    multiple = 'multiple' in storage_metadata
    for storage_id in hookenv.storage_list():
        if not storage_id.startswith(storage_name + '/'):
            continue
        storage_location = hookenv.storage_get('location', storage_id)
        if mountbase and multiple:
            mountpoint = Path(mountbase) / storage_id
        elif mountbase:
            mountpoint = Path(mountbase) / storage_name
        else:
            mountpoint = None
        encrypt_device(storage_location, mountpoint)
        set_flag('layer.vaultlocker.{}.ready'.format(storage_id))
        set_flag('layer.vaultlocker.{}.ready'.format(storage_name))


def encrypt_device(device, mountpoint=None, uuid=None):
    """
    Set up encryption for the given block device, and optionally create and
    mount an XFS filesystem on the encrypted device.

    If ``mountpoint`` is not given, the device will not be formatted or
    mounted.  When interacting with or mounting the device manually, the
    name returned by :func:`decrypted_device` called on the device name
    should be used in place of the raw device name.
    """
    if not is_block_device(device):
        raise VaultLockerError('Cannot encrypt non-block device: {}', device)
    if is_device_mounted(device):
        raise VaultLockerError('Cannot encrypt mounted device: {}', device)
    hookenv.log('Encrypting device: {}'.format(device))
    if uuid is None:
        uuid = str(uuid4())
    try:
        check_call(['vaultlocker', 'encrypt', '--uuid', uuid, device])
        unitdata.kv().set('layer.vaultlocker.uuids.{}'.format(device), uuid)
        if mountpoint:
            mapped_device = decrypted_device(device)
            hookenv.log('Creating filesystem on {} ({})'.format(mapped_device,
                                                                device))
            # If this fails, it's probalby due to the size of the loopback
            #    backing file that is defined by the `dd`.
            mkfs_xfs(mapped_device)
            Path(mountpoint).mkdir(mode=0o755, parents=True, exist_ok=True)
            hookenv.log('Mounting filesystem for {} ({}) at {}'
                        ''.format(mapped_device, device, mountpoint))
            host.mount(mapped_device, mountpoint, filesystem='xfs')
            host.fstab_add(mapped_device, mountpoint, 'xfs', ','.join([
                "defaults",
                "nofail",
                "x-systemd.requires=vaultlocker-decrypt@{uuid}.service".format(
                    uuid=uuid,
                ),
                "comment=vaultlocker",
            ]))
    except (CalledProcessError, OSError) as e:
        raise VaultLockerError('Error configuring VaultLocker') from e


def decrypted_device(device):
    """
    Returns the mapped device name for the decrypted version of the encrypted
    device.

    This mapped device name is what should be used for mounting the device.
    """
    uuid = unitdata.kv().get('layer.vaultlocker.uuids.{}'.format(device))
    if not uuid:
        return None
    return '/dev/mapper/crypt-{uuid}'.format(uuid=uuid)


def create_encrypted_loop_mount(mount_path, block_size='1M', block_count=20,
                                backing_file=None):
    """
    Creates a persistent loop device, encrypts it, formats it as XFS, and
    mounts it at the given `mount_path`.

    A backing file will be created under `/var/lib/vaultlocker/backing_files`,
    in a UUID named file, according to `block_size` and `block_count`
    parameters, which map to `bs` and `count` of the `dd` command.  Note that
    the backing file must be a bit over 16M to allow for the XFS file system
    plus some additional metadata needed for the encryption.  It is not
    recommended to go below the default of 20M (20 blocks, 1M each).

    The `backing_file` parameter can be used to change the location where the
    backing file is created.
    """
    uuid = str(uuid4())
    if backing_file is None:
        backing_file = Path('/var/lib/vaultlocker/backing_files') / uuid
        backing_file.parent.mkdir(parents=True, exist_ok=True)
    else:
        backing_file = Path(backing_file)
        if backing_file.exists():
            raise VaultLockerError('Backing file already exists: {}',
                                   backing_file)

    try:
        # ensure loop devices are enabled
        check_call(['modprobe', 'loop'])
        # create the backing file filled with random data
        check_call(['dd', 'if=/dev/urandom', 'of={}'.format(backing_file),
                    'bs=8M', 'count=4'])
        # claim an unused loop device
        output = check_output(['losetup', '--show', '-f', str(backing_file)])
        device_name = output.decode('utf8').strip()
        # encrypt the new loop device
        encrypt_device(device_name, str(mount_path), uuid)
        # setup the service to ensure loop device is restored after reboot
        (LOOP_ENVS / uuid).write_text(''.join([
            'BACK_FILE={}\n'.format(backing_file),
        ]))
        check_call(['systemctl', 'enable',
                    'vaultlocker-loop@{}.service'.format(uuid)])
    except (CalledProcessError, OSError) as e:
        raise VaultLockerError('Error configuring VaultLocker') from e
