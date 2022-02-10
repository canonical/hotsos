#!/usr/bin/env python

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

import ipaddress
import re
import os
import subprocess
import hashlib
import json
import traceback
import random
import string
import tempfile
import yaml

from base64 import b64decode, b64encode
from pathlib import Path
from subprocess import check_output, check_call
from socket import gethostname, getfqdn
from shlex import split
from subprocess import CalledProcessError
from charmhelpers.core import hookenv, unitdata
from charmhelpers.core import host
from charmhelpers.core.templating import render
from charms.reactive import endpoint_from_flag, is_state
from time import sleep

AUTH_SECRET_NS = "kube-system"
AUTH_SECRET_TYPE = "juju.is/token-auth"

db = unitdata.kv()
kubeclientconfig_path = "/root/.kube/config"
gcp_creds_env_key = "GOOGLE_APPLICATION_CREDENTIALS"
kubeproxyconfig_path = "/root/cdk/kubeproxyconfig"
certs_dir = Path("/root/cdk")
ca_crt_path = certs_dir / "ca.crt"
server_crt_path = certs_dir / "server.crt"
server_key_path = certs_dir / "server.key"
client_crt_path = certs_dir / "client.crt"
client_key_path = certs_dir / "client.key"


def get_version(bin_name):
    """Get the version of an installed Kubernetes binary.

    :param str bin_name: Name of binary
    :return: 3-tuple version (maj, min, patch)

    Example::

        >>> `get_version('kubelet')
        (1, 6, 0)

    """
    cmd = "{} --version".format(bin_name).split()
    version_string = subprocess.check_output(cmd).decode("utf-8")
    return tuple(int(q) for q in re.findall("[0-9]+", version_string)[:3])


def retry(times, delay_secs):
    """Decorator for retrying a method call.

    Args:
        times: How many times should we retry before giving up
        delay_secs: Delay in secs

    Returns: A callable that would return the last call outcome
    """

    def retry_decorator(func):
        """Decorator to wrap the function provided.

        Args:
            func: Provided function should return either True od False

        Returns: A callable that would return the last call outcome

        """

        def _wrapped(*args, **kwargs):
            res = func(*args, **kwargs)
            attempt = 0
            while not res and attempt < times:
                sleep(delay_secs)
                res = func(*args, **kwargs)
                if res:
                    break
                attempt += 1
            return res

        return _wrapped

    return retry_decorator


def calculate_resource_checksum(resource):
    """Calculate a checksum for a resource"""
    md5 = hashlib.md5()
    path = hookenv.resource_get(resource)
    if path:
        with open(path, "rb") as f:
            data = f.read()
        md5.update(data)
    return md5.hexdigest()


def get_resource_checksum_db_key(checksum_prefix, resource):
    """Convert a resource name to a resource checksum database key."""
    return checksum_prefix + resource


def migrate_resource_checksums(checksum_prefix, snap_resources):
    """Migrate resource checksums from the old schema to the new one"""
    for resource in snap_resources:
        new_key = get_resource_checksum_db_key(checksum_prefix, resource)
        if not db.get(new_key):
            path = hookenv.resource_get(resource)
            if path:
                # old key from charms.reactive.helpers.any_file_changed
                old_key = "reactive.files_changed." + path
                old_checksum = db.get(old_key)
                db.set(new_key, old_checksum)
            else:
                # No resource is attached. Previously, this meant no checksum
                # would be calculated and stored. But now we calculate it as if
                # it is a 0-byte resource, so let's go ahead and do that.
                zero_checksum = hashlib.md5().hexdigest()
                db.set(new_key, zero_checksum)


def check_resources_for_upgrade_needed(checksum_prefix, snap_resources):
    hookenv.status_set("maintenance", "Checking resources")
    for resource in snap_resources:
        key = get_resource_checksum_db_key(checksum_prefix, resource)
        old_checksum = db.get(key)
        new_checksum = calculate_resource_checksum(resource)
        if new_checksum != old_checksum:
            return True
    return False


def calculate_and_store_resource_checksums(checksum_prefix, snap_resources):
    for resource in snap_resources:
        key = get_resource_checksum_db_key(checksum_prefix, resource)
        checksum = calculate_resource_checksum(resource)
        db.set(key, checksum)


