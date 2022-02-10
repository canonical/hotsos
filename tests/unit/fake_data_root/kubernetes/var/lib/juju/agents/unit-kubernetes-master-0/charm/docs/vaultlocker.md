<h1 id="charms.layer.vaultlocker">charms.layer.vaultlocker</h1>


<h2 id="charms.layer.vaultlocker.encrypt_storage">encrypt_storage</h2>

```python
encrypt_storage(storage_name, mountbase=None)
```

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

<h2 id="charms.layer.vaultlocker.encrypt_device">encrypt_device</h2>

```python
encrypt_device(device, mountpoint=None)
```

Set up encryption for the given block device, and optionally create and
mount an XFS filesystem on the encrypted device.

If ``mountpoint`` is not given, the device will not be formatted or
mounted.  When interacting with or mounting the device manually, the
name returned by :func:`decrypted_device` called on the device name
should be used in place of the raw device name.

<h2 id="charms.layer.vaultlocker.decrypted_device">decrypted_device</h2>

```python
decrypted_device(device)
```

Returns the mapped device name for the decrypted version of the encrypted
device.

This mapped device name is what should be used for mounting the device.

