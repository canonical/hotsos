#!/usr/local/sbin/charm-env python3

# Copyright 2015 The Kubernetes Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import base64
import os
import re
import socket
import json
import traceback
import yaml

from itertools import filterfalse
from shutil import move, copyfile
from pathlib import Path
from subprocess import check_call
from subprocess import check_output
from subprocess import CalledProcessError
from urllib.request import Request, urlopen

import charms.coordinator
from charms.layer import snap
from charms.leadership import leader_get, leader_set
from charms.reactive import hook
from charms.reactive import remove_state, clear_flag
from charms.reactive import set_state, set_flag
from charms.reactive import is_state, is_flag_set, get_unset_flags
from charms.reactive import endpoint_from_flag, endpoint_from_name
from charms.reactive import when, when_any, when_not, when_none
from charms.reactive import register_trigger
from charms.reactive import data_changed, any_file_changed

from charms.layer import tls_client
from charms.layer import vaultlocker
from charms.layer import vault_kv

from charmhelpers.core import hookenv
from charmhelpers.core import host
from charmhelpers.core import unitdata
from charmhelpers.core.host import restart_on_change
from charmhelpers.core.host import service_pause, service_resume, service_stop
from charmhelpers.core.templating import render
from charmhelpers.contrib.charmsupport import nrpe

from charms.layer import kubernetes_master
from charms.layer import kubernetes_common

from charms.layer.hacluster import add_service_to_hacluster
from charms.layer.hacluster import remove_service_from_hacluster
from charms.layer.kubernetes_common import kubeclientconfig_path
from charms.layer.kubernetes_common import migrate_resource_checksums
from charms.layer.kubernetes_common import check_resources_for_upgrade_needed
from charms.layer.kubernetes_common import (
    calculate_and_store_resource_checksums,
)  # noqa
from charms.layer.kubernetes_common import arch
from charms.layer.kubernetes_common import service_restart
from charms.layer.kubernetes_common import get_ingress_address
from charms.layer.kubernetes_common import get_ingress_address6
from charms.layer.kubernetes_common import create_kubeconfig
from charms.layer.kubernetes_common import get_service_ip
from charms.layer.kubernetes_common import configure_kubernetes_service
from charms.layer.kubernetes_common import cloud_config_path
from charms.layer.kubernetes_common import encryption_config_path
from charms.layer.kubernetes_common import write_gcp_snap_config
from charms.layer.kubernetes_common import generate_openstack_cloud_config
from charms.layer.kubernetes_common import write_azure_snap_config
from charms.layer.kubernetes_common import configure_kube_proxy
from charms.layer.kubernetes_common import kubeproxyconfig_path
from charms.layer.kubernetes_common import get_version
from charms.layer.kubernetes_common import retry
from charms.layer.kubernetes_common import ca_crt_path
from charms.layer.kubernetes_common import server_crt_path
from charms.layer.kubernetes_common import server_key_path
from charms.layer.kubernetes_common import client_crt_path
from charms.layer.kubernetes_common import client_key_path
from charms.layer.kubernetes_common import kubectl, kubectl_manifest, kubectl_success
from charms.layer.kubernetes_common import _get_vmware_uuid

from charms.layer.nagios import install_nagios_plugin_from_file
from charms.layer.nagios import remove_nagios_plugin


# Override the default nagios shortname regex to allow periods, which we
# need because our bin names contain them (e.g. 'snap.foo.daemon'). The
# default regex in charmhelpers doesn't allow periods, but nagios itself does.
nrpe.Check.shortname_re = r"[\.A-Za-z0-9-_]+$"

snap_resources = [
    "kubectl",
    "kube-apiserver",
    "kube-controller-manager",
    "kube-scheduler",
    "cdk-addons",
    "kube-proxy",
]

master_services = [
    "kube-apiserver",
    "kube-controller-manager",
    "kube-scheduler",
    "kube-proxy",
]

cohort_snaps = snap_resources + ["kubelet"]


os.environ["PATH"] += os.pathsep + os.path.join(os.sep, "snap", "bin")
db = unitdata.kv()
checksum_prefix = "kubernetes-master.resource-checksums."
configure_prefix = "kubernetes-master.prev_args."
keystone_root = "/root/cdk/keystone"
keystone_policy_path = os.path.join(keystone_root, "keystone-policy.yaml")
kubecontrollermanagerconfig_path = "/root/cdk/kubecontrollermanagerconfig"
kubeschedulerconfig_path = "/root/cdk/kubeschedulerconfig"
cdk_addons_kubectl_config_path = "/root/cdk/cdk_addons_kubectl_config"
kubernetes_logs = "/var/log/kubernetes/"
aws_iam_webhook = "/root/cdk/aws-iam-webhook.yaml"
auth_webhook_root = "/root/cdk/auth-webhook"
auth_webhook_conf = os.path.join(auth_webhook_root, "auth-webhook-conf.yaml")
auth_webhook_exe = os.path.join(auth_webhook_root, "auth-webhook.py")
auth_webhook_svc_name = "cdk.master.auth-webhook"
auth_webhook_svc = "/etc/systemd/system/{}.service".format(auth_webhook_svc_name)


register_trigger(
    when="endpoint.aws.ready", set_flag="kubernetes-master.aws.changed"  # when set
)
register_trigger(
    when_not="endpoint.aws.ready",  # when cleared
    set_flag="kubernetes-master.aws.changed",
)
register_trigger(
    when="endpoint.azure.ready", set_flag="kubernetes-master.azure.changed"  # when set
)
register_trigger(
    when_not="endpoint.azure.ready",  # when cleared
    set_flag="kubernetes-master.azure.changed",
)
register_trigger(
    when="endpoint.gcp.ready", set_flag="kubernetes-master.gcp.changed"  # when set
)
register_trigger(
    when_not="endpoint.gcp.ready",  # when cleared
    set_flag="kubernetes-master.gcp.changed",
)
register_trigger(
    when="kubernetes-master.ceph.configured", set_flag="cdk-addons.reconfigure"
)
register_trigger(
    when_not="kubernetes-master.ceph.configured", set_flag="cdk-addons.reconfigure"
)
register_trigger(
    when="keystone-credentials.available", set_flag="cdk-addons.reconfigure"
)
register_trigger(
    when_not="keystone-credentials.available", set_flag="cdk-addons.reconfigure"
)
register_trigger(
    when="kubernetes-master.aws.changed", set_flag="cdk-addons.reconfigure"
)
register_trigger(
    when="kubernetes-master.azure.changed", set_flag="cdk-addons.reconfigure"
)
register_trigger(
    when="kubernetes-master.gcp.changed", set_flag="cdk-addons.reconfigure"
)
register_trigger(
    when="kubernetes-master.openstack.changed", set_flag="cdk-addons.reconfigure"
)
register_trigger(
    when_not="cni.available", clear_flag="kubernetes-master.components.started"
)
register_trigger(
    when="kube-control.requests.changed", clear_flag="authentication.setup"
)
register_trigger(
    when_not="kubernetes-master.apiserver.configured",
    clear_flag="kubernetes-master.apiserver.running",
)


def set_upgrade_needed(forced=False):
    set_state("kubernetes-master.upgrade-needed")
    config = hookenv.config()
    previous_channel = config.previous("channel")
    require_manual = config.get("require-manual-upgrade")
    hookenv.log("set upgrade needed")
    if previous_channel is None or not require_manual or forced:
        hookenv.log("forcing upgrade")
        set_state("kubernetes-master.upgrade-specified")


@when("config.changed.channel")
def channel_changed():
    set_upgrade_needed()


def maybe_install_kube_proxy():
    if not snap.is_installed("kube-proxy"):
        channel = hookenv.config("channel")
        hookenv.status_set("maintenance", "Installing kube-proxy snap")
        snap.install("kube-proxy", channel=channel, classic=True)
        calculate_and_store_resource_checksums(checksum_prefix, snap_resources)


@hook("install")
def fresh_install():
    # fresh installs should always send the unique cluster tag to cdk-addons
    set_state("kubernetes-master.cdk-addons.unique-cluster-tag")


@hook("upgrade-charm")
def check_for_upgrade_needed():
    """An upgrade charm event was triggered by Juju, react to that here."""
    hookenv.status_set("maintenance", "Checking resources")
    is_leader = is_state("leadership.is_leader")

    # migrate to new flags
    if is_state("kubernetes-master.restarted-for-cloud"):
        remove_state("kubernetes-master.restarted-for-cloud")
        set_state("kubernetes-master.cloud.ready")
    if is_state("kubernetes-master.cloud-request-sent"):
        # minor change, just for consistency
        remove_state("kubernetes-master.cloud-request-sent")
        set_state("kubernetes-master.cloud.request-sent")

    # ceph-storage.configured flag no longer exists
    remove_state("ceph-storage.configured")

    # reconfigure ceph. we need this in case we're reverting from ceph-csi back
    # to old ceph on Kubernetes 1.10 or 1.11
    remove_state("kubernetes-master.ceph.configured")

    maybe_install_kube_proxy()
    update_certificates()
    switch_auth_mode(forced=True)

    # File-based auth is gone in 1.19; ensure any entries in basic_auth.csv are
    # added to known_tokens.csv, and any known_tokens entries are created as secrets.
    if not is_flag_set("kubernetes-master.basic-auth.migrated"):
        if kubernetes_master.migrate_auth_file(kubernetes_master.AUTH_BASIC_FILE):
            set_flag("kubernetes-master.basic-auth.migrated")
        else:
            hookenv.log(
                "Unable to migrate {} to {}".format(
                    kubernetes_master.AUTH_BASIC_FILE,
                    kubernetes_master.AUTH_TOKENS_FILE,
                )
            )
    if not is_flag_set("kubernetes-master.token-auth.migrated"):
        register_auth_webhook()
        add_rbac_roles()
        if kubernetes_master.migrate_auth_file(kubernetes_master.AUTH_TOKENS_FILE):
            set_flag("kubernetes-master.token-auth.migrated")
        else:
            hookenv.log(
                "Unable to migrate {} to Kubernetes secrets".format(
                    kubernetes_master.AUTH_TOKENS_FILE
                )
            )
    set_state("reconfigure.authentication.setup")
    remove_state("authentication.setup")

    if not db.get("snap.resources.fingerprint.initialised"):
        # We are here on an upgrade from non-rolling master
        # Since this upgrade might also include resource updates eg
        # juju upgrade-charm kubernetes-master --resource kube-any=my.snap
        # we take no risk and forcibly upgrade the snaps.
        # Forcibly means we do not prompt the user to call the upgrade action.
        set_upgrade_needed(forced=True)

    migrate_resource_checksums(checksum_prefix, snap_resources)
    if check_resources_for_upgrade_needed(checksum_prefix, snap_resources):
        set_upgrade_needed()

    # Set the auto storage backend to etcd2.
    auto_storage_backend = leader_get("auto_storage_backend")
    if not auto_storage_backend and is_leader:
        leader_set(auto_storage_backend="etcd2")

    if is_leader and not leader_get("auto_dns_provider"):
        was_kube_dns = hookenv.config().previous("enable-kube-dns")
        if was_kube_dns is True:
            leader_set(auto_dns_provider="kube-dns")
        elif was_kube_dns is False:
            leader_set(auto_dns_provider="none")

    if is_flag_set("nrpe-external-master.available"):
        update_nrpe_config()

    remove_state("kubernetes-master.system-monitoring-rbac-role.applied")


@hook("pre-series-upgrade")
def pre_series_upgrade():
    """Stop the kubernetes master services"""
    for service in master_services:
        service_pause("snap.%s.daemon" % service)


@hook("post-series-upgrade")
def post_series_upgrade():
    for service in master_services:
        service_resume("snap.%s.daemon" % service)
    # set ourselves up to restart
    remove_state("kubernetes-master.components.started")


@hook("leader-elected")
def leader_elected():
    clear_flag("authentication.setup")


def add_rbac_roles():
    """Update the known_tokens file with proper groups.

    DEPRECATED: Once known_tokens are migrated, group data will be stored in K8s
    secrets. Do not use this function after migrating to authn with secrets.
    """
    if is_flag_set("kubernetes-master.token-auth.migrated"):
        hookenv.log("Known tokens have migrated to secrets. Skipping group changes")
        return
    tokens_fname = "/root/cdk/known_tokens.csv"
    tokens_backup_fname = "/root/cdk/known_tokens.csv.backup"
    move(tokens_fname, tokens_backup_fname)
    with open(tokens_fname, "w") as ftokens:
        with open(tokens_backup_fname, "r") as stream:
            for line in stream:
                if line.startswith("#"):
                    continue
                record = line.strip().split(",")
                try:
                    # valid line looks like: token,username,user,groups
                    if record[2] == "admin" and len(record) == 3:
                        towrite = '{0},{1},{2},"{3}"\n'.format(
                            record[0], record[1], record[2], "system:masters"
                        )
                        ftokens.write(towrite)
                        continue
                    if record[2] == "kube_proxy":
                        towrite = "{0},{1},{2}\n".format(
                            record[0], "system:kube-proxy", "kube-proxy"
                        )
                        ftokens.write(towrite)
                        continue
                    if record[2] == "kube_controller_manager":
                        towrite = "{0},{1},{2}\n".format(
                            record[0],
                            "system:kube-controller-manager",
                            "kube-controller-manager",
                        )
                        ftokens.write(towrite)
                        continue
                    if record[2] == "kubelet" and record[1] == "kubelet":
                        continue
                except IndexError:
                    msg = "Skipping invalid line from {}: {}".format(
                        tokens_backup_fname, line
                    )
                    hookenv.log(msg, level=hookenv.DEBUG)
                    continue
                else:
                    ftokens.write("{}".format(line))


@when("kubernetes-master.upgrade-specified")
def do_upgrade():
    install_snaps()
    remove_state("kubernetes-master.upgrade-needed")
    remove_state("kubernetes-master.upgrade-specified")


def install_snaps():
    channel = hookenv.config("channel")
    hookenv.status_set("maintenance", "Installing core snap")
    snap.install("core")
    hookenv.status_set("maintenance", "Installing kubectl snap")
    snap.install("kubectl", channel=channel, classic=True)
    hookenv.status_set("maintenance", "Installing kube-apiserver snap")
    snap.install("kube-apiserver", channel=channel)
    hookenv.status_set("maintenance", "Installing kube-controller-manager snap")
    snap.install("kube-controller-manager", channel=channel)
    hookenv.status_set("maintenance", "Installing kube-scheduler snap")
    snap.install("kube-scheduler", channel=channel)
    hookenv.status_set("maintenance", "Installing cdk-addons snap")
    snap.install("cdk-addons", channel=channel)
    hookenv.status_set("maintenance", "Installing kube-proxy snap")
    snap.install("kube-proxy", channel=channel, classic=True)
    calculate_and_store_resource_checksums(checksum_prefix, snap_resources)
    db.set("snap.resources.fingerprint.initialised", True)
    set_state("kubernetes-master.snaps.installed")
    remove_state("kubernetes-master.components.started")


@when("kubernetes-master.snaps.installed", "leadership.is_leader")
@when_not("leadership.set.cohort_keys")
def create_or_update_cohort_keys():
    cohort_keys = {}
    for snapname in cohort_snaps:
        cohort_key = snap.create_cohort_snapshot(snapname)
        cohort_keys[snapname] = cohort_key
    leader_set(cohort_keys=json.dumps(cohort_keys))
    hookenv.log("Snap cohort keys have been created.", level=hookenv.INFO)

    # Prime revision info so we can detect changes later
    cohort_revs = kubernetes_master.get_snap_revs(cohort_snaps)
    data_changed("leader-cohort-revs", cohort_revs)
    hookenv.log(
        "Tracking cohort revisions: {}".format(cohort_revs), level=hookenv.DEBUG
    )