def get_ingress_address(endpoint_name, ignore_addresses=None):
    try:
        network_info = hookenv.network_get(endpoint_name)
    except NotImplementedError:
        network_info = {}

    if not network_info or "ingress-addresses" not in network_info:
        # if they don't have ingress-addresses they are running a juju that
        # doesn't support spaces, so just return the private address
        return hookenv.unit_get("private-address")

    addresses = network_info["ingress-addresses"]

    if ignore_addresses:
        hookenv.log("ingress-addresses before filtering: {}".format(addresses))
        iter_filter = filter(lambda item: item not in ignore_addresses, addresses)
        addresses = list(iter_filter)
        hookenv.log("ingress-addresses after filtering: {}".format(addresses))

    # Need to prefer non-fan IP addresses due to various issues, e.g.
    # https://bugs.launchpad.net/charm-gcp-integrator/+bug/1822997
    # Fan typically likes to use IPs in the 240.0.0.0/4 block, so we'll
    # prioritize those last. Not technically correct, but good enough.
    try:
        sort_key = lambda a: int(a.partition(".")[0]) >= 240  # noqa: E731
        addresses = sorted(addresses, key=sort_key)
    except Exception:
        hookenv.log(traceback.format_exc())

    return addresses[0]


def get_ingress_address6(endpoint_name):
    try:
        network_info = hookenv.network_get(endpoint_name)
    except NotImplementedError:
        network_info = {}

    if not network_info or "ingress-addresses" not in network_info:
        return None

    addresses = network_info["ingress-addresses"]

    for addr in addresses:
        ip_addr = ipaddress.ip_interface(addr).ip
        if ip_addr.version == 6:
            return str(ip_addr)
    else:
        return None


def service_restart(service_name):
    hookenv.status_set("maintenance", "Restarting {0} service".format(service_name))
    host.service_restart(service_name)


def service_start(service_name):
    hookenv.log("Starting {0} service.".format(service_name))
    host.service_stop(service_name)


def service_stop(service_name):
    hookenv.log("Stopping {0} service.".format(service_name))
    host.service_stop(service_name)


def arch():
    """Return the package architecture as a string. Raise an exception if the
    architecture is not supported by kubernetes."""
    # Get the package architecture for this system.
    architecture = check_output(["dpkg", "--print-architecture"]).rstrip()
    # Convert the binary result into a string.
    architecture = architecture.decode("utf-8")
    return architecture


def get_service_ip(service, namespace="kube-system", errors_fatal=True):
    try:
        output = kubectl(
            "get", "service", "--namespace", namespace, service, "--output", "json"
        )
    except CalledProcessError:
        if errors_fatal:
            raise
        else:
            return None
    else:
        svc = json.loads(output.decode())
        return svc["spec"]["clusterIP"]


def kubectl(*args):
    """Run a kubectl cli command with a config file. Returns stdout and throws
    an error if the command fails."""
    command = ["kubectl", "--kubeconfig=" + kubeclientconfig_path] + list(args)
    hookenv.log("Executing {}".format(command))
    return check_output(command)


def kubectl_success(*args):
    """Runs kubectl with the given args. Returns True if successful, False if
    not."""
    try:
        kubectl(*args)
        return True
    except CalledProcessError:
        return False


def kubectl_manifest(operation, manifest):
    """Wrap the kubectl creation command when using filepath resources
    :param operation - one of get, create, delete, replace
    :param manifest - filepath to the manifest
    """
    # Deletions are a special case
    if operation == "delete":
        # Ensure we immediately remove requested resources with --now
        return kubectl_success(operation, "-f", manifest, "--now")
    else:
        # Guard against an error re-creating the same manifest multiple times
        if operation == "create":
            # If we already have the definition, its probably safe to assume
            # creation was true.
            if kubectl_success("get", "-f", manifest):
                hookenv.log("Skipping definition for {}".format(manifest))
                return True
        # Execute the requested command that did not match any of the special
        # cases above
        return kubectl_success(operation, "-f", manifest)


def get_node_name():
    kubelet_extra_args = parse_extra_args("kubelet-extra-args")
    cloud_provider = kubelet_extra_args.get("cloud-provider", "")
    if is_state("endpoint.aws.ready"):
        cloud_provider = "aws"
    elif is_state("endpoint.gcp.ready"):
        cloud_provider = "gce"
    elif is_state("endpoint.openstack.ready"):
        cloud_provider = "openstack"
    elif is_state("endpoint.vsphere.ready"):
        cloud_provider = "vsphere"
    elif is_state("endpoint.azure.ready"):
        cloud_provider = "azure"
    if cloud_provider == "aws":
        return getfqdn().lower()
    else:
        return gethostname().lower()


