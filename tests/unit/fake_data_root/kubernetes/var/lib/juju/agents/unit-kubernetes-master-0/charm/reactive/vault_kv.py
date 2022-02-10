from charmhelpers.core import hookenv, host
from charms.reactive import when_all, when_not, set_flag, clear_flag
from charms.reactive import endpoint_from_flag, register_trigger
from charms.reactive import data_changed

from charms.layer import vault_kv


register_trigger(when_not="vault-kv.connected", clear_flag="layer.vault-kv.ready")
register_trigger(when_not="vault-kv.connected", clear_flag="layer.vault-kv.requested")


@when_all("vault-kv.connected")
@when_not("layer.vault-kv.requested")
def request_vault_access():
    vault = endpoint_from_flag("vault-kv.connected")
    backend_name = vault_kv._get_secret_backend()
    # backend can't be isolated or VaultAppKV won't work; see issue #2
    vault.request_secret_backend(backend_name, isolated=False)
    set_flag("layer.vault-kv.requested")


@when_all("vault-kv.available")
def set_ready():
    try:
        vault_kv.get_vault_config()
    except vault_kv.VaultNotReady:
        clear_flag("layer.vault-kv.ready")
    else:
        set_flag("layer.vault-kv.ready")


@when_all("layer.vault-kv.ready")
def check_config_changed():
    try:
        config = vault_kv.get_vault_config()
    except vault_kv.VaultNotReady:
        return
    else:
        if data_changed("layer.vault-kv.config", config):
            set_flag("layer.vault-kv.config.changed")


def manage_app_kv_flags():
    try:
        app_kv = vault_kv.VaultAppKV()
        for key in app_kv.keys():
            app_kv._manage_flags(key)
    except vault_kv.VaultNotReady:
        vault_kv.VaultAppKV._clear_all_flags()


def update_app_kv_hashes():
    try:
        app_kv = vault_kv.VaultAppKV()
        if app_kv.any_changed():
            if hookenv.is_leader():
                # force hooks to run on non-leader units
                hookenv.leader_set({"vault-kv-nonce": host.pwgen(8)})
            # Update the local unit hashes at successful exit
            app_kv.update_hashes()
    except vault_kv.VaultNotReady:
        return


hookenv.atstart(manage_app_kv_flags)
hookenv.atexit(update_app_kv_hashes)