@when(
    "kubernetes-master.snaps.installed",
    "leadership.is_leader",
    "leadership.set.cohort_keys",
)
def check_cohort_updates():
    cohort_revs = kubernetes_master.get_snap_revs(cohort_snaps)
    if cohort_revs and data_changed("leader-cohort-revs", cohort_revs):
        leader_set(cohort_keys=None)
        hookenv.log("Snap cohort revisions have changed.", level=hookenv.INFO)


@when("kubernetes-master.snaps.installed", "leadership.set.cohort_keys")
@when_none("coordinator.granted.cohort", "coordinator.requested.cohort")
def safely_join_cohort():
    """Coordinate the rollout of snap refreshes.

    When cohort keys change, grab a lock so that only 1 unit in the
    application joins the new cohort at a time. This allows us to roll out
    snap refreshes without risking all units going down at once.
    """
    cohort_keys = leader_get("cohort_keys")
    # NB: initial data-changed is always true
    if data_changed("leader-cohorts", cohort_keys):
        clear_flag("kubernetes-master.cohorts.joined")
        clear_flag("kubernetes-master.cohorts.sent")
        charms.coordinator.acquire("cohort")


@when(
    "kubernetes-master.snaps.installed",
    "leadership.set.cohort_keys",
    "coordinator.granted.cohort",
)
@when_not("kubernetes-master.cohorts.joined")
def join_or_update_cohorts():
    """Join or update a cohort snapshot.

    All units of this application (leader and followers) need to refresh their
    installed snaps to the current cohort snapshot.
    """
    cohort_keys = json.loads(leader_get("cohort_keys"))
    for snapname in cohort_snaps:
        cohort_key = cohort_keys[snapname]
        if snap.is_installed(snapname):  # we also manage workers' cohorts
            hookenv.status_set("maintenance", "Joining snap cohort.")
            snap.join_cohort_snapshot(snapname, cohort_key)
    set_flag("kubernetes-master.cohorts.joined")
    hookenv.log("{} has joined the snap cohort".format(hookenv.local_unit()))


@when(
    "kubernetes-master.snaps.installed",
    "leadership.set.cohort_keys",
    "kubernetes-master.cohorts.joined",
    "kube-control.connected",
)
@when_not("kubernetes-master.cohorts.sent")
def send_cohorts():
    """Send cohort information to workers.

    If we have peers, wait until all peers are updated before sending.
    Otherwise, we're a single unit k8s-master and can fire when connected.
    """
    cohort_keys = json.loads(leader_get("cohort_keys"))
    kube_control = endpoint_from_flag("kube-control.connected")
    kube_masters = endpoint_from_flag("kube-masters.connected")

    # If we have peers, tell them we've joined the cohort. This is needed so
    # we don't tell workers about cohorts until all masters are in-sync.
    goal_peers = len(list(hookenv.expected_peer_units()))
    if goal_peers > 0:
        if kube_masters:
            # tell peers about the cohort keys
            kube_masters.set_cohort_keys(cohort_keys)
        else:
            msg = "Waiting for {} peers before setting the cohort.".format(goal_peers)
            hookenv.log(msg, level=hookenv.DEBUG)
            return

        if is_flag_set("kube-masters.cohorts.ready"):
            # tell workers about the cohort keys
            kube_control.set_cohort_keys(cohort_keys)
            hookenv.log(
                "{} (peer) sent cohort keys to workers".format(hookenv.local_unit())
            )
        else:
            msg = "Waiting for k8s-masters to agree on cohorts."
            hookenv.log(msg, level=hookenv.DEBUG)
            return
    else:
        # tell workers about the cohort keys
        kube_control.set_cohort_keys(cohort_keys)
        hookenv.log(
            "{} (single) sent cohort keys to workers".format(hookenv.local_unit())
        )

    set_flag("kubernetes-master.cohorts.sent")


@when("etcd.available")
@when("config.changed.enable-metrics")
def enable_metric_changed():
    """
    Trigger an api server update.

    :return: None
    """
    clear_flag("kubernetes-master.apiserver.configured")

    if is_state("leadership.is_leader"):
        configure_cdk_addons()


@when("config.changed.client_password", "leadership.is_leader")
def password_changed():
    """Handle password change by reconfiguring authentication."""
    remove_state("authentication.setup")


@when("config.changed.storage-backend")
def storage_backend_changed():
    remove_state("kubernetes-master.components.started")


@when("leadership.is_leader")
@when_not("authentication.setup")
def setup_leader_authentication():
    """
    Setup service accounts and tokens for the cluster.

    As of 1.19 charms, this will also propogate a generic basic_auth.csv, which is
    merged into known_tokens.csv, which are migrated to secrets during upgrade-charm.
    """
    basic_auth = "/root/cdk/basic_auth.csv"
    known_tokens = "/root/cdk/known_tokens.csv"
    service_key = "/root/cdk/serviceaccount.key"
    os.makedirs("/root/cdk", exist_ok=True)

    hookenv.status_set("maintenance", "Rendering authentication templates.")

    keys = [basic_auth, known_tokens, service_key]
    # Try first to fetch data from an old leadership broadcast.
    if not get_keys_from_leader(keys) or is_state("reconfigure.authentication.setup"):
        kubernetes_master.deprecate_auth_file(basic_auth)
        set_flag("kubernetes-master.basic-auth.migrated")

        kubernetes_master.deprecate_auth_file(known_tokens)
        set_flag("kubernetes-master.token-auth.migrated")

        # Generate the default service account token key
        if not os.path.isfile(service_key):
            cmd = ["openssl", "genrsa", "-out", service_key, "2048"]
            check_call(cmd)
        remove_state("reconfigure.authentication.setup")

    # Write the admin token every time we setup authn to ensure we honor a
    # configured password.
    client_pass = hookenv.config("client_password") or get_token("admin")
    setup_tokens(client_pass, "admin", "admin", "system:masters")

    create_tokens_and_sign_auth_requests()

    # send auth files to followers via leadership data
    leader_data = {}
    for f in [basic_auth, known_tokens, service_key]:
        try:
            with open(f, "r") as fp:
                leader_data[f] = fp.read()
        except FileNotFoundError:
            pass

    # this is slightly opaque, but we are sending file contents under its file
    # path as a key.
    # eg:
    # {'/root/cdk/serviceaccount.key': 'RSA:2471731...'}
    leader_set(leader_data)

    remove_state("kubernetes-master.components.started")
    remove_state("kube-control.requests.changed")
    set_state("authentication.setup")


@when_not("leadership.is_leader")
def setup_non_leader_authentication():
    basic_auth = "/root/cdk/basic_auth.csv"
    known_tokens = "/root/cdk/known_tokens.csv"
    service_key = "/root/cdk/serviceaccount.key"

    # Starting with 1.19, we don't use csv auth files; handle changing secrets.
    secrets = {
        "admin": get_token("admin"),
        "kube-controller-manager": get_token("system:kube-controller-manager"),
        "kube-proxy": get_token("system:kube-proxy"),
        "kube-scheduler": get_token("system:kube-scheduler"),
    }
    if data_changed("secrets-data", secrets):
        set_flag("kubernetes-master.token-auth.migrated")
        build_kubeconfig()
        remove_state("kubernetes-master.components.started")

    keys = [basic_auth, known_tokens, service_key]
    # Pre-secrets, the source of truth for non-leaders is the leader.
    # Therefore we overwrite_local with whatever the leader has.
    if not get_keys_from_leader(keys, overwrite_local=True):
        # the keys were not retrieved. Non-leaders have to retry.
        return

    if any_file_changed(keys):
        remove_state("kubernetes-master.components.started")

    # Clear stale creds from the kube-control relation so that the leader can
    # assume full control of them.
    kube_control = endpoint_from_flag("kube-control.connected")
    if kube_control:
        kube_control.clear_creds()

    remove_state("kube-control.requests.changed")
    set_state("authentication.setup")


def get_keys_from_leader(keys, overwrite_local=False):
    """
    Gets the broadcasted keys from the leader and stores them in
    the corresponding files.

    Args:
        keys: list of keys. Keys are actually files on the FS.

    Returns: True if all key were fetched, False if not.

    """
    # This races with other codepaths, and seems to require being created first
    # This block may be extracted later, but for now seems to work as intended
    os.makedirs("/root/cdk", exist_ok=True)

    for k in keys:
        # If the path does not exist, assume we need it
        if not os.path.exists(k) or overwrite_local:
            # Fetch data from leadership broadcast
            contents = leader_get(k)
            # Default to logging the warning and wait for leader data to be set
            if contents is None:
                hookenv.log("Missing content for file {}".format(k))
                return False
            # Write out the file and move on to the next item
            with open(k, "w+") as fp:
                fp.write(contents)
                fp.write("\n")

    return True


@when("kubernetes-master.snaps.installed")
def set_app_version():
    """Declare the application version to juju"""
    version = check_output(["kube-apiserver", "--version"])
    hookenv.application_version_set(version.split(b" v")[-1].rstrip())


@hookenv.atstart
def check_vault_pending():
    try:
        goal_state = hookenv.goal_state()
    except NotImplementedError:
        goal_state = {}
    vault_kv_goal = "vault-kv" in goal_state.get("relations", {})
    vault_kv_connected = is_state("vault-kv.connected")
    vault_kv_related = vault_kv_goal or vault_kv_connected
    vault_kv_ready = is_state("layer.vault-kv.ready")
    if vault_kv_related and not vault_kv_ready:
        set_flag("kubernetes-master.vault-kv.pending")
    else:
        clear_flag("kubernetes-master.vault-kv.pending")


@hookenv.atexit
def set_final_status():
    """Set the final status of the charm as we leave hook execution"""
    try:
        goal_state = hookenv.goal_state()
    except NotImplementedError:
        goal_state = {}

    if is_flag_set("upgrade.series.in-progress"):
        hookenv.status_set("blocked", "Series upgrade in progress")
        return

    if not is_flag_set("certificates.available"):
        if "certificates" in goal_state.get("relations", {}):
            hookenv.status_set("waiting", "Waiting for certificates authority.")
        else:
            hookenv.status_set("blocked", "Missing relation to certificate authority.")
        return

    if is_flag_set("kubernetes-master.secure-storage.failed"):
        hookenv.status_set(
            "blocked",
            "Failed to configure encryption; "
            "secrets are unencrypted or inaccessible",
        )
        return
    elif is_flag_set("kubernetes-master.secure-storage.created"):
        if not encryption_config_path().exists():
            hookenv.status_set(
                "blocked", "VaultLocker containing encryption config unavailable"
            )
            return

    vsphere_joined = is_state("endpoint.vsphere.joined")
    azure_joined = is_state("endpoint.azure.joined")
    cloud_blocked = is_state("kubernetes-master.cloud.blocked")
    if vsphere_joined and cloud_blocked:
        hookenv.status_set(
            "blocked", "vSphere integration requires K8s 1.12 or greater"
        )
        return
    if azure_joined and cloud_blocked:
        hookenv.status_set("blocked", "Azure integration requires K8s 1.11 or greater")
        return
    if not is_flag_set("kubernetes.cni-plugins.installed"):
        hookenv.status_set("blocked", "Missing CNI resource")
        return
    if is_state("kubernetes-master.cloud.pending"):
        hookenv.status_set("waiting", "Waiting for cloud integration")
        return

    if "kube-api-endpoint" in goal_state.get("relations", {}):
        if not is_state("kube-api-endpoint.available"):
            hookenv.status_set("waiting", "Waiting for kube-api-endpoint relation")
            return

    for lb_endpoint in ("loadbalancer-internal", "loadbalancer-external"):
        if lb_endpoint in goal_state.get("relations", {}):
            lb_provider = endpoint_from_name(lb_endpoint)
            if not lb_provider.has_response:
                hookenv.status_set("waiting", "Waiting for " + lb_endpoint)
                return

    if not is_state("kube-control.connected"):
        if "kube-control" in goal_state.get("relations", {}):
            status = "waiting"
        else:
            status = "blocked"
        hookenv.status_set(status, "Waiting for workers.")
        return

    ks = endpoint_from_flag("keystone-credentials.available")
    if ks and ks.api_version() == "2":
        msg = "Keystone auth v2 detected. v3 is required."
        hookenv.status_set("blocked", msg)
        return

    upgrade_needed = is_state("kubernetes-master.upgrade-needed")
    upgrade_specified = is_state("kubernetes-master.upgrade-specified")
    if upgrade_needed and not upgrade_specified:
        msg = "Needs manual upgrade, run the upgrade action"
        hookenv.status_set("blocked", msg)
        return

    try:
        get_dns_provider()
    except InvalidDnsProvider as e:
        if e.value == "core-dns":
            msg = "dns-provider=core-dns requires k8s 1.14+"
        else:
            msg = "dns-provider=%s is invalid" % e.value
        hookenv.status_set("blocked", msg)
        return

    if is_state("kubernetes-master.vault-kv.pending"):
        hookenv.status_set(
            "waiting", "Waiting for encryption info from Vault to secure secrets"
        )
        return

    if is_state("kubernetes-master.had-service-cidr-expanded"):
        hookenv.status_set(
            "waiting", "Waiting to retry updates for service-cidr expansion"
        )
        return

    if not is_state("etcd.available"):
        if "etcd" in goal_state.get("relations", {}):
            status = "waiting"
        else:
            status = "blocked"
        hookenv.status_set(status, "Waiting for etcd")
        return

    if not is_state("cni.available"):
        if "cni" in goal_state.get("relations", {}):
            status = "waiting"
        else:
            status = "blocked"
        hookenv.status_set(status, "Waiting for CNI plugins to become available")
        return

    if not is_state("tls_client.certs.saved"):
        hookenv.status_set("waiting", "Waiting for certificates")
        return

    if not is_flag_set("kubernetes-master.auth-webhook-service.started"):
        hookenv.status_set("waiting", "Waiting for auth-webhook service to start")
        return

    if not is_flag_set("kubernetes-master.apiserver.configured"):
        hookenv.status_set("waiting", "Waiting for API server to be configured")
        return

    if not is_flag_set("kubernetes-master.apiserver.running"):
        hookenv.status_set("waiting", "Waiting for API server to start")
        return

    authentication_setup = is_state("authentication.setup")
    if not authentication_setup:
        hookenv.status_set("waiting", "Waiting on crypto keys.")
        return

    if not is_flag_set("kubernetes-master.auth-webhook-tokens.setup"):
        hookenv.status_set("waiting", "Waiting for auth-webhook tokens")
        return

    if is_state("kubernetes-master.components.started"):
        # All services should be up and running at this point. Double-check...
        failing_services = master_services_down()
        if len(failing_services) != 0:
            msg = "Stopped services: {}".format(",".join(failing_services))
            hookenv.status_set("blocked", msg)
            return
    else:
        # if we don't have components starting, we're waiting for that and
        # shouldn't fall through to Kubernetes master running.
        hookenv.status_set("maintenance", "Waiting for master components to start")
        return

    # Note that after this point, kubernetes-master.components.started is
    # always True.

    is_leader = is_state("leadership.is_leader")
    addons_configured = is_state("cdk-addons.configured")
    if is_leader and not addons_configured:
        hookenv.status_set("waiting", "Waiting to retry addon deployment")
        return

    if is_leader and not is_state(
        "kubernetes-master.system-monitoring-rbac-role.applied"
    ):
        msg = "Waiting to retry applying system:monitoring RBAC role"
        hookenv.status_set("waiting", msg)
        return

    try:
        unready = get_kube_system_pods_not_running()
    except FailedToGetPodStatus:
        hookenv.status_set("waiting", "Waiting for kube-system pods to start")
        return

    if unready:
        plural = "s" if len(unready) > 1 else ""
        msg = "Waiting for {} kube-system pod{} to start"
        msg = msg.format(len(unready), plural)
        hookenv.status_set("waiting", msg)
        return

    service_cidr = kubernetes_master.service_cidr()
    if hookenv.config("service-cidr") != service_cidr:
        msg = "WARN: cannot change service-cidr, still using " + service_cidr
        hookenv.status_set("active", msg)
        return

    gpu_available = is_state("kube-control.gpu.available")
    gpu_enabled = is_state("kubernetes-master.gpu.enabled")
    if gpu_available and not gpu_enabled:
        msg = 'GPUs available. Set allow-privileged="auto" to enable.'
        hookenv.status_set("active", msg)
        return

    if (
        is_state("ceph-storage.available")
        and is_state("ceph-client.connected")
        and is_state("kubernetes-master.privileged")
        and not is_state("kubernetes-master.ceph.configured")
    ):

        ceph_admin = endpoint_from_flag("ceph-storage.available")

        if get_version("kube-apiserver") >= (1, 12) and not ceph_admin.key():
            hookenv.status_set("waiting", "Waiting for Ceph to provide a key.")
            return

    if is_leader and ks and is_flag_set("kubernetes-master.keystone-policy-error"):
        hookenv.status_set("blocked", "Invalid keystone policy file.")
        return

    if (
        is_leader
        and ks
        and not is_flag_set("kubernetes-master.keystone-policy-handled")
    ):
        hookenv.status_set("waiting", "Waiting to apply keystone policy file.")
        return

    hookenv.status_set("active", "Kubernetes master running.")