def create_kubeconfig(
    kubeconfig,
    server,
    ca,
    key=None,
    certificate=None,
    user="ubuntu",
    context="juju-context",
    cluster="juju-cluster",
    password=None,
    token=None,
    keystone=False,
    aws_iam_cluster_id=None,
):
    """Create a configuration for Kubernetes based on path using the supplied
    arguments for values of the Kubernetes server, CA, key, certificate, user
    context and cluster."""
    if not key and not certificate and not password and not token:
        raise ValueError("Missing authentication mechanism.")
    elif key and not certificate:
        raise ValueError("Missing certificate.")
    elif not key and certificate:
        raise ValueError("Missing key.")
    elif token and password:
        # token and password are mutually exclusive. Error early if both are
        # present. The developer has requested an impossible situation.
        # see: kubectl config set-credentials --help
        raise ValueError("Token and Password are mutually exclusive.")

    old_kubeconfig = Path(kubeconfig)
    new_kubeconfig = Path(str(kubeconfig) + ".new")

    # Create the config file with the address of the master server.
    cmd = (
        "kubectl config --kubeconfig={0} set-cluster {1} "
        "--server={2} --certificate-authority={3} --embed-certs=true"
    )
    check_call(split(cmd.format(new_kubeconfig, cluster, server, ca)))
    # Delete old users
    cmd = "kubectl config --kubeconfig={0} unset users"
    check_call(split(cmd.format(new_kubeconfig)))
    # Create the credentials using the client flags.
    cmd = "kubectl config --kubeconfig={0} " "set-credentials {1} ".format(
        new_kubeconfig, user
    )

    if key and certificate:
        cmd = (
            "{0} --client-key={1} --client-certificate={2} "
            "--embed-certs=true".format(cmd, key, certificate)
        )
    if password:
        cmd = "{0} --username={1} --password={2}".format(cmd, user, password)
    # This is mutually exclusive from password. They will not work together.
    if token:
        cmd = "{0} --token={1}".format(cmd, token)
    check_call(split(cmd))
    # Create a default context with the cluster.
    cmd = "kubectl config --kubeconfig={0} set-context {1} " "--cluster={2} --user={3}"
    check_call(split(cmd.format(new_kubeconfig, context, cluster, user)))
    # Make the config use this new context.
    cmd = "kubectl config --kubeconfig={0} use-context {1}"
    check_call(split(cmd.format(new_kubeconfig, context)))
    if keystone:
        # create keystone user
        cmd = "kubectl config --kubeconfig={0} " "set-credentials keystone-user".format(
            new_kubeconfig
        )
        check_call(split(cmd))
        # create keystone context
        cmd = (
            "kubectl config --kubeconfig={0} "
            "set-context --cluster={1} "
            "--user=keystone-user keystone".format(new_kubeconfig, cluster)
        )
        check_call(split(cmd))
        # use keystone context
        cmd = "kubectl config --kubeconfig={0} " "use-context keystone".format(
            new_kubeconfig
        )
        check_call(split(cmd))
        # manually add exec command until kubectl can do it for us
        with open(new_kubeconfig, "r") as f:
            content = f.read()
            content = content.replace(
                """- name: keystone-user
  user: {}""",
                """- name: keystone-user
  user:
    exec:
      command: "/snap/bin/client-keystone-auth"
      apiVersion: "client.authentication.k8s.io/v1beta1"
""",
            )
        with open(new_kubeconfig, "w") as f:
            f.write(content)
    if aws_iam_cluster_id:
        # create aws-iam context
        cmd = (
            "kubectl config --kubeconfig={0} "
            "set-context --cluster={1} "
            "--user=aws-iam-user aws-iam-authenticator"
        )
        check_call(split(cmd.format(new_kubeconfig, cluster)))

        # append a user for aws-iam
        cmd = (
            "kubectl --kubeconfig={0} config set-credentials "
            "aws-iam-user --exec-command=aws-iam-authenticator "
            '--exec-arg="token" --exec-arg="-i" --exec-arg="{1}" '
            '--exec-arg="-r" --exec-arg="<<insert_arn_here>>" '
            "--exec-api-version=client.authentication.k8s.io/v1alpha1"
        )
        check_call(split(cmd.format(new_kubeconfig, aws_iam_cluster_id)))

        # not going to use aws-iam context by default since we don't have
        # the desired arn. This will make the config not usable if copied.

        # cmd = 'kubectl config --kubeconfig={0} ' \
        #       'use-context aws-iam-authenticator'.format(new_kubeconfig)
        # check_call(split(cmd))
    if old_kubeconfig.exists():
        changed = new_kubeconfig.read_text() != old_kubeconfig.read_text()
    else:
        changed = True
    if changed:
        new_kubeconfig.rename(old_kubeconfig)


