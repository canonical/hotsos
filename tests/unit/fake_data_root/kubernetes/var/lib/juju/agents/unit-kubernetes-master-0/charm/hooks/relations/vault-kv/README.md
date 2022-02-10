# Overview

This interface handles the communication with the vault charm using the
vault-kv interface type.

Vault will enable simple KV based secrets backends with AppRole based
authentication and policies to allow consuming charms to store and retrieve
secrets in Vault.

Access to the backend will be limited to the network address binding of
of the relation endpoint name and ownership of a secret\_id which the
consuming application must retrieve using a one-shot token out-of-band
from Juju.

# Usage

## Requires

The interface layer will set the following reactive states, as appropriate:

  * `{relation_name}.connected` The relation is established and ready for
    the local charm to make a request for access to a secrets backend using
    the `request_secret_backend` method.

  * `{relation_name}.available` When vault has created the backend and an
    associated AppRole to allow the local charm to store and retrieve secrets
    in vault - the `vault_url` and `unit_role_id` properties will be set.

 For example:

```python
from charms.reactive.flags import endpoint_from_flag

 @when('secrets-storage.connected')
 def ss_connected():
 	secrets = endpoint_from_flag('secrets-storage.connected')
 	secrets.request_secret_backend('charm-vaultlocker', isolated=True)


 @when('secrets-storage.available')
 def ss_ready_for_use():
 	secrets = endpoint_from_flag('secrets-storage.connected')
 	configure_my_local_service(
 		vault_url=secrets.vault_url,
 		role_id=secrets.unit_role_id,
        secret_id=vault.get_response(secrets.unit_token),
 		backend='charm-vaultlocker',
 	)
 ```

 Note that the backend name must be prefixed with 'charm-' otherwise the vault
 charm will skip creation of the secrets backend and associated access.