def master_services_down():
    """Ensure master services are up and running.

    Return: list of failing services"""
    return list(filterfalse(kubernetes_master.check_service, master_services))


def add_systemd_file_limit():
    directory = "/etc/systemd/system/snap.kube-apiserver.daemon.service.d"
    if not os.path.isdir(directory):
        os.makedirs(directory)

    file_name = "file-limit.conf"
    path = os.path.join(directory, file_name)
    if not os.path.isfile(path):
        with open(path, "w") as f:
            f.write("[Service]\n")
            f.write("LimitNOFILE=65535")


def add_systemd_restart_always():
    template = "templates/service-always-restart.systemd-latest.conf"

    try:
        # Get the systemd version
        cmd = ["systemd", "--version"]
        output = check_output(cmd).decode("UTF-8")
        line = output.splitlines()[0]
        words = line.split()
        assert words[0] == "systemd"
        systemd_version = int(words[1])

        # Check for old version (for xenial support)
        if systemd_version < 230:
            template = "templates/service-always-restart.systemd-229.conf"
    except Exception:
        traceback.print_exc()
        hookenv.log(
            "Failed to detect systemd version, using latest template", level="ERROR"
        )

    for service in master_services:
        dest_dir = "/etc/systemd/system/snap.{}.daemon.service.d".format(service)
        os.makedirs(dest_dir, exist_ok=True)
        copyfile(template, "{}/always-restart.conf".format(dest_dir))


def add_systemd_file_watcher():
    """Setup systemd file-watcher service.

    This service watches these files for changes:

    /root/cdk/known_tokens.csv
    /root/cdk/serviceaccount.key

    If a file is changed, the service uses juju-run to invoke a script in a
    hook context on this unit. If this unit is the leader, the script will
    call leader-set to distribute the contents of these files to the
    non-leaders so they can sync their local copies to match.

    """
    render(
        "cdk.master.leader.file-watcher.sh",
        "/usr/local/sbin/cdk.master.leader.file-watcher.sh",
        {},
        perms=0o777,
    )
    render(
        "cdk.master.leader.file-watcher.service",
        "/etc/systemd/system/cdk.master.leader.file-watcher.service",
        {"unit": hookenv.local_unit()},
        perms=0o644,
    )
    render(
        "cdk.master.leader.file-watcher.path",
        "/etc/systemd/system/cdk.master.leader.file-watcher.path",
        {},
        perms=0o644,
    )
    service_resume("cdk.master.leader.file-watcher.path")


@when("etcd.available", "tls_client.certs.saved")
@restart_on_change(
    {
        auth_webhook_conf: [auth_webhook_svc_name],
        auth_webhook_exe: [auth_webhook_svc_name],
        auth_webhook_svc: [auth_webhook_svc_name],
    }
)
def register_auth_webhook():
    """Render auth webhook templates and start the related service."""
    os.makedirs(auth_webhook_root, exist_ok=True)
    config = hookenv.config()

    # For 'api_ver', match the api version of the authentication.k8s.io TokenReview
    # that k8s-apiserver will be sending:
    #   https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.18
    context = {
        "api_ver": "v1beta1",
        "charm_dir": hookenv.charm_dir(),
        "host": get_ingress_address(
            "kube-api-endpoint", ignore_addresses=[hookenv.config("ha-cluster-vip")]
        ),
        "pidfile": "{}.pid".format(auth_webhook_svc_name),
        "logfile": "{}.log".format(auth_webhook_svc_name),
        "port": 5000,
        "root_dir": auth_webhook_root,
    }

    context["aws_iam_endpoint"] = None
    if endpoint_from_flag("endpoint.aws-iam.ready"):
        aws_webhook = Path(aws_iam_webhook)
        if aws_webhook.exists():
            aws_yaml = yaml.safe_load(aws_webhook.read_text())
            try:
                context["aws_iam_endpoint"] = aws_yaml["clusters"][0]["cluster"][
                    "server"
                ]
            except (KeyError, TypeError):
                hookenv.log(
                    "Unable to find server in AWS IAM webhook: {}".format(aws_yaml)
                )
                pass

    context["keystone_endpoint"] = None
    if endpoint_from_flag("keystone-credentials.available"):
        ks_webhook = Path(keystone_root) / "webhook.yaml"
        if ks_webhook.exists():
            ks_yaml = yaml.safe_load(ks_webhook.read_text())
            try:
                context["keystone_endpoint"] = ks_yaml["clusters"][0]["cluster"][
                    "server"
                ]
            except (KeyError, TypeError):
                hookenv.log(
                    "Unable to find server in Keystone webhook: {}".format(ks_yaml)
                )
                pass

    context["custom_authn_endpoint"] = None
    custom_authn = config.get("authn-webhook-endpoint")
    if custom_authn:
        context["custom_authn_endpoint"] = custom_authn

    k8s_log_path = Path(kubernetes_logs)
    k8s_log_path.mkdir(parents=True, exist_ok=True)  # ensure log path exists
    render("cdk.master.auth-webhook-conf.yaml", auth_webhook_conf, context)
    render("cdk.master.auth-webhook.py", auth_webhook_exe, context)
    render(
        "cdk.master.auth-webhook.logrotate", "/etc/logrotate.d/auth-webhook", context
    )

    # Move existing log files from ${auth_webhook_root} to /var/log/kubernetes/
    for log_file in Path(auth_webhook_root).glob("auth-webhook.log*"):
        # all historical log files (.log, .log.1 and .log.3.tgz)
        new_log_file = k8s_log_path / ("cdk.master." + log_file.name)
        if not new_log_file.exists():
            move(str(log_file), str(new_log_file))

    # Set the number of gunicorn workers based on our core count. (2*cores)+1 is
    # recommended: https://docs.gunicorn.org/en/stable/design.html#how-many-workers
    try:
        cores = int(check_output(["nproc"]).decode("utf-8").strip())
    except CalledProcessError:
        # Our default architecture is 2-cores for k8s-master units
        cores = 2
    else:
        # Put an upper bound on cores; more than 12ish workers is overkill
        cores = 6 if cores > 6 else cores
    context["num_workers"] = cores * 2 + 1
    render("cdk.master.auth-webhook.service", auth_webhook_svc, context)
    if any_file_changed([auth_webhook_svc]):
        # if the service file has changed (or is new),
        # we have to inform systemd about it
        check_call(["systemctl", "daemon-reload"])
    if not is_flag_set("kubernetes-master.auth-webhook-service.started"):
        if service_resume(auth_webhook_svc_name):
            set_flag("kubernetes-master.auth-webhook-service.started")
            clear_flag("kubernetes-master.apiserver.configured")
        else:
            hookenv.status_set(
                "maintenance", "Waiting for {} to start.".format(auth_webhook_svc_name)
            )
            hookenv.log("{} failed to start; will retry".format(auth_webhook_svc_name))


@when(
    "kubernetes-master.apiserver.running",
    "kubernetes-master.auth-webhook-service.started",
    "authentication.setup",
)
@when_not("kubernetes-master.auth-webhook-tokens.setup")
def setup_auth_webhook_tokens():
    """Reconfigure authentication to setup auth-webhook tokens.

    If authentication has been setup with a non-auth-webhook configuration,
    convert it to use auth-webhook tokens instead. Alternatively, if the
    auth-webhook setup failed, this will also ensure that it is retried.
    """
    # Even if the apiserver is configured, it may not be fully started. Only
    # proceed if we can get secrets.
    if not kubectl_success("get", "secrets"):
        hookenv.log("Secrets are not yet available; will retry")
        return
    if create_tokens_and_sign_auth_requests():
        # Force setup_leader_authentication to be re-run.
        remove_state("authentication.setup")


@when(
    "etcd.available",
    "tls_client.certs.saved",
    "authentication.setup",
    "leadership.set.auto_storage_backend",
    "leadership.set.cluster_tag",
    "cni.available",
)
@when_not(
    "kubernetes-master.components.started",
    "kubernetes-master.cloud.pending",
    "kubernetes-master.cloud.blocked",
    "kubernetes-master.vault-kv.pending",
    "tls_client.certs.changed",
    "tls_client.ca.written",
    "upgrade.series.in-progress",
)
def start_master():
    """Run the Kubernetes master components."""
    hookenv.status_set("maintenance", "Configuring the Kubernetes master services.")

    if not is_state("kubernetes-master.vault-kv.pending") and not is_state(
        "kubernetes-master.secure-storage.created"
    ):
        encryption_config_path().parent.mkdir(parents=True, exist_ok=True)
        host.write_file(
            path=str(encryption_config_path()),
            perms=0o600,
            content=yaml.safe_dump(
                {
                    "kind": "EncryptionConfig",
                    "apiVersion": "v1",
                    "resources": [
                        {"resources": ["secrets"], "providers": [{"identity": {}}]}
                    ],
                }
            ),
        )

    kubernetes_master.freeze_service_cidr()

    etcd = endpoint_from_flag("etcd.available")
    if not etcd.get_connection_string():
        # etcd is not returning a connection string. This happens when
        # the master unit disconnects from etcd and is ready to terminate.
        # No point in trying to start master services and fail. Just return.
        return

    # TODO: Make sure below relation is handled on change
    # https://github.com/kubernetes/kubernetes/issues/43461
    handle_etcd_relation(etcd)

    # Set up additional systemd services
    add_systemd_restart_always()
    add_systemd_file_limit()
    add_systemd_file_watcher()
    add_systemd_iptables_patch()
    check_call(["systemctl", "daemon-reload"])

    # Add CLI options to all components
    clear_flag("kubernetes-master.apiserver.configured")
    configure_controller_manager()
    configure_scheduler()

    # kube-proxy
    cluster_cidr = kubernetes_common.cluster_cidr()
    if kubernetes_common.is_ipv6(cluster_cidr):
        kubernetes_common.enable_ipv6_forwarding()

    local_address = get_ingress_address("kube-api-endpoint")
    local_server = "https://{0}:{1}".format(local_address, 6443)

    configure_kube_proxy(configure_prefix, [local_server], cluster_cidr)
    service_restart("snap.kube-proxy.daemon")

    set_state("kubernetes-master.components.started")
    hookenv.open_port(6443)


@when("config.changed.proxy-extra-args")
def proxy_args_changed():
    clear_flag("kubernetes-master.components.started")
    clear_flag("config.changed.proxy-extra-args")


@when("tls_client.certs.changed")
def certs_changed():
    clear_flag("kubernetes-master.components.started")
    clear_flag("tls_client.certs.changed")


@when("tls_client.ca.written")
def ca_written():
    clear_flag("kubernetes-master.components.started")
    if is_state("leadership.is_leader"):
        if leader_get("kubernetes-master-addons-ca-in-use"):
            leader_set({"kubernetes-master-addons-restart-for-ca": True})
    clear_flag("tls_client.ca.written")


@when("etcd.available")
def etcd_data_change(etcd):
    """Etcd scale events block master reconfiguration due to the
    kubernetes-master.components.started state. We need a way to
    handle these events consistently only when the number of etcd
    units has actually changed"""

    # key off of the connection string
    connection_string = etcd.get_connection_string()

    # If the connection string changes, remove the started state to trigger
    # handling of the master components
    if data_changed("etcd-connect", connection_string):
        remove_state("kubernetes-master.components.started")

    # If the cert info changes, remove the started state to trigger
    # handling of the master components
    if data_changed("etcd-certs", etcd.get_client_credentials()):
        clear_flag("kubernetes-master.components.started")

    # We are the leader and the auto_storage_backend is not set meaning
    # this is the first time we connect to etcd.
    auto_storage_backend = leader_get("auto_storage_backend")
    is_leader = is_state("leadership.is_leader")
    if is_leader and not auto_storage_backend:
        if etcd.get_version().startswith("3."):
            leader_set(auto_storage_backend="etcd3")
        else:
            leader_set(auto_storage_backend="etcd2")


@when("kube-control.connected")
@when("cdk-addons.configured")
def send_cluster_dns_detail(kube_control):
    """Send cluster DNS info"""
    dns_provider = endpoint_from_flag("dns-provider.available")
    try:
        goal_state_rels = hookenv.goal_state().get("relations", {})
    except NotImplementedError:
        goal_state_rels = {}
    dns_provider_missing = not dns_provider and "dns-provider" not in goal_state_rels
    dns_provider_pending = not dns_provider and "dns-provider" in goal_state_rels
    try:
        dns_disabled_cfg = get_dns_provider() == "none"
    except InvalidDnsProvider:
        dns_disabled_cfg = False
    if dns_provider_missing and dns_disabled_cfg:
        kube_control.set_dns(None, None, None, False)
    elif dns_provider_pending:
        pass
    elif dns_provider:
        details = dns_provider.details()
        kube_control.set_dns(
            details["port"], details["domain"], details["sdn-ip"], True
        )
    else:
        try:
            dns_provider = get_dns_provider()
        except InvalidDnsProvider:
            hookenv.log(traceback.format_exc())
            return
        dns_domain = hookenv.config("dns_domain")
        dns_ip = None
        try:
            dns_ip = kubernetes_master.get_dns_ip()
        except CalledProcessError:
            hookenv.log("DNS addon service not ready yet")
            return
        kube_control.set_dns(53, dns_domain, dns_ip, True)