def parse_extra_args(config_key):
    elements = hookenv.config().get(config_key, "").split()
    args = {}

    for element in elements:
        if "=" in element:
            key, _, value = element.partition("=")
            args[key] = value
        else:
            args[element] = "true"

    return args


def configure_kubernetes_service(key, service, base_args, extra_args_key):
    db = unitdata.kv()

    prev_args_key = key + service
    prev_snap_args = db.get(prev_args_key) or {}

    extra_args = parse_extra_args(extra_args_key)

    args = {}
    args.update(base_args)
    args.update(extra_args)

    # CIS benchmark action may inject kv config to pass failing tests. Merge
    # these after the func args as they should take precedence.
    cis_args_key = "cis-" + service
    cis_args = db.get(cis_args_key) or {}
    args.update(cis_args)

    # Remove any args with 'None' values (all k8s args are 'k=v') and
    # construct an arg string for use by 'snap set'.
    args = {k: v for k, v in args.items() if v is not None}
    args = ['--%s="%s"' % arg for arg in args.items()]
    args = " ".join(args)

    snap_opts = {}
    for arg in prev_snap_args:
        # remove previous args by setting to null
        snap_opts[arg] = "null"
    snap_opts["args"] = args
    snap_opts = ["%s=%s" % opt for opt in snap_opts.items()]

    cmd = ["snap", "set", service] + snap_opts
    check_call(cmd)

    # Now that we've started doing snap configuration through the "args"
    # option, we should never need to clear previous args again.
    db.set(prev_args_key, {})


def _snap_common_path(component):
    return Path("/var/snap/{}/common".format(component))


def cloud_config_path(component):
    return _snap_common_path(component) / "cloud-config.conf"


def _gcp_creds_path(component):
    return _snap_common_path(component) / "gcp-creds.json"


def _daemon_env_path(component):
    return _snap_common_path(component) / "environment"


def _cloud_endpoint_ca_path(component):
    return _snap_common_path(component) / "cloud-endpoint-ca.crt"


def encryption_config_path():
    apiserver_snap_common_path = _snap_common_path("kube-apiserver")
    encryption_conf_dir = apiserver_snap_common_path / "encryption"
    return encryption_conf_dir / "encryption_config.yaml"


def write_gcp_snap_config(component):
    # gcp requires additional credentials setup
    gcp = endpoint_from_flag("endpoint.gcp.ready")
    creds_path = _gcp_creds_path(component)
    with creds_path.open("w") as fp:
        os.fchmod(fp.fileno(), 0o600)
        fp.write(gcp.credentials)

    # create a cloud-config file that sets token-url to nil to make the
    # services use the creds env var instead of the metadata server, as
    # well as making the cluster multizone
    comp_cloud_config_path = cloud_config_path(component)
    comp_cloud_config_path.write_text(
        "[Global]\n" "token-url = nil\n" "multizone = true\n"
    )

    daemon_env_path = _daemon_env_path(component)
    if daemon_env_path.exists():
        daemon_env = daemon_env_path.read_text()
        if not daemon_env.endswith("\n"):
            daemon_env += "\n"
    else:
        daemon_env = ""
    if gcp_creds_env_key not in daemon_env:
        daemon_env += "{}={}\n".format(gcp_creds_env_key, creds_path)
        daemon_env_path.parent.mkdir(parents=True, exist_ok=True)
        daemon_env_path.write_text(daemon_env)


