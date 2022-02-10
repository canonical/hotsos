# Copyright 2018 Canonical Ltd
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

import functools
import json
import requests

import hvac
import tenacity

from charmhelpers.contrib.network.ip import (
    is_address_in_network,
    resolve_network_cidr,
)
import charmhelpers.core.hookenv as hookenv
import charmhelpers.core.host as host
import charms.reactive

CHARM_ACCESS_ROLE = 'local-charm-access'
CHARM_ACCESS_ROLE_ID = 'local-charm-access-id'
CHARM_POLICY_NAME = 'local-charm-policy'
CHARM_POLICY = """
# Allow managment of policies starting with charm- prefix
path "sys/policy/charm-*" {
  capabilities = ["create", "read", "update", "delete"]
}

# Allow discovery of all policies
path "sys/policy/" {
  capabilities = ["list"]
}

# Allow management of approle's with charm- prefix
path "auth/approle/role/charm-*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}

# Allow discovery of approles
path "auth/approle/role" {
  capabilities = ["read"]
}
path "auth/approle/role/" {
  capabilities = ["list"]
}

# Allow charm- prefixes secrets backends to be mounted and managed
path "sys/mounts/charm-*" {
  capabilities = ["create", "read", "update", "delete", "sudo"]
}

# Allow charm- prefixes pki backends to be used
path "charm-pki-*" {
  capabilities = ["create", "read", "update", "delete", "list", "sudo"]
}

# Allow discovery of secrets backends
path "sys/mounts" {
  capabilities = ["read"]
}
path "sys/mounts/" {
  capabilities = ["list"]
}"""

SECRET_BACKEND_HCL = """
path "{backend}/{hostname}/*" {{
  capabilities = ["create", "read", "update", "delete", "list"]
}}
path "sys/internal/ui/mounts/{backend}" {{
  capabilities = ["read"]
}}
"""

SECRET_BACKEND_SHARED_HCL = """
path "{backend}/*" {{
  capabilities = ["create", "read", "update", "delete", "list"]
}}
path "sys/internal/ui/mounts/{backend}" {{
  capabilities = ["read"]
}}
"""
VAULT_LOCALHOST_URL = "http://127.0.0.1:8220"
VAULT_HEALTH_URL = '{vault_addr}/v1/sys/health'


class VaultError(Exception):
    """
    Exception raised for Vault errors.
    """
    pass


class VaultNotReady(VaultError):
    """
    Exception raised for units in error state
    """

    def __init__(self, reason):
        message = "Vault is not ready ({})".format(reason)
        super(VaultNotReady, self).__init__(message)


class VaultInvalidRequest(VaultError):
    """
    Exception raised if a cert request can't be fulfilled.
    """
    pass


def binding_address(binding):
    try:
        return hookenv.network_get_primary_address(binding)
    except NotImplementedError:
        return hookenv.unit_private_ip()


def get_vault_url(binding, port, address=None):
    protocol = 'http'
    ip = address or binding_address(binding)
    if ':' in ip:
        ip = '[{}]'.format(ip)
    if charms.reactive.is_state('vault.ssl.available'):
        protocol = 'https'
    return '{}://{}:{}'.format(protocol, ip, port)


get_api_url = functools.partial(get_vault_url,
                                binding='access', port=8200)
get_cluster_url = functools.partial(get_vault_url,
                                    binding='cluster', port=8201)


def get_vip(binding=None):
    vip = hookenv.config('vip')
    if not vip:
        return None

    vips = vip.split()
    if len(vips) == 1:
        return vips[0]

    if not binding:
        binding = 'access'

    bound_cidr = resolve_network_cidr(
        binding_address(binding)
    )
    for vip in vips:
        if is_address_in_network(bound_cidr, vip):
            return vip

    return None


def get_access_address():
    protocol = 'http'
    addr = hookenv.config('dns-ha-access-record')
    addr = addr or get_vip('access')
    addr = addr or binding_address('access')
    if ':' in addr:
        addr = '[{}]'.format(addr)
    if charms.reactive.is_state('vault.ssl.available'):
        protocol = 'https'
    return '{}://{}:{}'.format(protocol, addr, 8200)


