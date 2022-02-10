<h1 id="charms.layer.vault_kv">charms.layer.vault_kv</h1>


<h2 id="charms.layer.vault_kv.VaultNotReady">VaultNotReady</h2>

```python
VaultNotReady(self, /, *args, **kwargs)
```

Exception indicating that Vault was accessed before it was ready.

<h2 id="charms.layer.vault_kv.VaultUnitKV">VaultUnitKV</h2>

```python
VaultUnitKV(self)
```

A simplified interface for storing data in Vault, with the data scoped to
the current unit.

Keys must be strings, but data can be structured as long as it is
JSON-serializable.

This class can be used as a dict, or you can use `self.get` and `self.set`
for a more KV-like interface. When values are set, via either style, they
are immediately persisted to Vault. Values are also cached in memory.

Note: This class is a singleton.

<h2 id="charms.layer.vault_kv.VaultAppKV">VaultAppKV</h2>

```python
VaultAppKV(self)
```

A simplified interface for storing data in Vault, with data shared by every
unit of the application.

Keys must be strings, but data can be structured as long as it is
JSON-serializable.

This class can be used as a dict, or you can use `self.get` and `self.set`
for a more KV-like interface. When values are set, via either style, they
are immediately persisted to Vault. Values are also cached in memory.

Note: This class is a singleton.

<h3 id="charms.layer.vault_kv.VaultAppKV.is_changed">is_changed</h3>

```python
VaultAppKV.is_changed(self, key)
```

Determine if the value for the given key has changed since the last
time `self.update_hashes()` has been called.

In order to detect changes, hashes of the values are also sotred
in Vault.

<h3 id="charms.layer.vault_kv.VaultAppKV.update_hashes">update_hashes</h3>

```python
VaultAppKV.update_hashes(self)
```

Update the hashes in Vault, thus marking all fields as unchanged.

This is done automatically at exit.

<h2 id="charms.layer.vault_kv.get_vault_config">get_vault_config</h2>

```python
get_vault_config()
```

Get the config data needed for this application to access Vault.

This is only needed if you're using another application, such as
VaultLocker, using the secrets backend provided by this layer.

Returns a dictionary containing the following keys:

  * vault_url
  * secret_backend
  * role_id
  * secret_id

Note: This data is cached in [UnitData][] so anything with access to that
could access Vault as this application.

If any of this data changes (such as the secret_id being rotated), this
layer will set the `layer.vault-kv.config.changed` flag.

If this is called before the Vault relation is available, it will raise
`VaultNotReady`.

[UnitData]: https://charm-helpers.readthedocs.io/en/latest/api/charmhelpers.core.unitdata.html