def generate_openstack_cloud_config():
    # openstack requires additional credentials setup
    openstack = endpoint_from_flag("endpoint.openstack.ready")

    lines = [
        "[Global]",
        "auth-url = {}".format(openstack.auth_url),
        "region = {}".format(openstack.region),
        "username = {}".format(openstack.username),
        "password = {}".format(openstack.password),
        "tenant-name = {}".format(openstack.project_name),
        "domain-name = {}".format(openstack.user_domain_name),
        "tenant-domain-name = {}".format(openstack.project_domain_name),
    ]
    if openstack.endpoint_tls_ca:
        lines.append("ca-file = /etc/config/endpoint-ca.cert")

    lines.extend(
        [
            "",
            "[LoadBalancer]",
        ]
    )

    if openstack.has_octavia in (True, None):
        # Newer integrator charm will detect whether underlying OpenStack has
        # Octavia enabled so we can set this intelligently. If we're still
        # related to an older integrator, though, default to assuming Octavia
        # is available.
        lines.append("use-octavia = true")
    else:
        lines.append("use-octavia = false")
        lines.append("lb-provider = haproxy")
    if openstack.subnet_id:
        lines.append("subnet-id = {}".format(openstack.subnet_id))
    if openstack.floating_network_id:
        lines.append("floating-network-id = {}".format(openstack.floating_network_id))
    if openstack.lb_method:
        lines.append("lb-method = {}".format(openstack.lb_method))
    if openstack.manage_security_groups:
        lines.append(
            "manage-security-groups = {}".format(openstack.manage_security_groups)
        )
    if any(
        [openstack.bs_version, openstack.trust_device_path, openstack.ignore_volume_az]
    ):
        lines.append("")
        lines.append("[BlockStorage]")
    if openstack.bs_version is not None:
        lines.append("bs-version = {}".format(openstack.bs_version))
    if openstack.trust_device_path is not None:
        lines.append("trust-device-path = {}".format(openstack.trust_device_path))
    if openstack.ignore_volume_az is not None:
        lines.append("ignore-volume-az = {}".format(openstack.ignore_volume_az))
    return "\n".join(lines) + "\n"


def write_azure_snap_config(component):
    azure = endpoint_from_flag("endpoint.azure.ready")
    comp_cloud_config_path = cloud_config_path(component)
    comp_cloud_config_path.write_text(
        json.dumps(
            {
                "useInstanceMetadata": True,
                "useManagedIdentityExtension": azure.managed_identity,
                "subscriptionId": azure.subscription_id,
                "resourceGroup": azure.resource_group,
                "location": azure.resource_group_location,
                "vnetName": azure.vnet_name,
                "vnetResourceGroup": azure.vnet_resource_group,
                "subnetName": azure.subnet_name,
                "securityGroupName": azure.security_group_name,
                "loadBalancerSku": "standard",
                "securityGroupResourceGroup": azure.security_group_resource_group,
                "aadClientId": azure.aad_client_id,
                "aadClientSecret": azure.aad_client_secret,
                "tenantId": azure.tenant_id,
            }
        )
    )


def configure_kube_proxy(
    configure_prefix, api_servers, cluster_cidr, bind_address=None
):
    kube_proxy_opts = {}
    kube_proxy_opts["cluster-cidr"] = cluster_cidr
    kube_proxy_opts["kubeconfig"] = kubeproxyconfig_path
    kube_proxy_opts["logtostderr"] = "true"
    kube_proxy_opts["v"] = "0"
    num_apis = len(api_servers)
    kube_proxy_opts["master"] = api_servers[get_unit_number() % num_apis]
    kube_proxy_opts["hostname-override"] = get_node_name()
    if bind_address:
        kube_proxy_opts["bind-address"] = bind_address
    elif is_ipv6(cluster_cidr):
        kube_proxy_opts["bind-address"] = "::"

    if host.is_container():
        kube_proxy_opts["conntrack-max-per-core"] = "0"

    feature_gates = []

    if is_dual_stack(cluster_cidr):
        feature_gates.append("IPv6DualStack=true")

    if is_state("endpoint.aws.ready"):
        feature_gates.append("CSIMigrationAWS=false")
    elif is_state("endpoint.gcp.ready"):
        feature_gates.append("CSIMigrationGCE=false")
    elif is_state("endpoint.azure.ready"):
        feature_gates.append("CSIMigrationAzureDisk=false")

    kube_proxy_opts["feature-gates"] = ",".join(feature_gates)

    configure_kubernetes_service(
        configure_prefix, "kube-proxy", kube_proxy_opts, "proxy-extra-args"
    )


def get_unit_number():
    return int(hookenv.local_unit().split("/")[1])