def enable_approle_auth(client):
    """Enable the approle auth method within vault

    :param client: Vault client
    :type client: hvac.Client"""
    if 'approle/' not in client.list_auth_backends():
        client.enable_auth_backend('approle')


def create_local_charm_access_role(client, policies):
    """Create a role within vault associating the supplied policies

    :param client: Vault client
    :type client: hvac.Client
    :param policies: List of policy names
    :type policies: [str, str, ...]
    :returns: Id of created role
    :rtype: str"""
    client.create_role(
        CHARM_ACCESS_ROLE,
        token_ttl='60s',
        token_max_ttl='60s',
        policies=policies,
        bind_secret_id='false',
        bound_cidr_list='127.0.0.1/32')
    return client.get_role_id(CHARM_ACCESS_ROLE)


def setup_charm_vault_access(token=None):
    """Create policies and role. Grant role to charm.

    :param token: Token to use to authenticate with vault
    :type token: str
    :returns: Id of created role
    :rtype: str"""
    if not token:
        token = hookenv.leader_get('root_token')
    client = hvac.Client(
        url=VAULT_LOCALHOST_URL,
        token=token)
    enable_approle_auth(client)
    policies = [CHARM_POLICY_NAME]
    client.set_policy(CHARM_POLICY_NAME, CHARM_POLICY)
    return create_local_charm_access_role(client, policies=policies)


def get_local_charm_access_role_id():
    """Retrieve the id of the role for local charm access

    :returns: Id of local charm access role
    :rtype: str
    """
    return hookenv.leader_get(CHARM_ACCESS_ROLE_ID)


def get_client(url=None):
    """Provide a client for talking to the vault api

    :returns: vault client
    :rtype: hvac.Client
    """
    return hvac.Client(url=url or get_api_url())


@tenacity.retry(wait=tenacity.wait_exponential(multiplier=1, max=60),
                stop=tenacity.stop_after_attempt(8),
                retry=tenacity.retry_if_exception_type(
                    hvac.exceptions.InternalServerError),
                reraise=True)
def get_local_client():
    """Provide a client for talking to the vault api

    :returns: vault client
    :rtype: hvac.Client
    """
    client = get_client(url=VAULT_LOCALHOST_URL)
    app_role_id = get_local_charm_access_role_id()
    if not app_role_id:
        hookenv.log('Could not retrieve app_role_id', level=hookenv.DEBUG)
        raise VaultNotReady("Cannot initialise local client")
    client = hvac.Client(url=VAULT_LOCALHOST_URL)
    client.auth_approle(app_role_id)
    return client


@tenacity.retry(wait=tenacity.wait_exponential(multiplier=1, max=60),
                stop=tenacity.stop_after_attempt(10),
                reraise=True)
def get_vault_health():
    """Query vault to retrieve health

    :returns: Vault health
    :rtype: dict
    """
    response = requests.get(
        VAULT_HEALTH_URL.format(vault_addr=VAULT_LOCALHOST_URL))
    return response.json()


def opportunistic_restart():
    """Restart vault if possible"""
    if can_restart():
        hookenv.log("Restarting vault", level=hookenv.DEBUG)
        host.service_restart('vault')
    else:
        hookenv.log("Starting vault", level=hookenv.DEBUG)
        host.service_start('vault')


def prepare_vault():
    """Setup vault as much as possible

    Attempt to prepare vault for operation. Where possible, initialise, unseal
    and create role for local charm access to vault.
    """
    if not host.service_running('vault'):
        hookenv.log("Defering unlock vault not running ", level=hookenv.DEBUG)
        return
    vault_health = get_vault_health()
    if not vault_health['initialized'] and hookenv.is_leader():
        initialize_vault()
    if vault_health['sealed'] and hookenv.leader_get('keys'):
        unseal_vault()
    if hookenv.is_leader():
        role_id = setup_charm_vault_access()
        hookenv.leader_set({CHARM_ACCESS_ROLE_ID: role_id})


