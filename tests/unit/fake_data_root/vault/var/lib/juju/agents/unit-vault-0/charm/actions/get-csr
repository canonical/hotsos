#!/usr/local/sbin/charm-env python3
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

import base64
import os
import sys
from traceback import format_exc

# Load modules from $CHARM_DIR/lib
sys.path.append('lib')

from charms.layer import basic
basic.bootstrap_charm_deps()
basic.init_config_states()

import charmhelpers.core.hookenv as hookenv
import charmhelpers.core.unitdata as unitdata
import charmhelpers.core.host as host

import charm.vault as vault
import charm.vault_pki as vault_pki
import charms.reactive
import reactive.vault_handlers as handlers  # noqa: E402

from charms.reactive.flags import set_flag, clear_flag


def authorize_charm_action(*args):
    """Create a role allowing the charm to perform certain vault actions.
    """
    if not hookenv.is_leader():
        hookenv.action_fail('Please run action on lead unit')
        return
    action_config = hookenv.action_get()
    role_id = vault.setup_charm_vault_access(action_config['token'])
    hookenv.leader_set({vault.CHARM_ACCESS_ROLE_ID: role_id})
    set_flag('secrets.refresh')


def refresh_secrets(*args):
    """Refresh secret_id's and re-issue tokens for secret_id retrieval
    on secrets end-points"""
    if not hookenv.is_leader():
        hookenv.action_fail('Please run action on lead unit')
    set_flag('secrets.refresh')


def get_intermediate_csrs(*args):
    if not hookenv.is_leader():
        hookenv.action_fail('Please run action on lead unit')
        return
    action_config = hookenv.action_get() or {}
    csrs = vault_pki.get_csr(
        ttl=action_config.get('ttl'),
        country=action_config.get('country'),
        common_name=action_config.get('common-name'),
        locality=action_config.get('locality'),
        province=action_config.get('province'),
        organization=action_config.get('organization'),
        organizational_unit=action_config.get('organizational-unit'))
    # We have to clear both the reactive flag, as well as the leadership
    # managed root-ca option, otherwise, we will end up with the flag being
    # reset in the reactive handler after this is run.
    clear_flag('charm.vault.ca.ready')
    hookenv.leader_set(
        {'root-ca': None})
    hookenv.action_set({'output': csrs})


def upload_signed_csr(*args):
    if not hookenv.is_leader():
        hookenv.action_fail('Please run action on lead unit')
        return

    action_config = hookenv.action_get()
    root_ca = action_config.get('root-ca')
    if root_ca:
        hookenv.leader_set(
            {'root-ca': base64.b64decode(root_ca).decode("utf-8")})
    vault_pki.upload_signed_csr(
        base64.b64decode(action_config['pem']).decode("utf-8"),
        allowed_domains=action_config.get('allowed-domains'),
        allow_subdomains=action_config.get('allow-subdomains'),
        enforce_hostnames=action_config.get('enforce-hostnames'),
        allow_any_name=action_config.get('allow-any-name'),
        max_ttl=action_config.get('max-ttl'))
    set_flag('charm.vault.ca.ready')
    set_flag('pki.backend.tuned')
    # reissue any certificates we might previously have provided
    set_flag('certificates.reissue.requested')
    set_flag('certificates.reissue.global.requested')


def generate_root_ca(*args):
    if not hookenv.is_leader():
        hookenv.action_fail('Please run action on lead unit')
        return

    action_config = hookenv.action_get()
    root_ca = vault_pki.generate_root_ca(
        ttl=action_config['ttl'],
        allow_any_name=action_config['allow-any-name'],
        allowed_domains=action_config['allowed-domains'],
        allow_bare_domains=action_config['allow-bare-domains'],
        allow_subdomains=action_config['allow-subdomains'],
        allow_glob_domains=action_config['allow-glob-domains'],
        enforce_hostnames=action_config['enforce-hostnames'],
        max_ttl=action_config['max-ttl'])
    hookenv.leader_set({'root-ca': root_ca})
    hookenv.action_set({'output': root_ca})
    set_flag('charm.vault.ca.ready')
    set_flag('pki.backend.tuned')
    # reissue any certificates we might previously have provided
    set_flag('certificates.reissue.requested')
    set_flag('certificates.reissue.global.requested')


def get_root_ca(*args):
    hookenv.action_set({'output': vault_pki.get_ca()})


def disable_pki(*args):
    if not hookenv.is_leader():
        hookenv.action_fail('Please run action on lead unit')
        return
    vault_pki.disable_pki_backend()
    clear_flag('charm.vault.ca.ready')
    clear_flag('pki.backend.tuned')
    hookenv.leader_set({'root-ca': None})


def reissue_certificates(*args):
    set_flag('certificates.reissue.requested')
    set_flag('certificates.reissue.global.requested')


def pause(args):
    """Pauses the Vault service.

    The result of this action will be to have vault daemon
    stopped. juju will report the unit status as "Blocked, vault
    service not running".

    """
    handlers.pause_vault_unit()


def resume(args):
    """Resumes the Vault service.

    The result of this action will be to have vault daemon
    resumed. User will have to unseal the service. juju will report
    the unit status as "Blocked, unit is sealed".

    """
    handlers.resume_vault_unit()


def restart(args):
    """Restart the Vault service.

    The result of this action will be to have vault daemon
    restarted.
    Mind that this action will cause the Vault to be sealed.

    """
    host.service_restart(service_name='vault')


def reload(args):
    """Reload the Vault service.

    The result of this action will be to have vault daemon
    reloaded (preferably with HUP signal in systemd).
    That allows for live changes in listener (only certs)
    without need of User intervention to unseal the vault.
    Unfortunately other options like disable_mlock, ui
    are not supported.

    """
    host.service_reload(service_name='vault')


# Actions to function mapping, to allow for illegal python action names that
# can map to a python function.
ACTIONS = {
    "authorize-charm": authorize_charm_action,
    "refresh-secrets": refresh_secrets,
    "get-csr": get_intermediate_csrs,
    "upload-signed-csr": upload_signed_csr,
    "reissue-certificates": reissue_certificates,
    "generate-root-ca": generate_root_ca,
    "get-root-ca": get_root_ca,
    "disable-pki": disable_pki,
    "pause": pause,
    "resume": resume,
    "restart": restart,
    "reload": reload
}


def main(args):
    action_name = os.path.basename(args[0])
    try:
        action = ACTIONS[action_name]
    except KeyError:
        return "Action %s undefined" % action_name
    else:
        try:
            action(args)
        except vault.VaultError as e:
            hookenv.action_fail(str(e))
        except Exception:
            exc = format_exc()
            hookenv.log(exc, hookenv.ERROR)
            hookenv.action_fail(exc.splitlines()[-1])
        else:
            # we were successful, so commit changes from the action
            unitdata.kv().flush()
            # try running handlers based on new state
            try:
                charms.reactive.main()
            except Exception:
                exc = format_exc()
                hookenv.log(exc, hookenv.ERROR)
                hookenv.action_fail(exc.splitlines()[-1])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