def cluster_cidr():
    """Return the cluster CIDR provided by the CNI"""
    cni = endpoint_from_flag("cni.available")
    if not cni:
        return None
    config = hookenv.config()
    if "default-cni" in config:
        # master
        default_cni = config["default-cni"]
    else:
        # worker
        kube_control = endpoint_from_flag("kube-control.dns.available")
        if not kube_control:
            return None
        default_cni = kube_control.get_default_cni()
    return cni.get_config(default=default_cni)["cidr"]


def is_dual_stack(cidrs):
    """Detect IPv4/IPv6 dual stack from CIDRs"""
    return {net.version for net in get_networks(cidrs)} == {4, 6}


def is_ipv4(cidrs):
    """Detect IPv6 from CIDRs"""
    return get_ipv4_network(cidrs) is not None


def is_ipv6(cidrs):
    """Detect IPv6 from CIDRs"""
    return get_ipv6_network(cidrs) is not None


def is_ipv6_preferred(cidrs):
    """Detect if IPv6 is preffered from CIDRs"""
    return get_networks(cidrs)[0].version == 6


def get_networks(cidrs):
    """Convert a comma-separated list of CIDRs to a list of networks."""
    if not cidrs:
        return []
    return [ipaddress.ip_interface(cidr).network for cidr in cidrs.split(",")]


def get_ipv4_network(cidrs):
    """Get the IPv4 network from the given CIDRs or None"""
    return {net.version: net for net in get_networks(cidrs)}.get(4)


def get_ipv6_network(cidrs):
    """Get the IPv6 network from the given CIDRs or None"""
    return {net.version: net for net in get_networks(cidrs)}.get(6)


def enable_ipv6_forwarding():
    """Enable net.ipv6.conf.all.forwarding in sysctl if it is not already."""
    check_call(["sysctl", "net.ipv6.conf.all.forwarding=1"])


def get_bind_addrs(ipv4=True, ipv6=True):
    """Get all global-scoped addresses that we might bind to."""
    try:
        output = check_output(["ip", "-br", "addr", "show", "scope", "global"])
    except CalledProcessError:
        # stderr will have any details, and go to the log
        hookenv.log("Unable to determine global addresses", hookenv.ERROR)
        return []

    ignore_interfaces = ("lxdbr", "flannel", "cni", "virbr", "docker")
    accept_versions = set()
    if ipv4:
        accept_versions.add(4)
    if ipv6:
        accept_versions.add(6)

    addrs = []
    for line in output.decode("utf8").splitlines():
        intf, state, *intf_addrs = line.split()
        if state != "UP" or any(
            intf.startswith(prefix) for prefix in ignore_interfaces
        ):
            continue
        for addr in intf_addrs:
            ip_addr = ipaddress.ip_interface(addr).ip
            if ip_addr.version in accept_versions:
                addrs.append(str(ip_addr))
    return addrs


class InvalidVMwareHost(Exception):
    pass


def _get_vmware_uuid():
    serial_id_file = "/sys/class/dmi/id/product_serial"
    # The serial id from VMWare VMs comes in following format:
    # VMware-42 28 13 f5 d4 20 71 61-5d b0 7b 96 44 0c cf 54
    try:
        with open(serial_id_file, "r") as f:
            serial_string = f.read().strip()
            if "VMware-" not in serial_string:
                hookenv.log(
                    "Unable to find VMware ID in "
                    "product_serial: {}".format(serial_string)
                )
                raise InvalidVMwareHost
            serial_string = (
                serial_string.split("VMware-")[1].replace(" ", "").replace("-", "")
            )
            uuid = "%s-%s-%s-%s-%s" % (
                serial_string[0:8],
                serial_string[8:12],
                serial_string[12:16],
                serial_string[16:20],
                serial_string[20:32],
            )
    except IOError as err:
        hookenv.log("Unable to read UUID from sysfs: {}".format(err))
        uuid = "UNKNOWN"

    return uuid


def token_generator(length=32):
    """Generate a random token for use in account tokens.

    param: length - the length of the token to generate
    """
    alpha = string.ascii_letters + string.digits
    token = "".join(random.SystemRandom().choice(alpha) for _ in range(length))
    return token