def initialize_vault(shares=1, threshold=1):
    """Initialise vault

    Initialise vault and store the resulting key(s) and token in the leader db.
    :param shares: Number of shares to create
    :type shares: int
    :param threshold: Minimum number of shares needed to unlock
    :type threshold: int
    """
    client = get_client(url=VAULT_LOCALHOST_URL)
    result = client.initialize(shares, threshold)
    client.token = result['root_token']
    hookenv.leader_set(
        root_token=result['root_token'],
        keys=json.dumps(result['keys']))


def unseal_vault(keys=None):
    """Unseal vault with provided keys. If no keys are provided retrieve from
    leader db"""
    client = get_client(url=VAULT_LOCALHOST_URL)
    if not keys:
        keys = json.loads(hookenv.leader_get()['keys'])
    for key in keys:
        client.unseal(key)


def can_restart():
    """Check if vault can be restarted

    :returns: Can vault be restarted
    :rtype: bool
    """
    safe_restart = False
    if not host.service_running('vault'):
        safe_restart = True
    elif hookenv.config('totally-unsecure-auto-unlock'):
        safe_restart = True
    else:
        client = get_client(url=VAULT_LOCALHOST_URL)
        if not client.is_initialized():
            safe_restart = True
        elif client.is_sealed():
            safe_restart = True
    hookenv.log(
        "Safe to restart: {}".format(safe_restart),
        level=hookenv.DEBUG)
    return safe_restart


def configure_secret_backend(client, name):
    """Ensure a KV backend is enabled

    :param client: Vault client
    :ptype client: hvac.Client
    :param name: Name of backend to enable
    :ptype name: str"""
    if '{}/'.format(name) not in client.list_secret_backends():
        client.enable_secret_backend(backend_type='kv',
                                     description='Charm created KV backend',
                                     mount_point=name,
                                     options={'version': 1})


def configure_policy(client, name, hcl):
    """Create/update a role within vault associating the supplied policies

    :param client: Vault client
    :ptype client: hvac.Client
    :param name: Name of policy to create
    :ptype name: str
    :param hcl: Vault policy HCL
    :ptype hcl: str"""
    client.set_policy(name, hcl)


def configure_approle(client, name, cidr, policies):
    """Create/update a role within vault associating the supplied policies

    :param client: Vault client
    :ptype client: hvac.Client
    :param name: Name of role
    :ptype name: str
    :param cidr: Network address of remote unit
    :ptype cidr: str
    :param policies: List of policy names
    :ptype policies: [str, str, ...]
    :returns: Id of created role
    :rtype: str"""
    client.create_role(
        name,
        token_ttl='60s',
        token_max_ttl='60s',
        policies=policies,
        bind_secret_id='true',
        bound_cidr_list=cidr)
    return client.get_role_id(name)


def generate_role_secret_id(client, name, cidr):
    """Generate a new secret_id for an AppRole

    :param client: Vault client
    :ptype client: hvac.Client
    :param name: Name of role
    :ptype name: str
    :param cidr: Network address of remote unit
    :ptype cidr: str
    :returns: Vault token to retrieve the response-wrapped response
    :rtype: str"""
    response = client.write('auth/approle/role/{}/secret-id'.format(name),
                            wrap_ttl='1h', cidr_list=cidr)
    return response['wrap_info']['token']


def is_backend_mounted(client, name):
    """Check if the supplied backend is mounted

    :returns: Whether mount point is in use
    :rtype: bool
    """
    return '{}/'.format(name) in client.list_secret_backends()


def vault_ready_for_clients():
    """Check if vault is ready to recieve client requests"""
    @tenacity.retry(wait=tenacity.wait_exponential(multiplier=1, max=10),
                    stop=tenacity.stop_after_attempt(10),
                    reraise=True)
    def _check_vault_status(client):
        if (not host.service_running('vault') or
                not client.is_initialized() or
                client.is_sealed()):
            return False
        return True

    # NOTE: use localhost listener as policy only allows 127.0.0.1 to
    #       administer the local vault instances via the charm
    client = get_client(url=VAULT_LOCALHOST_URL)

    status_ok = _check_vault_status(client)
    if status_ok:
        return True
    else:
        return False