def create_tokens_and_sign_auth_requests():
    """Create tokens for CK users and services."""
    clear_flag("kubernetes-master.auth-webhook-tokens.setup")
    # NB: This may be called before kube-apiserver is up when bootstrapping new
    # clusters with auth-webhook. In this case, setup_tokens will be a no-op.
    # We will re-enter this function once master services are available to
    # create proper secrets.
    controller_manager_token = get_token("system:kube-controller-manager")
    if not controller_manager_token:
        setup_tokens(None, "system:kube-controller-manager", "kube-controller-manager")

    proxy_token = get_token("system:kube-proxy")
    if not proxy_token:
        setup_tokens(None, "system:kube-proxy", "kube-proxy")
        proxy_token = get_token("system:kube-proxy")

    scheduler_token = get_token("system:kube-scheduler")
    if not scheduler_token:
        setup_tokens(None, "system:kube-scheduler", "system:kube-scheduler")

    client_token = get_token("admin")
    if not client_token:
        setup_tokens(None, "admin", "admin", "system:masters")
        client_token = get_token("admin")

    monitoring_token = get_token("system:monitoring")
    if not monitoring_token:
        setup_tokens(None, "system:monitoring", "system:monitoring")

    if not (proxy_token and client_token):
        # When bootstrapping a new cluster, we may not have all our secrets yet.
        # Do not let the kubelets start without all the needed tokens.
        hookenv.log(
            "Missing required tokens for kubelet startup; will retry", hookenv.WARNING
        )
        return False

    kube_control = endpoint_from_flag("kube-control.connected")
    requests = kube_control.auth_user() if kube_control else []
    any_failed = False
    for request in requests:
        username = request[1]["user"]
        group = request[1]["group"]
        if not username or not group:
            continue
        kubelet_token = get_token(username)
        if not kubelet_token:
            # Username will be in the form of system:node:<nodeName>.
            # User ID will be a worker <unitName>, and while not used today, we store
            # this in case it becomes useful to map a secret to a unit in the future.
            userid = request[0]
            setup_tokens(None, username, userid, group)
            kubelet_token = get_token(username)
        if not kubelet_token:
            hookenv.log(
                "Failed to create token for {}; will retry".format(username),
                hookenv.WARNING,
            )
            any_failed = True
            continue
        kube_control.sign_auth_request(
            request[0], username, kubelet_token, proxy_token, client_token
        )
    if not any_failed:
        set_flag("kubernetes-master.auth-webhook-tokens.setup")
        return True
    else:
        return False


@when("kube-api-endpoint.available")
def push_service_data():
    """Send configuration to the load balancer, and close access to the
    public interface.
    """
    kube_api = endpoint_from_flag("kube-api-endpoint.available")

    endpoints = kubernetes_master.get_endpoints_from_config()
    if endpoints:
        addresses = [e[0] for e in endpoints]
        kube_api.configure(kubernetes_master.STANDARD_API_PORT, addresses, addresses)
    else:
        # no manually configured LBs, so rely on the interface layer
        # to use the ingress address for each relation
        kube_api.configure(kubernetes_master.STANDARD_API_PORT)


@when("leadership.is_leader")
@when_any(
    "endpoint.loadbalancer-internal.available",
    "endpoint.loadbalancer-external.available",
)
def request_load_balancers():
    """Request LBs from the related provider(s)."""
    for lb_type in ("internal", "external"):
        lb_provider = endpoint_from_name("loadbalancer-" + lb_type)
        if not lb_provider.is_available:
            continue
        req = lb_provider.get_request("api-server-" + lb_type)
        req.protocol = req.protocols.tcp
        ext_api_port = kubernetes_master.EXTERNAL_API_PORT
        int_api_port = kubernetes_master.STANDARD_API_PORT
        api_port = ext_api_port if lb_type == "external" else int_api_port
        req.port_mapping = {api_port: int_api_port}
        req.public = lb_type == "external"
        if not req.health_checks:
            req.add_health_check(
                protocol=req.protocols.http,
                port=int_api_port,
                path="/livez",
            )
        lb_provider.send_request(req)


@when("kube-control.connected")
def send_api_urls():
    kube_control = endpoint_from_name("kube-control")
    if not hasattr(kube_control, "set_api_endpoints"):
        # built with an old version of the kube-control interface
        # the old kube-api-endpoint relation must be used instead
        return
    endpoints = kubernetes_master.get_internal_api_endpoints()
    if not endpoints:
        return
    kube_control.set_api_endpoints(kubernetes_master.get_api_urls(endpoints))


@when("certificates.available", "cni.available")
def send_data():
    """Send the data that is required to create a server certificate for
    this server."""
    # Use the public ip of this unit as the Common Name for the certificate.
    common_name = hookenv.unit_public_ip()

    # Get the SDN gateways based on the service CIDRs.
    k8s_service_ips = kubernetes_master.get_kubernetes_service_ips()

    cluster_cidr = kubernetes_common.cluster_cidr()
    bind_ips = kubernetes_common.get_bind_addrs(
        ipv4=kubernetes_common.is_ipv4(cluster_cidr),
        ipv6=kubernetes_common.is_ipv6(cluster_cidr),
    )

    # Get ingress address (this is probably already covered by bind_ips,
    # but list it explicitly as well just in case it's not).
    old_ingress_ip = get_ingress_address("kube-api-endpoint")
    new_ingress_ip = get_ingress_address("kube-control")

    local_endpoint = kubernetes_master.get_local_api_endpoint()[0][0]

    domain = hookenv.config("dns_domain")
    # Create SANs that the tls layer will add to the server cert.
    sans = (
        [
            # The CN field is checked as a hostname, so if it's an IP, it
            # won't match unless also included in the SANs as an IP field.
            common_name,
            local_endpoint,
            old_ingress_ip,
            new_ingress_ip,
            socket.gethostname(),
            socket.getfqdn(),
            "kubernetes",
            "kubernetes.{0}".format(domain),
            "kubernetes.default",
            "kubernetes.default.svc",
            "kubernetes.default.svc.{0}".format(domain),
        ]
        + k8s_service_ips
        + bind_ips
    )

    sans.extend(e[0] for e in kubernetes_master.get_internal_api_endpoints())
    sans.extend(e[0] for e in kubernetes_master.get_external_api_endpoints())

    # maybe they have extra names they want as SANs
    extra_sans = hookenv.config("extra_sans")
    if extra_sans and not extra_sans == "":
        sans.extend(extra_sans.split())

    # Request a server cert with this information.
    tls_client.request_server_cert(
        common_name,
        sorted(set(sans)),
        crt_path=server_crt_path,
        key_path=server_key_path,
    )

    # Request a client cert for kubelet.
    tls_client.request_client_cert(
        "system:kube-apiserver", crt_path=client_crt_path, key_path=client_key_path
    )


@when(
    "config.changed.extra_sans", "certificates.available", "kube-api-endpoint.available"
)
def update_certificates():
    # NOTE: This handler may be called by another function. Two relationships
    # are required, otherwise the send_data function fails.
    # (until the relations are available)
    missing_relations = get_unset_flags(
        "certificates.available", "kube-api-endpoint.available"
    )
    if missing_relations:
        hookenv.log(
            "Missing relations: '{}'".format(", ".join(missing_relations)),
            hookenv.ERROR,
        )
        return

    # Using the config.changed.extra_sans flag to catch changes.
    # IP changes will take ~5 minutes or so to propagate, but
    # it will update.
    send_data()
    clear_flag("config.changed.extra_sans")


@when(
    "kubernetes-master.components.started",
    "leadership.is_leader",
    "cdk-addons.reconfigure",
)
def reconfigure_cdk_addons():
    configure_cdk_addons()


@when(
    "kubernetes-master.components.started",
    "leadership.is_leader",
    "leadership.set.cluster_tag",
)
@when_not("upgrade.series.in-progress")
def configure_cdk_addons():
    """Configure CDK addons"""
    remove_state("cdk-addons.reconfigure")
    remove_state("cdk-addons.configured")
    remove_state("kubernetes-master.aws.changed")
    remove_state("kubernetes-master.azure.changed")
    remove_state("kubernetes-master.gcp.changed")
    remove_state("kubernetes-master.openstack.changed")
    load_gpu_plugin = hookenv.config("enable-nvidia-plugin").lower()
    gpuEnable = (
        get_version("kube-apiserver") >= (1, 9)
        and load_gpu_plugin == "auto"
        and is_state("kubernetes-master.gpu.enabled")
    )
    registry = hookenv.config("image-registry")
    dbEnabled = str(hookenv.config("enable-dashboard-addons")).lower()
    try:
        dnsProvider = get_dns_provider()
    except InvalidDnsProvider:
        hookenv.log(traceback.format_exc())
        return
    metricsEnabled = str(hookenv.config("enable-metrics")).lower()
    default_storage = ""
    ceph = {}
    ceph_ep = endpoint_from_flag("ceph-storage.available")
    cephfs_mounter = hookenv.config("cephfs-mounter")
    if (
        ceph_ep
        and ceph_ep.key()
        and ceph_ep.fsid()
        and ceph_ep.mon_hosts()
        and is_state("kubernetes-master.ceph.configured")
        and get_version("kube-apiserver") >= (1, 12)
    ):
        cephEnabled = "true"
        b64_ceph_key = base64.b64encode(ceph_ep.key().encode("utf-8"))
        ceph["admin_key"] = b64_ceph_key.decode("ascii")
        ceph["fsid"] = ceph_ep.fsid()
        ceph["kubernetes_key"] = b64_ceph_key.decode("ascii")
        ceph["mon_hosts"] = ceph_ep.mon_hosts()
        default_storage = hookenv.config("default-storage")
        if kubernetes_master.query_cephfs_enabled():
            cephFsEnabled = "true"
            ceph["fsname"] = kubernetes_master.get_cephfs_fsname() or ""
        else:
            cephFsEnabled = "false"
    else:
        cephEnabled = "false"
        cephFsEnabled = "false"

    keystone = {}
    ks = endpoint_from_flag("keystone-credentials.available")
    if ks:
        keystoneEnabled = "true"
        keystone["cert"] = "/root/cdk/server.crt"
        keystone["key"] = "/root/cdk/server.key"
        keystone["url"] = "{}://{}:{}/v{}".format(
            ks.credentials_protocol(),
            ks.credentials_host(),
            ks.credentials_port(),
            ks.api_version(),
        )
        keystone["keystone-ca"] = hookenv.config("keystone-ssl-ca")
    else:
        keystoneEnabled = "false"

    enable_aws = str(is_flag_set("endpoint.aws.ready")).lower()
    enable_azure = str(is_flag_set("endpoint.azure.ready")).lower()
    enable_gcp = str(is_flag_set("endpoint.gcp.ready")).lower()
    enable_openstack = str(is_flag_set("endpoint.openstack.ready")).lower()
    openstack = endpoint_from_flag("endpoint.openstack.ready")

    if is_state("kubernetes-master.cdk-addons.unique-cluster-tag"):
        cluster_tag = leader_get("cluster_tag")
    else:
        # allow for older upgraded charms to control when they start sending
        # the unique cluster tag to cdk-addons
        cluster_tag = "kubernetes"

    args = [
        "kubeconfig=" + cdk_addons_kubectl_config_path,
        "arch=" + arch(),
        "dns-domain=" + hookenv.config("dns_domain"),
        "registry=" + registry,
        "enable-dashboard=" + dbEnabled,
        "enable-metrics=" + metricsEnabled,
        "enable-gpu=" + str(gpuEnable).lower(),
        "enable-ceph=" + cephEnabled,
        "enable-cephfs=" + cephFsEnabled,
        "cephfs-mounter=" + cephfs_mounter,
        "ceph-admin-key=" + (ceph.get("admin_key", "")),
        "ceph-fsid=" + (ceph.get("fsid", "")),
        "ceph-fsname=" + (ceph.get("fsname", "")),
        "ceph-kubernetes-key=" + (ceph.get("admin_key", "")),
        'ceph-mon-hosts="' + (ceph.get("mon_hosts", "")) + '"',
        "default-storage=" + default_storage,
        "enable-keystone=" + keystoneEnabled,
        "keystone-cert-file=" + keystone.get("cert", ""),
        "keystone-key-file=" + keystone.get("key", ""),
        "keystone-server-url=" + keystone.get("url", ""),
        "keystone-server-ca=" + keystone.get("keystone-ca", ""),
        "dashboard-auth=token",
        "enable-aws=" + enable_aws,
        "enable-azure=" + enable_azure,
        "enable-gcp=" + enable_gcp,
        "enable-openstack=" + enable_openstack,
        "cluster-tag=" + cluster_tag,
    ]
    if openstack:
        args.extend(
            [
                "openstack-cloud-conf="
                + base64.b64encode(
                    generate_openstack_cloud_config().encode("utf-8")
                ).decode("utf-8"),
                "openstack-endpoint-ca=" + (openstack.endpoint_tls_ca or ""),
            ]
        )
    if get_version("kube-apiserver") >= (1, 14):
        args.append("dns-provider=" + dnsProvider)
    else:
        enableKubeDNS = dnsProvider == "kube-dns"
        args.append("enable-kube-dns=" + str(enableKubeDNS).lower())
    check_call(["snap", "set", "cdk-addons"] + args)
    if not addons_ready():
        remove_state("cdk-addons.configured")
        return

    set_state("cdk-addons.configured")
    leader_set({"kubernetes-master-addons-ca-in-use": True})
    if ks:
        leader_set({"keystone-cdk-addons-configured": True})
    else:
        leader_set({"keystone-cdk-addons-configured": None})


@retry(times=3, delay_secs=20)
def addons_ready():
    """
    Test if the add ons got installed

    Returns: True is the addons got applied

    """
    try:
        check_call(["cdk-addons.apply"])
        return True
    except CalledProcessError:
        hookenv.log("Addons are not ready yet.")
        return False


@when("ceph-storage.available")
def ceph_state_control():
    """Determine if we should remove the state that controls the re-render
    and execution of the ceph-relation-changed event because there
    are changes in the relationship data, and we should re-render any
    configs, keys, and/or service pre-reqs"""

    ceph_admin = endpoint_from_flag("ceph-storage.available")
    ceph_relation_data = {
        "mon_hosts": ceph_admin.mon_hosts(),
        "fsid": ceph_admin.fsid(),
        "auth_supported": ceph_admin.auth(),
        "hostname": socket.gethostname(),
        "key": ceph_admin.key(),
    }

    # Re-execute the rendering if the data has changed.
    if data_changed("ceph-config", ceph_relation_data):
        remove_state("kubernetes-master.ceph.configured")


@when("kubernetes-master.ceph.configured")
@when_not("ceph-storage.available")
def ceph_storage_gone():
    # ceph has left, so clean up
    clear_flag("kubernetes-master.apiserver.configured")
    remove_state("kubernetes-master.ceph.configured")


@when("kubernetes-master.ceph.pools.created")
@when_not("ceph-client.connected")
def ceph_client_gone():
    # can't nuke pools, but we can't be certain that they
    # are still made when a new relation comes in
    remove_state("kubernetes-master.ceph.pools.created")


@when("etcd.available")
@when("ceph-storage.available")
@when_not("kubernetes-master.privileged")
@when_not("kubernetes-master.ceph.configured")
def ceph_storage_privilege():
    """
    Before we configure Ceph, we
    need to allow the master to
    run privileged containers.

    :return: None
    """
    clear_flag("kubernetes-master.apiserver.configured")


@when("ceph-client.connected")
@when("kubernetes-master.ceph.configured")
@when_not("kubernetes-master.ceph.pool.created")
def ceph_storage_pool():
    """Once Ceph relation is ready,
    we need to add storage pools.

    :return: None
    """
    hookenv.log("Creating Ceph pools.")
    ceph_client = endpoint_from_flag("ceph-client.connected")

    pools = ["xfs-pool", "ext4-pool"]

    for pool in pools:
        hookenv.status_set("maintenance", "Creating {} pool.".format(pool))
        try:
            ceph_client.create_pool(name=pool, replicas=3)
        except Exception as e:
            hookenv.status_set("blocked", "Error creating {} pool: {}.".format(pool, e))

    set_state("kubernetes-master.ceph.pool.created")