def get_secret_names():
    """Return a dict of 'username: secret_id' for Charmed Kubernetes users."""
    try:
        output = kubectl(
            "get",
            "secrets",
            "-n",
            AUTH_SECRET_NS,
            "--field-selector",
            "type={}".format(AUTH_SECRET_TYPE),
            "-o",
            "json",
        ).decode("UTF-8")
    except (CalledProcessError, FileNotFoundError):
        # The api server may not be up, or we may be trying to run kubelet before
        # the snap is installed. Send back an empty dict.
        hookenv.log("Unable to get existing secrets", level=hookenv.WARNING)
        return {}

    secrets = json.loads(output)
    secret_names = {}
    if "items" in secrets:
        for secret in secrets["items"]:
            try:
                secret_id = secret["metadata"]["name"]
                username_b64 = secret["data"]["username"].encode("UTF-8")
            except (KeyError, TypeError):
                # CK secrets will have populated 'data', but not all secrets do
                continue
            secret_names[b64decode(username_b64).decode("UTF-8")] = secret_id
    return secret_names


def generate_rfc1123(length=10):
    """Generate a random string compliant with RFC 1123.

    https://kubernetes.io/docs/concepts/overview/working-with-objects/names/#dns-subdomain-names

    param: length - the length of the string to generate
    """
    length = 253 if length > 253 else length
    valid_chars = string.ascii_lowercase + string.digits
    rand_str = "".join(random.SystemRandom().choice(valid_chars) for _ in range(length))
    return rand_str


def create_secret(token, username, user, groups=None):
    secrets = get_secret_names()
    if username in secrets:
        # Use existing secret ID if one exists for our username
        secret_id = secrets[username]
    else:
        # secret IDs must be unique and rfc1123 compliant
        sani_name = re.sub("[^0-9a-z.-]+", "-", user.lower())
        secret_id = "auth-{}-{}".format(sani_name, generate_rfc1123(10))

    # The authenticator expects tokens to be in the form user::token
    token_delim = "::"
    if token_delim not in token:
        token = "{}::{}".format(user, token)

    context = {
        "type": AUTH_SECRET_TYPE,
        "secret_name": secret_id,
        "secret_namespace": AUTH_SECRET_NS,
        "user": b64encode(user.encode("UTF-8")).decode("utf-8"),
        "username": b64encode(username.encode("UTF-8")).decode("utf-8"),
        "password": b64encode(token.encode("UTF-8")).decode("utf-8"),
        "groups": b64encode(groups.encode("UTF-8")).decode("utf-8") if groups else "",
    }
    with tempfile.NamedTemporaryFile() as tmp_manifest:
        render("cdk.auth-webhook-secret.yaml", tmp_manifest.name, context=context)

        if kubectl_manifest("apply", tmp_manifest.name):
            hookenv.log("Created secret for {}".format(username))
            return True
        else:
            hookenv.log("WARN: Unable to create secret for {}".format(username))
            return False


def get_secret_password(username):
    """Get the password for the given user from the secret that CK created."""
    try:
        output = kubectl(
            "get",
            "secrets",
            "-n",
            AUTH_SECRET_NS,
            "--field-selector",
            "type={}".format(AUTH_SECRET_TYPE),
            "-o",
            "json",
        ).decode("UTF-8")
    except CalledProcessError:
        # NB: apiserver probably isn't up. This can happen on boostrap or upgrade
        # while trying to build kubeconfig files. If we need the 'admin' token during
        # this time, pull it directly out of the kubeconfig file if possible.
        token = None
        if username == "admin":
            admin_kubeconfig = Path("/root/.kube/config")
            if admin_kubeconfig.exists():
                data = yaml.safe_load(admin_kubeconfig.read_text())
                try:
                    token = data["users"][0]["user"]["token"]
                except (KeyError, IndexError, TypeError):
                    pass
        return token
    except FileNotFoundError:
        # New deployments may ask for a token before the kubectl snap is installed.
        # Give them nothing!
        return None

    secrets = json.loads(output)
    if "items" in secrets:
        for secret in secrets["items"]:
            try:
                data_b64 = secret["data"]
                password_b64 = data_b64["password"].encode("UTF-8")
                username_b64 = data_b64["username"].encode("UTF-8")
            except (KeyError, TypeError):
                # CK authn secrets will have populated 'data', but not all secrets do
                continue

            password = b64decode(password_b64).decode("UTF-8")
            secret_user = b64decode(username_b64).decode("UTF-8")
            if username == secret_user:
                return password
    return None
