# Overview

**WARNING**: This is an unofficial, untested, and experimental layer from
the community.

This interface layer handles the communication between the Ceph Monitor 
and a client that requires an admin key.

# Usage

## Requires

This interface layer will set the following states, as appropriate:

  * `{relation_name}.available` The ceph client has been related to a provider.
  The following accessors will be available:
   - key - The admin cephx key
   - auth - Whether or not strict auth is supported
   - mon_hosts - The public addresses list of the monitor cluster


Client example:

```python
@when('ceph-admin.available')
def ceph_connected(ceph_info):
  charm_ceph_conf = os.path.join(os.sep, 'etc', 'ceph', 'ceph.conf')
  cephx_key = os.path.join(os.sep, 'etc', 'ceph', 'ceph.client.admin.keyring')

  ceph_context = {
      'auth_supported': ceph_client.auth,
      'mon_hosts': ceph_client.mon_hosts,
  }

  with open(charm_ceph_conf, 'w') as cephconf:
    cephconf.write(render_template('ceph.conf', ceph_context))

  # Write out the cephx_key also
  with open(cephx_key, 'w') as cephconf:
    cephconf.write(ceph_client.key)
```