@when("ceph-storage.available")
@when("kubernetes-master.privileged")
@when_not("kubernetes-master.ceph.configured")
def ceph_storage():
    """Ceph on kubernetes will require a few things - namely a ceph
    configuration, and the ceph secret key file used for authentication.
    This method will install the client package, and render the requisit files
    in order to consume the ceph-storage relation."""
    hookenv.log("Configuring Ceph.")

    ceph_admin = endpoint_from_flag("ceph-storage.available")

    # >=1.12 will use CSI.
    if get_version("kube-apiserver") >= (1, 12) and not ceph_admin.key():
        return  # Retry until Ceph gives us a key.

    # Enlist the ceph-admin key as a kubernetes secret
    if ceph_admin.key():
        encoded_key = base64.b64encode(ceph_admin.key().encode("utf-8"))
    else:
        # We didn't have a key, and cannot proceed. Do not set state and
        # allow this method to re-execute
        return

    # CSI isn't available, so we need to do it ourselves,
    if get_version("kube-apiserver") < (1, 12):
        try:
            # At first glance this is deceptive. The apply stanza will
            # create if it doesn't exist, otherwise it will update the
            # entry, ensuring our ceph-secret is always reflective of
            # what we have in /etc/ceph assuming we have invoked this
            # anytime that file would change.
            context = {"secret": encoded_key.decode("ascii")}
            render("ceph-secret.yaml", "/tmp/ceph-secret.yaml", context)
            cmd = ["kubectl", "apply", "-f", "/tmp/ceph-secret.yaml"]
            check_call(cmd)
            os.remove("/tmp/ceph-secret.yaml")
            set_state("kubernetes-master.ceph.pool.created")
        except:  # NOQA
            # The enlistment in kubernetes failed, return and
            # prepare for re-exec.
            return

    # When complete, set a state relating to configuration of the storage
    # backend that will allow other modules to hook into this and verify we
    # have performed the necessary pre-req steps to interface with a ceph
    # deployment.
    set_state("kubernetes-master.ceph.configured")


@when("nrpe-external-master.available")
@when_not("nrpe-external-master.initial-config")
def initial_nrpe_config():
    set_state("nrpe-external-master.initial-config")
    update_nrpe_config()


@when("config.changed.authorization-mode")
def switch_auth_mode(forced=False):
    config = hookenv.config()
    mode = config.get("authorization-mode")

    if data_changed("auth-mode", mode) or forced:
        # manage flags to handle rbac related resources
        if mode and "rbac" in mode.lower():
            remove_state("kubernetes-master.remove.rbac")
            set_state("kubernetes-master.create.rbac")
        else:
            remove_state("kubernetes-master.create.rbac")
            set_state("kubernetes-master.remove.rbac")

        # set ourselves up to restart since auth mode has changed
        remove_state("kubernetes-master.components.started")


@when("leadership.is_leader", "kubernetes-master.components.started")
@when_not("kubernetes-master.pod-security-policy.applied")
def create_pod_security_policy_resources():
    pod_security_policy_path = "/root/cdk/pod-security-policy.yaml"
    pod_security_policy = hookenv.config("pod-security-policy")
    if pod_security_policy:
        hookenv.log("Using configuration defined on pod-security-policy option")
        write_file_with_autogenerated_header(
            pod_security_policy_path, pod_security_policy
        )
    else:
        hookenv.log("Using the default rbac-pod-security-policy template")
        render("rbac-pod-security-policy.yaml", pod_security_policy_path, {})

    hookenv.log("Creating pod security policy resources.")
    if kubectl_manifest("apply", pod_security_policy_path):
        set_state("kubernetes-master.pod-security-policy.applied")
    else:
        msg = "Failed to apply {}, will retry.".format(pod_security_policy_path)
        hookenv.log(msg)


@when(
    "leadership.is_leader",
    "kubernetes-master.components.started",
    "kubernetes-master.create.rbac",
)
def create_rbac_resources():
    rbac_proxy_path = "/root/cdk/rbac-proxy.yaml"

    # NB: when metrics and logs are retrieved by proxy, the 'user' is the
    # common name of the cert used to authenticate the proxied request.
    # The CN for /root/cdk/client.crt is 'system:kube-apiserver'
    # (see the send_data handler, above).
    proxy_users = ["client", "system:kube-apiserver"]

    context = {"juju_application": hookenv.service_name(), "proxy_users": proxy_users}
    render("rbac-proxy.yaml", rbac_proxy_path, context)

    hookenv.log("Creating proxy-related RBAC resources.")
    if kubectl_manifest("apply", rbac_proxy_path):
        remove_state("kubernetes-master.create.rbac")
    else:
        msg = "Failed to apply {}, will retry.".format(rbac_proxy_path)
        hookenv.log(msg)


@when("leadership.is_leader", "kubernetes-master.components.started")
@when_not("kubernetes-master.system-monitoring-rbac-role.applied")
def apply_system_monitoring_rbac_role():
    try:
        hookenv.status_set("maintenance", "Applying system:monitoring RBAC role")
        path = "/root/cdk/system-monitoring-rbac-role.yaml"
        render("system-monitoring-rbac-role.yaml", path, {})
        kubectl("apply", "-f", path)
        set_state("kubernetes-master.system-monitoring-rbac-role.applied")
    except Exception:
        hookenv.log(traceback.format_exc())
        hookenv.log("Waiting to retry applying system:monitoring RBAC role")
        return


@when(
    "leadership.is_leader",
    "kubernetes-master.components.started",
    "kubernetes-master.remove.rbac",
)
def remove_rbac_resources():
    rbac_proxy_path = "/root/cdk/rbac-proxy.yaml"
    if os.path.isfile(rbac_proxy_path):
        hookenv.log("Removing proxy-related RBAC resources.")
        if kubectl_manifest("delete", rbac_proxy_path):
            os.remove(rbac_proxy_path)
            remove_state("kubernetes-master.remove.rbac")
        else:
            msg = "Failed to delete {}, will retry.".format(rbac_proxy_path)
            hookenv.log(msg)
    else:
        # if we dont have the yaml, there's nothing for us to do
        remove_state("kubernetes-master.remove.rbac")


@when("kubernetes-master.components.started")
@when("nrpe-external-master.available")
@when_any("config.changed.nagios_context", "config.changed.nagios_servicegroups")
def update_nrpe_config():
    services = ["snap.{}.daemon".format(s) for s in master_services]
    services += [auth_webhook_svc_name]

    plugin = install_nagios_plugin_from_file(
        "templates/nagios_plugin.py", "check_k8s_master.py"
    )
    hostname = nrpe.get_nagios_hostname()
    current_unit = nrpe.get_nagios_unit_name()
    nrpe_setup = nrpe.NRPE(hostname=hostname)
    nrpe.add_init_service_checks(nrpe_setup, services, current_unit)
    nrpe_setup.add_check(
        "k8s-api-server",
        "Verify that the Kubernetes API server is accessible",
        str(plugin),
    )
    nrpe_setup.write()


@when_not("nrpe-external-master.available")
@when("nrpe-external-master.initial-config")
def remove_nrpe_config():
    # List of systemd services for which the checks will be removed
    services = ["snap.{}.daemon".format(s) for s in master_services]

    remove_nagios_plugin("check_k8s_master.py")

    # The current nrpe-external-master interface doesn't handle a lot of logic,
    # use the charm-helpers code for now.
    hostname = nrpe.get_nagios_hostname()
    nrpe_setup = nrpe.NRPE(hostname=hostname)

    for service in services:
        nrpe_setup.remove_check(shortname=service)
    nrpe_setup.remove_check(shortname="k8s-api-server")
    remove_state("nrpe-external-master.initial-config")


def is_privileged():
    """Return boolean indicating whether or not to set allow-privileged=true."""
    privileged = hookenv.config("allow-privileged").lower()
    if privileged == "auto":
        return (
            is_state("kubernetes-master.gpu.enabled")
            or is_state("ceph-storage.available")
            or is_state("endpoint.openstack.joined")
        )
    else:
        return privileged == "true"


@when("config.changed.allow-privileged")
@when("kubernetes-master.components.started")
def on_config_allow_privileged_change():
    """React to changed 'allow-privileged' config value."""
    remove_state("kubernetes-master.components.started")
    remove_state("config.changed.allow-privileged")


@when_any(
    "config.changed.api-extra-args",
    "config.changed.audit-policy",
    "config.changed.audit-webhook-config",
    "config.changed.enable-keystone-authorization",
    "config.changed.service-cidr",
)
@when("kubernetes-master.components.started")
@when("leadership.set.auto_storage_backend")
@when("etcd.available")
def reconfigure_apiserver():
    clear_flag("kubernetes-master.apiserver.configured")


@when("config.changed.controller-manager-extra-args")
@when("kubernetes-master.components.started")
def on_config_controller_manager_extra_args_change():
    configure_controller_manager()


@when("config.changed.scheduler-extra-args")
@when("kubernetes-master.components.started")
def on_config_scheduler_extra_args_change():
    configure_scheduler()


@when("kube-control.gpu.available")
@when("kubernetes-master.components.started")
@when_not("kubernetes-master.gpu.enabled")
def on_gpu_available(kube_control):
    """The remote side (kubernetes-worker) is gpu-enabled.

    We need to run in privileged mode.

    """
    kube_version = get_version("kube-apiserver")
    config = hookenv.config()
    if config["allow-privileged"].lower() == "false" and kube_version < (1, 9):
        return

    remove_state("kubernetes-master.components.started")
    set_state("kubernetes-master.gpu.enabled")


@when("kubernetes-master.gpu.enabled")
@when("kubernetes-master.components.started")
@when_not("kubernetes-master.privileged")
def gpu_with_no_privileged():
    """We were in gpu mode, but the operator has set allow-privileged="false",
    so we can't run in gpu mode anymore.

    """
    if get_version("kube-apiserver") < (1, 9):
        remove_state("kubernetes-master.gpu.enabled")


@when("kube-control.connected")
@when_not("kube-control.gpu.available")
@when("kubernetes-master.gpu.enabled")
@when("kubernetes-master.components.started")
def gpu_departed(kube_control):
    """We were in gpu mode, but the workers informed us there is
    no gpu support anymore.

    """
    remove_state("kubernetes-master.gpu.enabled")


@hook("stop")
def shutdown():
    """Stop the kubernetes master services"""
    for service in master_services:
        service_stop("snap.%s.daemon" % service)


@when(
    "certificates.ca.available",
    "certificates.client.cert.available",
    "authentication.setup",
)
def build_kubeconfig():
    """Gather the relevant data for Kubernetes configuration objects and create
    a config object with that information."""
    local_endpoint = kubernetes_master.get_local_api_endpoint()
    internal_endpoints = kubernetes_master.get_internal_api_endpoints()
    external_endpoints = kubernetes_master.get_external_api_endpoints()

    # Do we have everything we need?
    if ca_crt_path.exists() and internal_endpoints and external_endpoints:
        local_url = kubernetes_master.get_api_url(local_endpoint)
        internal_url = kubernetes_master.get_api_url(internal_endpoints)
        external_url = kubernetes_master.get_api_url(external_endpoints)
        client_pass = get_token("admin")
        if not client_pass:
            # If we made it this far without a password, we're bootstrapping a new
            # cluster. Create a new token so we can build an admin kubeconfig. The
            # auth-webhook service will ack this value from the kubeconfig file,
            # allowing us to continue until the master is started and a proper
            # secret can be created.
            client_pass = (
                hookenv.config("client_password") or kubernetes_master.token_generator()
            )
            client_pass = "admin::{}".format(client_pass)

        # drop keystone helper script?
        ks = endpoint_from_flag("keystone-credentials.available")
        if ks:
            script_filename = "kube-keystone.sh"
            keystone_path = os.path.join(os.sep, "home", "ubuntu", script_filename)
            context = {
                "protocol": ks.credentials_protocol(),
                "address": ks.credentials_host(),
                "port": ks.credentials_port(),
                "version": ks.api_version(),
            }
            render(script_filename, keystone_path, context)
        elif is_state("leadership.set.keystone-cdk-addons-configured"):
            # if addons are configured, we're going to do keystone
            # just not yet because we don't have creds
            hookenv.log("Keystone endpoint not found, will retry.")

        cluster_id = None
        aws_iam = endpoint_from_flag("endpoint.aws-iam.available")
        if aws_iam:
            cluster_id = aws_iam.get_cluster_id()

        # Create an absolute path for the kubeconfig file.
        kubeconfig_path = os.path.join(os.sep, "home", "ubuntu", "config")

        # Create the kubeconfig on this system so users can access the cluster.
        hookenv.log("Writing kubeconfig file.")

        if ks:
            create_kubeconfig(
                kubeconfig_path,
                external_url,
                ca_crt_path,
                user="admin",
                token=client_pass,
                keystone=True,
                aws_iam_cluster_id=cluster_id,
            )
        else:
            create_kubeconfig(
                kubeconfig_path,
                external_url,
                ca_crt_path,
                user="admin",
                token=client_pass,
                aws_iam_cluster_id=cluster_id,
            )

        # Make the config file readable by the ubuntu users so juju scp works.
        cmd = ["chown", "ubuntu:ubuntu", kubeconfig_path]
        check_call(cmd)

        # make a kubeconfig for root / the charm
        create_kubeconfig(
            kubeclientconfig_path,
            local_url,
            ca_crt_path,
            user="admin",
            token=client_pass,
        )

        # Create kubernetes configuration in the default location for ubuntu.
        create_kubeconfig(
            "/home/ubuntu/.kube/config",
            internal_url,
            ca_crt_path,
            user="admin",
            token=client_pass,
        )
        # Make the config dir readable by the ubuntu user
        check_call(["chown", "-R", "ubuntu:ubuntu", "/home/ubuntu/.kube"])

        # make a kubeconfig for cdk-addons
        create_kubeconfig(
            cdk_addons_kubectl_config_path,
            local_url,
            ca_crt_path,
            user="admin",
            token=client_pass,
        )

        # make a kubeconfig for our services
        proxy_token = get_token("system:kube-proxy")
        if proxy_token:
            create_kubeconfig(
                kubeproxyconfig_path,
                local_url,
                ca_crt_path,
                token=proxy_token,
                user="kube-proxy",
            )
        controller_manager_token = get_token("system:kube-controller-manager")
        if controller_manager_token:
            create_kubeconfig(
                kubecontrollermanagerconfig_path,
                local_url,
                ca_crt_path,
                token=controller_manager_token,
                user="kube-controller-manager",
            )
        scheduler_token = get_token("system:kube-scheduler")
        if scheduler_token:
            create_kubeconfig(
                kubeschedulerconfig_path,
                local_url,
                ca_crt_path,
                token=scheduler_token,
                user="kube-scheduler",
            )

        cni = endpoint_from_name("cni")
        if cni:
            cni.notify_kubeconfig_changed()


def handle_etcd_relation(reldata):
    """Save the client credentials and set appropriate daemon flags when
    etcd declares itself as available"""
    # Define where the etcd tls files will be kept.
    etcd_dir = "/root/cdk/etcd"

    # Create paths to the etcd client ca, key, and cert file locations.
    ca = os.path.join(etcd_dir, "client-ca.pem")
    key = os.path.join(etcd_dir, "client-key.pem")
    cert = os.path.join(etcd_dir, "client-cert.pem")

    # Save the client credentials (in relation data) to the paths provided.
    reldata.save_client_credentials(key, cert, ca)


