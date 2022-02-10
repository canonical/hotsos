# Copyright 2018-2021 Canonical Limited.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
import os

import charmhelpers.contrib.openstack.alternatives as alternatives
import charmhelpers.contrib.openstack.context as context

import charmhelpers.core.hookenv as hookenv
import charmhelpers.core.host as host
import charmhelpers.core.templating as templating
import charmhelpers.core.unitdata as unitdata

VAULTLOCKER_BACKEND = 'charm-vaultlocker'


class VaultKVContext(context.OSContextGenerator):
    """Vault KV context for interaction with vault-kv interfaces"""
    interfaces = ['secrets-storage']

    def __init__(self, secret_backend=None):
        super(context.OSContextGenerator, self).__init__()
        self.secret_backend = (
            secret_backend or 'charm-{}'.format(hookenv.service_name())
        )

    def __call__(self):
        try:
            import hvac
        except ImportError:
            # BUG: #1862085 - if the relation is made to vault, but the
            # 'encrypt' option is not made, then the charm errors with an
            # import warning.  This catches that, logs a warning, and returns
            # with an empty context.
            hookenv.log("VaultKVContext: trying to use hvac pythong module "
                        "but it's not available.  Is secrets-stroage relation "
                        "made, but encrypt option not set?",
                        level=hookenv.WARNING)
            # return an empty context on hvac import error
            return {}
        ctxt = {}
        # NOTE(hopem): see https://bugs.launchpad.net/charm-helpers/+bug/1849323
        db = unitdata.kv()
        # currently known-good secret-id
        secret_id = db.get('secret-id')

        for relation_id in hookenv.relation_ids(self.interfaces[0]):
            for unit in hookenv.related_units(relation_id):
                data = hookenv.relation_get(unit=unit,
                                            rid=relation_id)
                vault_url = data.get('vault_url')
                role_id = data.get('{}_role_id'.format(hookenv.local_unit()))
                token = data.get('{}_token'.format(hookenv.local_unit()))

                if all([vault_url, role_id, token]):
                    token = json.loads(token)
                    vault_url = json.loads(vault_url)

                    # Tokens may change when secret_id's are being
                    # reissued - if so use token to get new secret_id
                    token_success = False
                    try:
                        secret_id = retrieve_secret_id(
                            url=vault_url,
                            token=token
                        )
                        token_success = True
                    except hvac.exceptions.InvalidRequest:
                        # Try next
                        pass

                    if token_success:
                        db.set('secret-id', secret_id)
                        db.flush()

                        ctxt['vault_url'] = vault_url
                        ctxt['role_id'] = json.loads(role_id)
                        ctxt['secret_id'] = secret_id
                        ctxt['secret_backend'] = self.secret_backend
                        vault_ca = data.get('vault_ca')
                        if vault_ca:
                            ctxt['vault_ca'] = json.loads(vault_ca)

                        self.complete = True
                        break
                    else:
                        if secret_id:
                            ctxt['vault_url'] = vault_url
                            ctxt['role_id'] = json.loads(role_id)
                            ctxt['secret_id'] = secret_id
                            ctxt['secret_backend'] = self.secret_backend
                            vault_ca = data.get('vault_ca')
                            if vault_ca:
                                ctxt['vault_ca'] = json.loads(vault_ca)

            if self.complete:
                break

        if ctxt:
            self.complete = True

        return ctxt


def write_vaultlocker_conf(context, priority=100):
    """Write vaultlocker configuration to disk and install alternative

    :param context: Dict of data from vault-kv relation
    :ptype: context: dict
    :param priority: Priority of alternative configuration
    :ptype: priority: int"""
    charm_vl_path = "/var/lib/charm/{}/vaultlocker.conf".format(
        hookenv.service_name()
    )
    host.mkdir(os.path.dirname(charm_vl_path), perms=0o700)
    templating.render(source='vaultlocker.conf.j2',
                      target=charm_vl_path,
                      context=context, perms=0o600),
    alternatives.install_alternative('vaultlocker.conf',
                                     '/etc/vaultlocker/vaultlocker.conf',
                                     charm_vl_path, priority)


def vault_relation_complete(backend=None):
    """Determine whether vault relation is complete

    :param backend: Name of secrets backend requested
    :ptype backend: string
    :returns: whether the relation to vault is complete
    :rtype: bool"""
    try:
        import hvac
    except ImportError:
        return False
    try:
        vault_kv = VaultKVContext(secret_backend=backend or VAULTLOCKER_BACKEND)
        vault_kv()
        return vault_kv.complete
    except hvac.exceptions.InvalidRequest:
        return False


# TODO: contrib a high level unwrap method to hvac that works
def retrieve_secret_id(url, token):
    """Retrieve a response-wrapped secret_id from Vault

    :param url: URL to Vault Server
    :ptype url: str
    :param token: One shot Token to use
    :ptype token: str
    :returns: secret_id to use for Vault Access
    :rtype: str"""
    import hvac
    try:
        # hvac 0.10.1 changed default adapter to JSONAdapter
        client = hvac.Client(url=url, token=token, adapter=hvac.adapters.Request)
    except AttributeError:
        # hvac < 0.6.2 doesn't have adapter but uses the same response interface
        client = hvac.Client(url=url, token=token)
    else:
        # hvac < 0.9.2 assumes adapter is an instance, so doesn't instantiate
        if not isinstance(client.adapter, hvac.adapters.Request):
            client.adapter = hvac.adapters.Request(base_uri=url, token=token)
    response = client._post('/v1/sys/wrapping/unwrap')
    if response.status_code == 200:
        data = response.json()
        return data['data']['secret_id']