def remove_if_exists(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def write_file_with_autogenerated_header(path, contents):
    with open(path, "w") as f:
        header = "# Autogenerated by kubernetes-master charm"
        f.write(header + "\n" + contents)


@when(
    "etcd.available", "cni.available", "kubernetes-master.auth-webhook-service.started"
)
@when_not("kubernetes-master.apiserver.configured")
def configure_apiserver():
    etcd_connection_string = endpoint_from_flag(
        "etcd.available"
    ).get_connection_string()
    if not etcd_connection_string:
        # etcd is not returning a connection string. This happens when
        # the master unit disconnects from etcd and is ready to terminate.
        # No point in trying to start master services and fail. Just return.
        return

    # Update unit db service-cidr
    was_service_cidr_expanded = kubernetes_master.is_service_cidr_expansion()
    kubernetes_master.freeze_service_cidr()

    cluster_cidr = kubernetes_common.cluster_cidr()
    service_cidr = kubernetes_master.service_cidr()

    api_opts = {}

    if is_privileged():
        api_opts["allow-privileged"] = "true"
        set_state("kubernetes-master.privileged")
    else:
        api_opts["allow-privileged"] = "false"
        remove_state("kubernetes-master.privileged")

    # Handle static options for now
    api_opts["service-cluster-ip-range"] = service_cidr
    # Enable StreamingProxyRedirects to work around `kubectl exec` failures
    # when passing through kubeapi-load-balancer. This feature will be removed
    # in k8s 1.24.
    # https://bugs.launchpad.net/bugs/1940527
    feature_gates = ["StreamingProxyRedirects=true"]
    if kubernetes_common.is_dual_stack(cluster_cidr):
        feature_gates.append("IPv6DualStack=true")
    api_opts["min-request-timeout"] = "300"
    api_opts["v"] = "4"
    api_opts["tls-cert-file"] = str(server_crt_path)
    api_opts["tls-private-key-file"] = str(server_key_path)
    api_opts["kubelet-certificate-authority"] = str(ca_crt_path)
    api_opts["kubelet-client-certificate"] = str(client_crt_path)
    api_opts["kubelet-client-key"] = str(client_key_path)
    api_opts["logtostderr"] = "true"
    api_opts["storage-backend"] = getStorageBackend()
    api_opts["insecure-port"] = "0"
    api_opts["profiling"] = "false"

    api_opts["anonymous-auth"] = "false"
    api_opts["authentication-token-webhook-cache-ttl"] = "1m0s"
    api_opts["authentication-token-webhook-config-file"] = auth_webhook_conf
    api_opts["service-account-issuer"] = "https://kubernetes.default.svc"
    api_opts["service-account-signing-key-file"] = "/root/cdk/serviceaccount.key"
    api_opts["service-account-key-file"] = "/root/cdk/serviceaccount.key"
    api_opts[
        "kubelet-preferred-address-types"
    ] = "InternalIP,Hostname,InternalDNS,ExternalDNS,ExternalIP"
    api_opts["encryption-provider-config"] = str(encryption_config_path())
    if kubernetes_common.is_ipv6(cluster_cidr):
        api_opts["bind-address"] = "::"
    if kubernetes_common.is_ipv6_preferred(cluster_cidr):
        api_opts["advertise-address"] = get_ingress_address6("kube-control")
    else:
        api_opts["advertise-address"] = get_ingress_address("kube-control")

    etcd_dir = "/root/cdk/etcd"
    etcd_ca = os.path.join(etcd_dir, "client-ca.pem")
    etcd_key = os.path.join(etcd_dir, "client-key.pem")
    etcd_cert = os.path.join(etcd_dir, "client-cert.pem")

    api_opts["etcd-cafile"] = etcd_ca
    api_opts["etcd-keyfile"] = etcd_key
    api_opts["etcd-certfile"] = etcd_cert
    api_opts["etcd-servers"] = etcd_connection_string

    # In Kubernetes 1.10 and later, some admission plugins are enabled by
    # default. The current list of default plugins can be found at
    # https://bit.ly/2meP9XT, listed under the '--enable-admission-plugins'
    # option.
    #
    # The list below need only include the plugins we want to enable
    # in addition to the defaults.

    admission_plugins = [
        "PersistentVolumeLabel",
        "PodSecurityPolicy",
        "NodeRestriction",
    ]

    auth_mode = hookenv.config("authorization-mode")

    ks = endpoint_from_flag("keystone-credentials.available")
    if ks:
        ks_ip = None
        ks_ip = get_service_ip("k8s-keystone-auth-service", errors_fatal=False)
        if ks and ks_ip:
            os.makedirs(keystone_root, exist_ok=True)

            keystone_webhook = keystone_root + "/webhook.yaml"
            context = {}
            context["keystone_service_cluster_ip"] = ks_ip
            render("keystone-api-server-webhook.yaml", keystone_webhook, context)

            if hookenv.config("enable-keystone-authorization"):
                # if user wants authorization, enable it
                if "Webhook" not in auth_mode:
                    auth_mode += ",Webhook"
                api_opts["authorization-webhook-config-file"] = keystone_webhook  # noqa
            set_state("keystone.apiserver.configured")
        else:
            if ks and not ks_ip:
                hookenv.log(
                    "Unable to find k8s-keystone-auth-service " "service. Will retry"
                )
                # Note that we can get into a nasty state here
                # if the user has specified webhook and they're relying on
                # keystone auth to handle that, the api server will fail to
                # start because we push it Webhook and no webhook config.
                # We can't generate the config because we can't talk to the
                # apiserver to get the ip of the service to put into the
                # webhook template. A chicken and egg problem. To fix this,
                # remove Webhook if keystone is related and trying to come
                # up until we can find the service IP.
                if "Webhook" in auth_mode:
                    auth_mode = ",".join(
                        [i for i in auth_mode.split(",") if i != "Webhook"]
                    )
            elif is_state("leadership.set.keystone-cdk-addons-configured"):
                hookenv.log("Unable to find keystone endpoint. Will retry")
            remove_state("keystone.apiserver.configured")

    api_opts["authorization-mode"] = auth_mode
    api_opts["enable-admission-plugins"] = ",".join(admission_plugins)

    kube_version = get_version("kube-apiserver")

    if kube_version > (1, 6) and hookenv.config("enable-metrics"):
        api_opts["requestheader-client-ca-file"] = str(ca_crt_path)
        api_opts["requestheader-allowed-names"] = "system:kube-apiserver,client"
        api_opts["requestheader-extra-headers-prefix"] = "X-Remote-Extra-"
        api_opts["requestheader-group-headers"] = "X-Remote-Group"
        api_opts["requestheader-username-headers"] = "X-Remote-User"
        api_opts["proxy-client-cert-file"] = str(client_crt_path)
        api_opts["proxy-client-key-file"] = str(client_key_path)
        api_opts["enable-aggregator-routing"] = "true"
        api_opts["client-ca-file"] = str(ca_crt_path)

    api_cloud_config_path = cloud_config_path("kube-apiserver")
    if is_state("endpoint.aws.ready"):
        api_opts["cloud-provider"] = "aws"
        feature_gates.append("CSIMigrationAWS=false")
    elif is_state("endpoint.gcp.ready"):
        api_opts["cloud-provider"] = "gce"
        api_opts["cloud-config"] = str(api_cloud_config_path)
        feature_gates.append("CSIMigrationGCE=false")
    elif is_state("endpoint.vsphere.ready") and get_version("kube-apiserver") >= (
        1,
        12,
    ):
        api_opts["cloud-provider"] = "vsphere"
        api_opts["cloud-config"] = str(api_cloud_config_path)
    elif is_state("endpoint.azure.ready"):
        api_opts["cloud-provider"] = "azure"
        api_opts["cloud-config"] = str(api_cloud_config_path)
        feature_gates.append("CSIMigrationAzureDisk=false")

    api_opts["feature-gates"] = ",".join(feature_gates)

    audit_root = "/root/cdk/audit"
    os.makedirs(audit_root, exist_ok=True)

    audit_log_path = audit_root + "/audit.log"
    api_opts["audit-log-path"] = audit_log_path
    api_opts["audit-log-maxage"] = "30"
    api_opts["audit-log-maxsize"] = "100"
    api_opts["audit-log-maxbackup"] = "10"

    audit_policy_path = audit_root + "/audit-policy.yaml"
    audit_policy = hookenv.config("audit-policy")
    if audit_policy:
        write_file_with_autogenerated_header(audit_policy_path, audit_policy)
        api_opts["audit-policy-file"] = audit_policy_path
    else:
        remove_if_exists(audit_policy_path)

    audit_webhook_config_path = audit_root + "/audit-webhook-config.yaml"
    audit_webhook_config = hookenv.config("audit-webhook-config")
    if audit_webhook_config:
        write_file_with_autogenerated_header(
            audit_webhook_config_path, audit_webhook_config
        )
        api_opts["audit-webhook-config-file"] = audit_webhook_config_path
    else:
        remove_if_exists(audit_webhook_config_path)

    configure_kubernetes_service(
        configure_prefix, "kube-apiserver", api_opts, "api-extra-args"
    )
    service_restart("snap.kube-apiserver.daemon")

    if was_service_cidr_expanded and is_state("leadership.is_leader"):
        set_flag("kubernetes-master.had-service-cidr-expanded")

    set_flag("kubernetes-master.apiserver.configured")
    if kubernetes_master.check_service("kube-apiserver"):
        set_flag("kubernetes-master.apiserver.running")


@when("kubernetes-master.apiserver.configured")
@when_not("kubernetes-master.apiserver.running")
def check_apiserver():
    if kubernetes_master.check_service("kube-apiserver"):
        set_flag("kubernetes-master.apiserver.running")


@when(
    "kubernetes-master.had-service-cidr-expanded",
    "kubernetes-master.apiserver.configured",
    "leadership.is_leader",
)
def update_for_service_cidr_expansion():
    # We just restarted the API server, so there's a decent chance it's
    # not up yet. Keep trying to get the svcs list until we can; get_svcs
    # has a built-in retry and delay, so this should try for around 30s.
    def _wait_for_svc_ip():
        for attempt in range(10):
            svcs = get_svcs()
            if svcs:
                svc_ip = {
                    svc["metadata"]["name"]: svc["spec"]["clusterIP"]
                    for svc in svcs["items"]
                }.get("kubernetes")
                if svc_ip:
                    return svc_ip
        else:
            return None

    hookenv.log("service-cidr expansion: Waiting for API service")
    # First network is the default, which is used for the API service's address.
    # This logic will likely need to change once dual-stack services are
    # supported: https://bit.ly/2YlbxOx
    expected_service_ip = kubernetes_master.get_kubernetes_service_ips()[0]
    actual_service_ip = _wait_for_svc_ip()
    if not actual_service_ip:
        hookenv.log("service-cidr expansion: Timed out waiting for API service")
        return
    try:
        if actual_service_ip != expected_service_ip:
            hookenv.log("service-cidr expansion: Deleting service kubernetes")
            kubectl("delete", "service", "kubernetes")
            actual_service_ip = _wait_for_svc_ip()
            if not actual_service_ip:
                # we might need another restart to get the service recreated
                hookenv.log(
                    "service-cidr expansion: Timed out waiting for "
                    "the service to return; restarting API server"
                )
                clear_flag("kubernetes-master.apiserver.configured")
                return
            if actual_service_ip != expected_service_ip:
                raise ValueError(
                    "Unexpected service IP: {} != {}".format(
                        actual_service_ip, expected_service_ip
                    )
                )

        # Restart the cdk-addons
        # Get deployments/daemonsets/statefulsets
        hookenv.log("service-cidr expansion: Restart the cdk-addons")
        output = kubectl(
            "get",
            "daemonset,deployment,statefulset",
            "-o",
            "json",
            "--all-namespaces",
            "-l",
            "cdk-restart-on-ca-change=true",
        ).decode("UTF-8")
        deployments = json.loads(output)["items"]

        # Now restart the addons
        for deployment in deployments:
            kind = deployment["kind"]
            namespace = deployment["metadata"]["namespace"]
            name = deployment["metadata"]["name"]
            hookenv.log("Restarting addon: {0} {1} {2}".format(kind, namespace, name))
            kubectl("rollout", "restart", kind + "/" + name, "-n", namespace)
    except CalledProcessError:
        # the kubectl calls already log the command and don't capture stderr,
        # so logging the exception is a bit superfluous
        hookenv.log("service-cidr expansion: failed to restart components")
    else:
        clear_flag("kubernetes-master.had-service-cidr-expanded")


def configure_controller_manager():
    controller_opts = {}
    cluster_cidr = kubernetes_common.cluster_cidr()
    service_cidr = kubernetes_master.service_cidr()

    # Default to 3 minute resync. TODO: Make this configurable?
    controller_opts["min-resync-period"] = "3m"
    controller_opts["v"] = "2"
    controller_opts["root-ca-file"] = str(ca_crt_path)
    controller_opts["logtostderr"] = "true"
    controller_opts["kubeconfig"] = kubecontrollermanagerconfig_path
    controller_opts["authorization-kubeconfig"] = kubecontrollermanagerconfig_path
    controller_opts["authentication-kubeconfig"] = kubecontrollermanagerconfig_path
    controller_opts["use-service-account-credentials"] = "true"
    controller_opts["service-account-private-key-file"] = "/root/cdk/serviceaccount.key"
    controller_opts["tls-cert-file"] = str(server_crt_path)
    controller_opts["tls-private-key-file"] = str(server_key_path)
    controller_opts["cluster-name"] = leader_get("cluster_tag")
    controller_opts["terminated-pod-gc-threshold"] = "12500"
    controller_opts["profiling"] = "false"
    controller_opts["service-cluster-ip-range"] = service_cidr
    controller_opts["cluster-cidr"] = cluster_cidr
    feature_gates = ["RotateKubeletServerCertificate=true"]
    if kubernetes_common.is_dual_stack(cluster_cidr):
        feature_gates.append("IPv6DualStack=true")
    net_ipv6 = kubernetes_common.get_ipv6_network(cluster_cidr)
    if net_ipv6:
        controller_opts["node-cidr-mask-size-ipv6"] = net_ipv6.prefixlen

    cm_cloud_config_path = cloud_config_path("kube-controller-manager")
    if is_state("endpoint.aws.ready"):
        controller_opts["cloud-provider"] = "aws"
        feature_gates.append("CSIMigrationAWS=false")
    elif is_state("endpoint.gcp.ready"):
        controller_opts["cloud-provider"] = "gce"
        controller_opts["cloud-config"] = str(cm_cloud_config_path)
        feature_gates.append("CSIMigrationGCE=false")
    elif is_state("endpoint.vsphere.ready") and get_version("kube-apiserver") >= (
        1,
        12,
    ):
        controller_opts["cloud-provider"] = "vsphere"
        controller_opts["cloud-config"] = str(cm_cloud_config_path)
    elif is_state("endpoint.azure.ready"):
        controller_opts["cloud-provider"] = "azure"
        controller_opts["cloud-config"] = str(cm_cloud_config_path)
        feature_gates.append("CSIMigrationAzureDisk=false")

    controller_opts["feature-gates"] = ",".join(feature_gates)

    configure_kubernetes_service(
        configure_prefix,
        "kube-controller-manager",
        controller_opts,
        "controller-manager-extra-args",
    )
    service_restart("snap.kube-controller-manager.daemon")


def configure_scheduler():
    kube_scheduler_config_path = "/root/cdk/kube-scheduler-config.yaml"

    scheduler_opts = {}

    scheduler_opts["v"] = "2"
    scheduler_opts["logtostderr"] = "true"
    scheduler_opts["profiling"] = "false"
    scheduler_opts["config"] = kube_scheduler_config_path

    feature_gates = []

    if is_state("endpoint.aws.ready"):
        feature_gates.append("CSIMigrationAWS=false")
    elif is_state("endpoint.gcp.ready"):
        feature_gates.append("CSIMigrationGCE=false")
    elif is_state("endpoint.azure.ready"):
        feature_gates.append("CSIMigrationAzureDisk=false")

    scheduler_opts["feature-gates"] = ",".join(feature_gates)

    scheduler_ver = get_version("kube-scheduler")
    if scheduler_ver >= (1, 23):
        api_ver = "v1beta2"
    elif scheduler_ver >= (1, 19):
        api_ver = "v1beta1"
    elif scheduler_ver >= (1, 18):
        api_ver = "v1alpha2"
    else:
        api_ver = "v1alpha1"

    host.write_file(
        path=kube_scheduler_config_path,
        perms=0o600,
        content=yaml.safe_dump(
            {
                "apiVersion": "kubescheduler.config.k8s.io/{}".format(api_ver),
                "kind": "KubeSchedulerConfiguration",
                "clientConnection": {"kubeconfig": kubeschedulerconfig_path},
            }
        ),
    )

    configure_kubernetes_service(
        configure_prefix, "kube-scheduler", scheduler_opts, "scheduler-extra-args"
    )

    service_restart("snap.kube-scheduler.daemon")


def setup_tokens(token, username, user, groups=None):
    """Create a token for kubernetes authentication.

    Create a new secret if known_tokens have been migrated. Otherwise,
    add an entry to the 'known_tokens.csv' file.
    """
    if not token:
        token = kubernetes_master.token_generator()
    if is_flag_set("kubernetes-master.token-auth.migrated"):
        # We need the apiserver before we can create secrets.
        if is_flag_set("kubernetes-master.apiserver.configured"):
            kubernetes_master.create_secret(token, username, user, groups)
        else:
            hookenv.log("Delaying secret creation until the apiserver is configured.")
    else:
        kubernetes_master.create_known_token(token, username, user, groups)


def get_token(username):
    """Fetch a token for the given username.

    Grab a token from the given user's secret if known_tokens have been
    migrated. Otherwise, fetch it from the 'known_tokens.csv' file.
    """
    if is_flag_set("kubernetes-master.token-auth.migrated"):
        return kubernetes_common.get_secret_password(username)
    else:
        return kubernetes_master.get_csv_password("known_tokens.csv", username)


def set_token(password, save_salt):
    """Store a token so it can be recalled later by token_generator.

    param: password - the password to be stored
    param: save_salt - the key to store the value of the token."""
    db.set(save_salt, password)
    return db.get(save_salt)


@retry(times=3, delay_secs=1)
def get_pods(namespace="default"):
    try:
        output = kubectl(
            "get", "po", "-n", namespace, "-o", "json", "--request-timeout", "10s"
        ).decode("UTF-8")
        result = json.loads(output)
    except CalledProcessError:
        hookenv.log("failed to get {} pod status".format(namespace))
        return None
    return result


@retry(times=3, delay_secs=1)
def get_svcs(namespace="default"):
    try:
        output = kubectl(
            "get", "svc", "-n", namespace, "-o", "json", "--request-timeout", "10s"
        ).decode("UTF-8")
        result = json.loads(output)
    except CalledProcessError:
        hookenv.log("failed to get {} service status".format(namespace))
        return None
    return result


class FailedToGetPodStatus(Exception):
    pass


def get_kube_system_pods_not_running():
    """Check pod status in the kube-system namespace. Throws
    FailedToGetPodStatus if unable to determine pod status. This can
    occur when the api server is not currently running. On success,
    returns a list of pods that are not currently running
    or an empty list if all are running."""

    result = get_pods("kube-system")
    if result is None:
        raise FailedToGetPodStatus

    hookenv.log(
        "Checking system pods status: {}".format(
            ", ".join(
                "=".join([pod["metadata"]["name"], pod["status"]["phase"]])
                for pod in result["items"]
            )
        )
    )

    # Pods that are Running or Evicted (which should re-spawn) are
    # considered running
    not_running = [
        pod
        for pod in result["items"]
        if pod["status"]["phase"] != "Running"
        and pod["status"].get("reason", "") != "Evicted"
    ]

    pending = [pod for pod in result["items"] if pod["status"]["phase"] == "Pending"]
    any_pending = len(pending) > 0
    if is_state("endpoint.gcp.ready") and any_pending:
        poke_network_unavailable()
        return not_running

    return not_running


def poke_network_unavailable():
    """
    Work around https://github.com/kubernetes/kubernetes/issues/44254 by
    manually poking the status into the API server to tell the nodes they have
    a network route.

    This is needed because kubelet sets the NetworkUnavailable flag and expects
    the network plugin to clear it, which only kubenet does. There is some
    discussion about refactoring the affected code but nothing has happened
    in a while.
    """
    internal_endpoints = kubernetes_master.get_internal_api_endpoints()
    internal_url = kubernetes_master.get_api_url(internal_endpoints)

    client_token = get_token("admin")
    http_header = ("Authorization", "Bearer {}".format(client_token))

    try:
        output = kubectl("get", "nodes", "-o", "json").decode("utf-8")
        nodes = json.loads(output)["items"]
    except CalledProcessError:
        hookenv.log("failed to get kube-system nodes")
        return
    except (KeyError, json.JSONDecodeError) as e:
        hookenv.log(
            "failed to parse kube-system node status " "({}): {}".format(e, output),
            hookenv.ERROR,
        )
        return

    for node in nodes:
        node_name = node["metadata"]["name"]
        url = "{}/api/v1/nodes/{}/status".format(internal_url, node_name)
        req = Request(url)
        req.add_header(*http_header)
        with urlopen(req) as response:
            code = response.getcode()
            body = response.read().decode("utf8")
        if code != 200:
            hookenv.log(
                "failed to get node status from {} [{}]: {}".format(url, code, body),
                hookenv.ERROR,
            )
            return
        try:
            node_info = json.loads(body)
            conditions = node_info["status"]["conditions"]
            i = [c["type"] for c in conditions].index("NetworkUnavailable")
            if conditions[i]["status"] == "True":
                hookenv.log("Clearing NetworkUnavailable from {}".format(node_name))
                conditions[i] = {
                    "type": "NetworkUnavailable",
                    "status": "False",
                    "reason": "RouteCreated",
                    "message": "Manually set through k8s api",
                }
                req = Request(
                    url,
                    method="PUT",
                    data=json.dumps(node_info).encode("utf8"),
                    headers={"Content-Type": "application/json"},
                )
                req.add_header(*http_header)
                with urlopen(req) as response:
                    code = response.getcode()
                    body = response.read().decode("utf8")
                if code not in (200, 201, 202):
                    hookenv.log(
                        "failed to update node status [{}]: {}".format(code, body),
                        hookenv.ERROR,
                    )
                    return
        except (json.JSONDecodeError, KeyError):
            hookenv.log("failed to parse node status: {}".format(body), hookenv.ERROR)
            return


def apiserverVersion():
    cmd = "kube-apiserver --version".split()
    version_string = check_output(cmd).decode("utf-8")
    return tuple(int(q) for q in re.findall("[0-9]+", version_string)[:3])


def touch(fname):
    try:
        os.utime(fname, None)
    except OSError:
        open(fname, "a").close()


def getStorageBackend():
    storage_backend = hookenv.config("storage-backend")
    if storage_backend == "auto":
        storage_backend = leader_get("auto_storage_backend")
    return storage_backend


@when("leadership.is_leader")
@when_not("leadership.set.cluster_tag")
def create_cluster_tag():
    cluster_tag = "kubernetes-{}".format(kubernetes_master.token_generator().lower())
    leader_set(cluster_tag=cluster_tag)


@when("leadership.set.cluster_tag", "kube-control.connected")
def send_cluster_tag():
    cluster_tag = leader_get("cluster_tag")
    kube_control = endpoint_from_flag("kube-control.connected")
    kube_control.set_cluster_tag(cluster_tag)


@when_not("kube-control.connected")
def clear_cluster_tag_sent():
    remove_state("kubernetes-master.cluster-tag-sent")


@when_any(
    "endpoint.aws.joined",
    "endpoint.gcp.joined",
    "endpoint.openstack.joined",
    "endpoint.vsphere.joined",
    "endpoint.azure.joined",
)
@when_not("kubernetes-master.cloud.ready")
def set_cloud_pending():
    k8s_version = get_version("kube-apiserver")
    k8s_1_11 = k8s_version >= (1, 11)
    k8s_1_12 = k8s_version >= (1, 12)
    vsphere_joined = is_state("endpoint.vsphere.joined")
    azure_joined = is_state("endpoint.azure.joined")
    if (vsphere_joined and not k8s_1_12) or (azure_joined and not k8s_1_11):
        set_state("kubernetes-master.cloud.blocked")
    else:
        remove_state("kubernetes-master.cloud.blocked")
    set_state("kubernetes-master.cloud.pending")


@when_any("endpoint.aws.joined", "endpoint.gcp.joined", "endpoint.azure.joined")
@when("leadership.set.cluster_tag")
@when_not("kubernetes-master.cloud.request-sent")
def request_integration():
    hookenv.status_set("maintenance", "requesting cloud integration")
    cluster_tag = leader_get("cluster_tag")
    if is_state("endpoint.aws.joined"):
        cloud = endpoint_from_flag("endpoint.aws.joined")
        cloud.tag_instance(
            {
                "kubernetes.io/cluster/{}".format(cluster_tag): "owned",
                "k8s.io/role/master": "true",
            }
        )
        cloud.tag_instance_security_group(
            {
                "kubernetes.io/cluster/{}".format(cluster_tag): "owned",
            }
        )
        cloud.tag_instance_subnet(
            {
                "kubernetes.io/cluster/{}".format(cluster_tag): "owned",
            }
        )
        cloud.enable_object_storage_management(["kubernetes-*"])
        cloud.enable_load_balancer_management()
    elif is_state("endpoint.gcp.joined"):
        cloud = endpoint_from_flag("endpoint.gcp.joined")
        cloud.label_instance(
            {
                "k8s-io-cluster-name": cluster_tag,
                "k8s-io-role-master": "master",
            }
        )
        cloud.enable_object_storage_management()
        cloud.enable_security_management()
    elif is_state("endpoint.azure.joined"):
        cloud = endpoint_from_flag("endpoint.azure.joined")
        cloud.tag_instance(
            {
                "k8s-io-cluster-name": cluster_tag,
                "k8s-io-role-master": "master",
            }
        )
        cloud.enable_object_storage_management()
        cloud.enable_security_management()
        cloud.enable_loadbalancer_management()
    cloud.enable_instance_inspection()
    cloud.enable_network_management()
    cloud.enable_dns_management()
    cloud.enable_block_storage_management()
    set_state("kubernetes-master.cloud.request-sent")


@when_none(
    "endpoint.aws.joined",
    "endpoint.gcp.joined",
    "endpoint.openstack.joined",
    "endpoint.vsphere.joined",
    "endpoint.azure.joined",
)
@when_any(
    "kubernetes-master.cloud.pending",
    "kubernetes-master.cloud.request-sent",
    "kubernetes-master.cloud.blocked",
    "kubernetes-master.cloud.ready",
)
def clear_cloud_flags():
    remove_state("kubernetes-master.cloud.pending")
    remove_state("kubernetes-master.cloud.request-sent")
    remove_state("kubernetes-master.cloud.blocked")
    remove_state("kubernetes-master.cloud.ready")
    clear_flag("kubernetes-master.apiserver.configured")
    _kick_controller_manager()


@when_any(
    "endpoint.aws.ready",
    "endpoint.gcp.ready",
    "endpoint.openstack.ready",
    "endpoint.vsphere.ready",
    "endpoint.azure.ready",
)
@when_not("kubernetes-master.cloud.blocked", "kubernetes-master.cloud.ready")
def cloud_ready():
    if is_state("endpoint.gcp.ready"):
        write_gcp_snap_config("kube-apiserver")
        write_gcp_snap_config("kube-controller-manager")
    elif is_state("endpoint.vsphere.ready"):
        _write_vsphere_snap_config("kube-apiserver")
        _write_vsphere_snap_config("kube-controller-manager")
    elif is_state("endpoint.azure.ready"):
        write_azure_snap_config("kube-apiserver")
        write_azure_snap_config("kube-controller-manager")
    remove_state("kubernetes-master.cloud.pending")
    set_state("kubernetes-master.cloud.ready")
    remove_state("kubernetes-master.components.started")  # force restart


@when("kubernetes-master.cloud.ready")
@when_any(
    "endpoint.openstack.ready.changed",
    "endpoint.vsphere.ready.changed",
    "endpoint.azure.ready.changed",
)
def update_cloud_config():
    """Signal that cloud config has changed.

    Some clouds (openstack, vsphere) support runtime config that needs to be
    reflected in the k8s cloud config files when changed. Manage flags to
    ensure this happens.
    """
    if is_state("endpoint.openstack.ready.changed"):
        remove_state("endpoint.openstack.ready.changed")
        set_state("kubernetes-master.openstack.changed")
    if is_state("endpoint.vsphere.ready.changed"):
        remove_state("kubernetes-master.cloud.ready")
        remove_state("endpoint.vsphere.ready.changed")
    if is_state("endpoint.azure.ready.changed"):
        remove_state("kubernetes-master.cloud.ready")
        remove_state("endpoint.azure.ready.changed")


def _cdk_addons_template_path():
    return Path("/snap/cdk-addons/current/templates")


def _write_vsphere_snap_config(component):
    # vsphere requires additional cloud config
    vsphere = endpoint_from_flag("endpoint.vsphere.ready")

    # NB: vsphere provider will ask kube-apiserver and -controller-manager to
    # find a uuid from sysfs unless a global config value is set. Our strict
    # snaps cannot read sysfs, so let's do it in the charm. An invalid uuid is
    # not fatal for storage, but it will muddy the logs; try to get it right.
    uuid = _get_vmware_uuid()

    comp_cloud_config_path = cloud_config_path(component)
    comp_cloud_config_path.write_text(
        "\n".join(
            [
                "[Global]",
                "insecure-flag = true",
                'datacenters = "{}"'.format(vsphere.datacenter),
                'vm-uuid = "VMware-{}"'.format(uuid),
                '[VirtualCenter "{}"]'.format(vsphere.vsphere_ip),
                'user = "{}"'.format(vsphere.user),
                'password = "{}"'.format(vsphere.password),
                "[Workspace]",
                'server = "{}"'.format(vsphere.vsphere_ip),
                'datacenter = "{}"'.format(vsphere.datacenter),
                'default-datastore = "{}"'.format(vsphere.datastore),
                'folder = "{}"'.format(vsphere.folder),
                'resourcepool-path = "{}"'.format(vsphere.respool_path),
                "[Disk]",
                'scsicontrollertype = "pvscsi"',
            ]
        )
    )


@when("config.changed.keystone-policy")
@when("kubernetes-master.keystone-policy-handled")
def regen_keystone_policy():
    clear_flag("kubernetes-master.keystone-policy-handled")


@when(
    "keystone-credentials.available",
    "leadership.is_leader",
    "kubernetes-master.apiserver.configured",
)
@when_not("kubernetes-master.keystone-policy-handled")
def generate_keystone_configmap():
    keystone_policy = hookenv.config("keystone-policy")
    if keystone_policy:
        os.makedirs(keystone_root, exist_ok=True)
        write_file_with_autogenerated_header(keystone_policy_path, keystone_policy)
        if kubectl_manifest("apply", keystone_policy_path):
            set_flag("kubernetes-master.keystone-policy-handled")
            clear_flag("kubernetes-master.keystone-policy-error")
        else:
            set_flag("kubernetes-master.keystone-policy-error")
    else:
        # a missing policy configmap will crashloop the pods, but...
        # what do we do in this situation. We could just do nothing,
        # but that isn't cool for the user so we surface an error
        # and wait for them to fix it.
        set_flag("kubernetes-master.keystone-policy-error")

    # note that information is surfaced to the user in the code above where we
    # write status. It will notify the user we are waiting on the policy file
    # to apply if the keystone-credentials.available flag is set, but
    # kubernetes-master.keystone-policy-handled is not set.


@when("leadership.is_leader", "kubernetes-master.keystone-policy-handled")
@when_not("keystone-credentials.available")
def remove_keystone():
    clear_flag("kubernetes-master.apiserver.configured")
    if not os.path.exists(keystone_policy_path):
        clear_flag("kubernetes-master.keystone-policy-handled")
    elif kubectl_manifest("delete", keystone_policy_path):
        os.remove(keystone_policy_path)
        clear_flag("kubernetes-master.keystone-policy-handled")


@when("keystone-credentials.connected")
def setup_keystone_user():
    # This seems silly, but until we request a user from keystone
    # we don't get information about the keystone server...
    ks = endpoint_from_flag("keystone-credentials.connected")
    ks.request_credentials("k8s")


def _kick_controller_manager():
    if is_flag_set("kubernetes-master.components.started"):
        configure_controller_manager()


@when(
    "keystone.credentials.configured", "leadership.set.keystone-cdk-addons-configured"
)
@when_not("keystone.apiserver.configured")
def keystone_kick_apiserver():
    clear_flag("kubernetes-master.apiserver.configured")


@when(
    "keystone-credentials.available",
    "certificates.ca.available",
    "certificates.client.cert.available",
    "authentication.setup",
    "etcd.available",
    "leadership.set.keystone-cdk-addons-configured",
)
def keystone_config():
    # first, we have to have the service set up before we can render this stuff
    ks = endpoint_from_flag("keystone-credentials.available")
    data = {
        "host": ks.credentials_host(),
        "proto": ks.credentials_protocol(),
        "port": ks.credentials_port(),
        "version": ks.api_version(),
    }
    if data_changed("keystone", data):
        remove_state("keystone.credentials.configured")
        clear_flag("kubernetes-master.apiserver.configured")
        build_kubeconfig()
        generate_keystone_configmap()
        set_state("keystone.credentials.configured")


@when("layer.vault-kv.app-kv.set.encryption_key", "layer.vaultlocker.ready")
@when_not("kubernetes-master.secure-storage.created")
def create_secure_storage():
    encryption_conf_dir = encryption_config_path().parent
    encryption_conf_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        vaultlocker.create_encrypted_loop_mount(encryption_conf_dir)
    except vaultlocker.VaultLockerError:
        # One common cause of this would be deploying on lxd.
        # Should this be more fatal?
        hookenv.log(
            "Unable to create encrypted mount for storing encryption config.\n"
            "{}".format(traceback.format_exc()),
            level=hookenv.ERROR,
        )
        set_flag("kubernetes-master.secure-storage.failed")
        clear_flag("kubernetes-master.secure-storage.created")
    else:
        # TODO: If Vault isn't available, it's probably still better to encrypt
        # anyway and store the key in plaintext and leadership than to just
        # give up on encryption entirely.
        _write_encryption_config()
        # prevent an unnecessary service restart on this
        # unit since we've already handled the change
        clear_flag("layer.vault-kv.app-kv.changed.encryption_key")
        # mark secure storage as ready
        set_flag("kubernetes-master.secure-storage.created")
        clear_flag("kubernetes-master.secure-storage.failed")
        # restart to regen config
        clear_flag("kubernetes-master.apiserver.configured")


@when_not("layer.vaultlocker.ready")
@when("kubernetes-master.secure-storage.created")
def revert_secure_storage():
    clear_flag("kubernetes-master.secure-storage.created")
    clear_flag("kubernetes-master.secure-storage.failed")
    clear_flag("kubernetes-master.apiserver.configured")


@when("leadership.is_leader", "layer.vault-kv.ready")
@when_not("layer.vault-kv.app-kv.set.encryption_key")
def generate_encryption_key():
    app_kv = vault_kv.VaultAppKV()
    app_kv["encryption_key"] = kubernetes_master.token_generator(32)


@when(
    "layer.vault-kv.app-kv.changed.encryption_key",
    "kubernetes-master.secure-storage.created",
)
def restart_apiserver_for_encryption_key():
    clear_flag("kubernetes-master.apiserver.configured")
    clear_flag("layer.vault-kv.app-kv.changed.encryption_key")


def _write_encryption_config():
    app_kv = vault_kv.VaultAppKV()
    encryption_config_path().parent.mkdir(parents=True, exist_ok=True)
    secret = app_kv["encryption_key"]
    secret = base64.b64encode(secret.encode("utf8")).decode("utf8")
    host.write_file(
        path=str(encryption_config_path()),
        perms=0o600,
        content=yaml.safe_dump(
            {
                "kind": "EncryptionConfig",
                "apiVersion": "v1",
                "resources": [
                    {
                        "resources": ["secrets"],
                        "providers": [
                            {
                                "aescbc": {
                                    "keys": [
                                        {
                                            "name": "key1",
                                            "secret": secret,
                                        }
                                    ],
                                }
                            },
                            {"identity": {}},
                        ],
                    }
                ],
            }
        ),
    )


@when_any("config.changed.pod-security-policy")
def pod_security_policy_config_changed():
    clear_flag("kubernetes-master.pod-security-policy.applied")


@when_any("config.changed.ha-cluster-vip", "config.changed.ha-cluster-dns")
def haconfig_changed():
    clear_flag("hacluster-configured")


@when("ha.connected", "kubernetes-master.components.started")
@when_not("hacluster-configured")
def configure_hacluster():
    for service in master_services:
        daemon = "snap.{}.daemon".format(service)
        add_service_to_hacluster(service, daemon)

    # get a new cert
    if is_flag_set("certificates.available"):
        send_data()

    # update workers
    if is_flag_set("kube-control.connected"):
        send_api_urls()
    if is_flag_set("kube-api-endpoint.available"):
        push_service_data()

    set_flag("hacluster-configured")


@when_not("ha.connected")
@when("hacluster-configured")
def remove_hacluster():
    for service in master_services:
        daemon = "snap.{}.daemon".format(service)
        remove_service_from_hacluster(service, daemon)

    # get a new cert
    if is_flag_set("certificates.available"):
        send_data()
    # update workers
    if is_flag_set("kube-control.connected"):
        send_api_urls()
    if is_flag_set("kube-api-endpoint.available"):
        push_service_data()

    clear_flag("hacluster-configured")


class InvalidDnsProvider(Exception):
    def __init__(self, value):
        self.value = value


def get_dns_provider():
    valid_dns_providers = ["auto", "core-dns", "kube-dns", "none"]
    if get_version("kube-apiserver") < (1, 14):
        valid_dns_providers.remove("core-dns")

    dns_provider = hookenv.config("dns-provider").lower()
    if dns_provider not in valid_dns_providers:
        raise InvalidDnsProvider(dns_provider)

    if dns_provider == "auto":
        dns_provider = leader_get("auto_dns_provider")
        # On new deployments, the first time this is called, auto_dns_provider
        # hasn't been set yet. We need to make a choice now.
        if not dns_provider:
            if "core-dns" in valid_dns_providers:
                dns_provider = "core-dns"
            else:
                dns_provider = "kube-dns"

    # LP: 1833089. Followers end up here when setting final status; ensure only
    # leaders call leader_set.
    if is_state("leadership.is_leader"):
        leader_set(auto_dns_provider=dns_provider)
    return dns_provider


@when("kube-control.connected")
@when_not("kubernetes-master.sent-registry")
def send_registry_location():
    registry_location = hookenv.config("image-registry")
    kube_control = endpoint_from_flag("kube-control.connected")

    # Send registry to workers
    kube_control.set_registry_location(registry_location)

    # Construct and send the sandbox image (pause container) to our runtime
    runtime = endpoint_from_flag("endpoint.container-runtime.available")
    if runtime:
        uri = "{}/pause-{}:3.1".format(registry_location, arch())
        runtime.set_config(sandbox_image=uri)

    set_flag("kubernetes-master.sent-registry")


@when("config.changed.image-registry")
def send_new_registry_location():
    clear_flag("kubernetes-master.sent-registry")


@when(
    "leadership.is_leader",
    "leadership.set.kubernetes-master-addons-restart-for-ca",
    "kubernetes-master.components.started",
)
def restart_addons_for_ca():
    try:
        # Get deployments/daemonsets/statefulsets
        output = kubectl(
            "get",
            "daemonset,deployment,statefulset",
            "-o",
            "json",
            "--all-namespaces",
            "-l",
            "cdk-restart-on-ca-change=true",
        ).decode("UTF-8")
        deployments = json.loads(output)["items"]

        # Get ServiceAccounts
        service_account_names = set(
            (
                deployment["metadata"]["namespace"],
                deployment["spec"]["template"]["spec"].get(
                    "serviceAccountName", "default"
                ),
            )
            for deployment in deployments
        )
        service_accounts = []
        for namespace, name in service_account_names:
            output = kubectl(
                "get", "ServiceAccount", name, "-o", "json", "-n", namespace
            ).decode("UTF-8")
            service_account = json.loads(output)
            service_accounts.append(service_account)

        # Get ServiceAccount secrets
        secret_names = set()
        for service_account in service_accounts:
            namespace = service_account["metadata"]["namespace"]
            for secret in service_account["secrets"]:
                secret_names.add((namespace, secret["name"]))
        secrets = []
        for namespace, name in secret_names:
            output = kubectl(
                "get", "Secret", name, "-o", "json", "-n", namespace
            ).decode("UTF-8")
            secret = json.loads(output)
            secrets.append(secret)

        # Check secrets have updated CA
        with open(ca_crt_path, "rb") as f:
            ca = f.read()
        encoded_ca = base64.b64encode(ca).decode("UTF-8")
        mismatched_secrets = [
            secret for secret in secrets if secret["data"]["ca.crt"] != encoded_ca
        ]
        if mismatched_secrets:
            hookenv.log(
                "ServiceAccount secrets do not have correct ca.crt: "
                + ",".join(secret["metadata"]["name"] for secret in mismatched_secrets)
            )
            hookenv.log("Waiting to retry restarting addons")
            return

        # Now restart the addons
        for deployment in deployments:
            kind = deployment["kind"]
            namespace = deployment["metadata"]["namespace"]
            name = deployment["metadata"]["name"]
            hookenv.log("Restarting addon: %s %s %s" % (kind, namespace, name))
            kubectl("rollout", "restart", kind + "/" + name, "-n", namespace)

        leader_set({"kubernetes-master-addons-restart-for-ca": None})
    except Exception:
        hookenv.log(traceback.format_exc())
        hookenv.log("Waiting to retry restarting addons")


def add_systemd_iptables_patch():
    source = "templates/kube-proxy-iptables-fix.sh"
    dest = "/usr/local/bin/kube-proxy-iptables-fix.sh"
    copyfile(source, dest)
    os.chmod(dest, 0o775)

    template = "templates/service-iptables-fix.service"
    dest_dir = "/etc/systemd/system"
    os.makedirs(dest_dir, exist_ok=True)
    service_name = "kube-proxy-iptables-fix.service"
    copyfile(template, "{}/{}".format(dest_dir, service_name))

    check_call(["systemctl", "daemon-reload"])

    # enable and run the service
    service_resume(service_name)


@when(
    "leadership.is_leader",
    "kubernetes-master.components.started",
    "endpoint.prometheus.joined",
    "certificates.ca.available",
)
def register_prometheus_jobs():
    prometheus = endpoint_from_flag("endpoint.prometheus.joined")
    tls = endpoint_from_flag("certificates.ca.available")
    monitoring_token = get_token("system:monitoring")

    for relation in prometheus.relations:
        endpoints = kubernetes_master.get_internal_api_endpoints(relation)
        if not endpoints:
            continue
        address, port = endpoints[0]

        templates_dir = Path("templates")
        for job_file in Path("templates/prometheus").glob("*.yaml.j2"):
            prometheus.register_job(
                relation=relation,
                job_name=job_file.name.split(".")[0],
                job_data=yaml.safe_load(
                    render(
                        source=str(job_file.relative_to(templates_dir)),
                        target=None,  # don't write file, just return data
                        context={
                            "k8s_api_address": address,
                            "k8s_api_port": port,
                            "k8s_token": monitoring_token,
                        },
                    )
                ),
                ca_cert=tls.root_ca_cert,
            )


def detect_telegraf():
    # Telegraf uses the implicit juju-info relation, which makes it difficult
    # to tell if it's related. The "best" option is to look for the subordinate
    # charm on disk.
    for charm_dir in Path("/var/lib/juju/agents").glob("unit-*/charm"):
        metadata = yaml.safe_load((charm_dir / "metadata.yaml").read_text())
        if "telegraf" in metadata["name"]:
            return True
    else:
        return False


@when(
    "leadership.is_leader",
    "kubernetes-master.components.started",
    "endpoint.grafana.joined",
)
def register_grafana_dashboards():
    grafana = endpoint_from_flag("endpoint.grafana.joined")

    # load conditional dashboards
    dash_dir = Path("templates/grafana/conditional")
    if is_flag_set("endpoint.prometheus.joined"):
        dashboard = (dash_dir / "prometheus.json").read_text()
        grafana.register_dashboard("prometheus", json.loads(dashboard))
    if detect_telegraf():
        dashboard = (dash_dir / "telegraf.json").read_text()
        grafana.register_dashboard("telegraf", json.loads(dashboard))

    # load automatic dashboards
    dash_dir = Path("templates/grafana/autoload")
    for dash_file in dash_dir.glob("*.json"):
        dashboard = dash_file.read_text()
        grafana.register_dashboard(dash_file.stem, json.loads(dashboard))


@when("endpoint.aws-iam.ready")
@when_not("kubernetes-master.aws-iam.configured")
def enable_aws_iam_webhook():
    # if etcd isn't available yet, we'll set this up later
    # when we start the api server.
    if is_flag_set("etcd.available"):
        # call the other things we need to update
        clear_flag("kubernetes-master.apiserver.configured")
        build_kubeconfig()
    set_flag("kubernetes-master.aws-iam.configured")


@when("kubernetes-master.components.started", "endpoint.aws-iam.available")
def api_server_started():
    aws_iam = endpoint_from_flag("endpoint.aws-iam.available")
    if aws_iam:
        aws_iam.set_api_server_status(True)


@when_not("kubernetes-master.components.started")
@when("endpoint.aws-iam.available")
def api_server_stopped():
    aws_iam = endpoint_from_flag("endpoint.aws-iam.available")
    if aws_iam:
        aws_iam.set_api_server_status(False)


@when("kube-control.connected")
def send_default_cni():
    """Send the value of the default-cni config to the kube-control relation.
    This allows kubernetes-worker to use the same config value as well.
    """
    default_cni = hookenv.config("default-cni")
    kube_control = endpoint_from_flag("kube-control.connected")
    kube_control.set_default_cni(default_cni)


@when("config.changed.default-cni")
def default_cni_changed():
    remove_state("kubernetes-master.components.started")
