# Copyright 2016 Canonical Ltd
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

import hashlib
import re
import subprocess
import socket
import tempfile
import time
import xml.etree.ElementTree as etree

from distutils.version import StrictVersion
from io import StringIO
from charmhelpers.core import unitdata
from charmhelpers.core.hookenv import (
    log,
    INFO,
    DEBUG,
    WARNING,
)


class ServicesNotUp(Exception):
    pass


class PropertyNotFound(Exception):
    pass


def wait_for_pcmk(retries=12, sleep=10):
    """Wait for pacemaker/corosync to fully come up.

    :param retries: Number of times to check for crm's output before raising.
    :type retries: int
    :param sleep: Number of seconds to sleep between retries.
    :type sleep: int
    :raises: ServicesNotUp
    """
    expected_hostname = socket.gethostname()
    last_exit_code = None
    last_output = None
    for i in range(retries):
        if i > 0:
            time.sleep(sleep)
        last_exit_code, last_output = subprocess.getstatusoutput(
            'crm node list')
        if expected_hostname in last_output:
            return

    msg = ('Pacemaker or Corosync are still not fully up after waiting for '
           '{} retries. '.format(retries))
    if last_exit_code != 0:
        msg += 'Last exit code: {}. '.format(last_exit_code)
    if 'not supported between' in last_output:
        # NOTE(lourot): transient crmsh bug
        # https://github.com/ClusterLabs/crmsh/issues/764
        msg += 'This looks like ClusterLabs/crmsh#764. '
    elif 'node1' in last_output:
        # NOTE(lourot): transient bug on deployment. The charm will recover
        # later but the corosync ring will still show an offline 'node1' node.
        # The corosync ring can then be cleaned up by running the 'update-ring'
        # action.
        msg += 'This looks like lp:1874719. '
    msg += 'Last output: {}'.format(last_output)
    raise ServicesNotUp(msg)


def commit(cmd, failure_is_fatal=False):
    """Run the given command.

    :param cmd: Command to run
    :type cmd: str
    :param failure_is_fatal: Whether to raise exception if command fails.
    :type failure_is_fatal: bool
    :raises: subprocess.CalledProcessError
    """
    if failure_is_fatal:
        return subprocess.check_output(cmd.split(), stderr=subprocess.STDOUT)
    else:
        return subprocess.call(cmd.split())


def is_resource_present(resource):
    status = subprocess.getstatusoutput("crm resource status %s" % resource)[0]
    if status != 0:
        return False

    return True


def parse_version(cmd_output):
    """Parse version from cmd output.

    :params cmd_output: output from command line
    :type cmd_output: str
    :returns: parsed version
    :rtype: distutils.version.StrictVersion
    :raises: ValueError version could not be parsed
    """
    r = re.compile(r".*(\d+\.\d+\.\d+).*")
    matched = r.match(cmd_output)
    if not matched:
        raise ValueError("error parsing version: {}".format(cmd_output))
    else:
        return StrictVersion(matched.group(1))


def crm_opt_exists(opt_name):
    output = subprocess.getstatusoutput("crm configure show")[1]
    if opt_name in output:
        return True

    return False


def crm_maas_stonith_resource_list():
    """Returns list of resources of the type stonith:external/maas.

    :returns: List of resource names.
    :rtype: [str,]
    """
    resource_names = []
    output = subprocess.check_output(['crm_resource', '-L']).decode()
    for line in output.split('\n'):
        if 'stonith:external/maas' in line:
            resource_names.append(line.split()[0])
    return [n for n in resource_names if n.startswith('st-maas-')]


def crm_res_running(opt_name):
    (_, output) = subprocess.getstatusoutput(
        "crm resource status %s" % opt_name)
    if output.startswith("resource %s is running" % opt_name):
        return True

    log('CRM Resource not running - Status: {}'.format(output), WARNING)
    return False


def crm_res_running_on_node(resource, node):
    """Determine if the resource is running on the given node.

    If the resource is active/passive check if it is running on any node.
    If the resources is active/active check it is running on the given node.

    :param resource: str name of resource
    :param node: str name of node
    :returns: boolean
    """

    (_, output) = subprocess.getstatusoutput(
        "crm resource status {}".format(resource))
    lines = output.split("\n")

    if len(lines) > 1:
        # Multi line is a clone list like haproxy and should run on all nodes
        # check if it is running on this node
        for line in lines:
            if node in line:
                if line.startswith("resource {} is running".format(resource)):
                    return True
    else:
        # Single line is for active/passive like a VIP, may not be on this node
        # but check it is running somewhere
        if output.startswith("resource {} is running".format(resource)):
            return True

    log('CRM Resource not running - Status: {}'.format(output), WARNING)
    return False


def list_nodes():
    """List member nodes."""
    cmd = ['crm', 'node', 'status']
    out = subprocess.check_output(cmd).decode('utf-8')
    tree = etree.fromstring(out)
    nodes = [n.attrib['uname'] for n in tree.iter('node')]
    return sorted(nodes)


def set_node_status_to_maintenance(node_name):
    """See https://crmsh.github.io/man-2.0/#cmdhelp_node_maintenance

    :param node_name: Name of the node to set to maintenance.
    :type node_name: str
    :raises: subprocess.CalledProcessError
    """
    log('Setting node {} to maintenance'.format(node_name))
    commit('crm -w -F node maintenance {}'.format(node_name),
           failure_is_fatal=True)


def delete_node(node_name, failure_is_fatal=True):
    """See https://crmsh.github.io/man-2.0/#cmdhelp_node_delete

    :param node_name: Name of the node to be removed from the cluster.
    :type node_name: str
    :param failure_is_fatal: Whether to raise exception if command fails.
    :type failure_is_fatal: bool
    :raises: subprocess.CalledProcessError
    """
    log('Deleting node {} from the cluster'.format(node_name))
    cmd = 'crm -w -F node delete {}'.format(node_name)
    for attempt in [2, 1, 0]:
        try:
            commit(cmd, failure_is_fatal=failure_is_fatal)
        except subprocess.CalledProcessError as e:
            output = e.output.decode('utf-8').strip()
            log('"{}" failed with "{}"'.format(cmd, output), WARNING)
            if output == 'ERROR: node {} not found in the CIB'.format(
                    node_name):
                # NOTE(lourot): Sometimes seen when called from the
                # `update-ring` action.
                log('{} was already removed from the cluster, moving on',
                    WARNING)
                return
            if '/cmdline' in output:
                # NOTE(lourot): older versions of crmsh may fail with
                # https://github.com/ClusterLabs/crmsh/issues/283 . If that's
                # the case let's retry.
                log('This looks like ClusterLabs/crmsh#283.', WARNING)
                if attempt > 0:
                    log('Retrying...', WARNING)
                    continue
            if 'Transport endpoint is not connected' in output:
                # NOTE(lourot): happens more often with corosync >= 3.1.0
                # (hirsute), see lp:1931588
                log('Transport endpoint not connected.', WARNING)
                if attempt > 0:
                    log('Retrying...', WARNING)
                    continue
            raise


def get_property_from_xml(name, output):
    """Read a configuration property from the XML generated by 'crm configure show
    xml'

    :param name: property's name
    :param output: string with the output of `crm configure show xml`
    :returns: value of the property
    :rtype: str
    :raises: pcmk.PropertyNotFound
    """

    tree = etree.parse(StringIO(output))
    root = tree.getroot()
    crm_config = root.find('configuration').find('crm_config')
    props = crm_config.find('cluster_property_set')
    for element in props:
        if element.attrib['name'] == name:
            # property found!
            return element.attrib['value']

    raise PropertyNotFound(name)


def get_property(name):
    """Retrieve a cluster's property

    :param name: property name
    :returns: property value
    :rtype: str
    """
    # crmsh >= 2.3 renamed show-property to get-property, 2.3.x is
    # available since zesty
    if crm_version() >= StrictVersion('2.3.0'):
        output = subprocess.check_output(
            ['crm', 'configure', 'get-property', name],
            universal_newlines=True)
    elif crm_version() < StrictVersion('2.2.0'):
        # before 2.2.0 there is no method to get a property
        output = subprocess.check_output(['crm', 'configure', 'show', 'xml'],
                                         universal_newlines=True)

        return get_property_from_xml(name, output)
    else:
        output = subprocess .check_output(
            ['crm', 'configure', 'show-property', name],
            universal_newlines=True)

    return output


def set_property(name, value):
    """Set a cluster's property

    :param name: property name
    :param value: new value
    """
    subprocess.check_call(['crm', 'configure',
                           'property', '%s=%s' % (name, value)],
                          universal_newlines=True)


def crm_version():
    """Get `crm` version.

    Parses the output of `crm --version`.

    :returns: crm version
    :rtype: distutils.version.StrictVersion
    :raises: ValueError version could not be parsed
    :raises: subprocess.CalledProcessError if the check_output fails
    """
    ver = subprocess.check_output(["crm", "--version"],
                                  universal_newlines=True)
    return parse_version(ver)


def _crm_update_object(update_template, update_ctxt, hash_keys, unitdata_key,
                       res_params=None, force=False):
    """Update a object using `crm configure load update`

    :param update_template: Format string to create object when update_ctxt is
                            applied.
    :type update_template: str
    :param update_ctxt: Context to apply to update_template to generate object
                        creation directive.
    :type update_ctxt: dict
    :param hash_keys: List of keys to use from update_ctxt when generating
                      objects hash.
    :type hash_keys: List[str]
    :param unitdata_key: Key to use when storing objects hash in in unitdata
                         kv.
    :type unitdata_key: str
    :param res_params: Resource's additional parameters
                       (e.g. "params ip=10.5.250.250")
    :type res_params: str or None
    :param force: Whether to force the update irrespective of whats currently
                  configured.
    :type force: bool
    :returns: Return code (0 => success)
    :rtype: int
    """
    db = unitdata.kv()
    res_hash = generate_checksum(update_ctxt[k] for k in hash_keys)
    if not force and db.get(unitdata_key) == res_hash:
        log("Resource {} already defined and parameters haven't changed"
            .format(update_ctxt['object_name']))
        return 0

    with tempfile.NamedTemporaryFile() as f:
        f.write(update_template.format(**update_ctxt).encode('ascii'))

        if res_params:
            f.write(' \\\n\t{}'.format(res_params).encode('ascii'))
        else:
            f.write('\n'.encode('ascii'))

        f.flush()
        f.seek(0)
        log(
            'Updating resource {}'.format(update_ctxt['object_name']),
            level=INFO)
        log('File content:\n{}'.format(f.read()), level=DEBUG)
        cmd = "crm configure load update {}".format(f.name)
        log('Update command: {}'.format(cmd))
        retcode = commit(cmd)
        if retcode == 0:
            level = DEBUG
        else:
            level = WARNING

        log('crm command exit code: {}'.format(retcode), level=level)

        if retcode == 0:
            db.set(unitdata_key, res_hash)
            db.flush()

        return retcode


def crm_update_resource(res_name, res_type, res_params=None, force=False):
    """Update a resource using `crm configure load update`

    :param res_name: resource name
    :type res_name: str
    :param res_type: resource type (e.g. IPaddr2)
    :type res_type: str
    :param res_params: resource's parameters (e.g. "params ip=10.5.250.250")
    :type res_params: str or None
    :param force: Whether to force the update irrespective of whats currently
                  configured.
    :type force: bool
    :returns: Return code (0 => success)
    :rtype: int
    """
    hash_keys = ['resource_type']
    if res_params:
        hash_keys.append('resource_params')
    return _crm_update_object(
        'primitive {object_name} {resource_type}',
        {
            'object_name': res_name,
            'resource_params': res_params,
            'resource_type': res_type},
        hash_keys,
        '{}-{}'.format(res_name, res_type),
        res_params=res_params,
        force=force)


def crm_update_location(location_name, resource_name, score, node,
                        force=False):
    """Update a location rule.

    :param location_name: Name of location rule.
    :type location_name: str
    :param resource_name: Resource name location rule governs.
    :type resource_name: str
    :param score: The score for the resource running on node.
    :type score: int
    :param node: Name of the node this rule applies to.
    :type node: str
    :param force: Whether to force the update irrespective of whats currently
                  configured.
    :type force: bool
    :returns: Return code (0 => success)
    :rtype: int
    """
    return _crm_update_object(
        'location {object_name} {resource_name} {score}: {node}',
        {
            'object_name': location_name,
            'resource_name': resource_name,
            'score': str(score),
            'node': node},
        ['resource_name', 'score', 'node'],
        '{}-{}'.format(location_name, resource_name),
        force=force)


def generate_checksum(check_strings):
    """Create a md5 checksum using each string in the list.

    :param check_strings: resource name
    :type check_strings: List[str]
    :returns: Hash generated from strings.
    :rtype: str
    """
    m = hashlib.md5()
    for entry in check_strings:
        m.update(entry.encode('utf-8'))
    return m.hexdigest()


def resource_checksum(res_name, res_type, res_params=None):
    """Create a md5 checksum of the resource parameters.

    :param res_name: resource name
    :param res_type: resource type (e.g. IPaddr2)
    :param res_params: resource's parameters (e.g. "params ip=10.5.250.250")
    """
    data = [res_type]
    if res_params is not None:
        data.append(res_params)
    return generate_checksum(data)


def get_tag(element, name):
    """Get tag from element.

    :param element: parent element
    :type element: etree.Element
    :param name: name of tag
    :type name: str
    :returns: element with tag name
    :rtype: etree.Element
    """
    tag = element.find(name)
    if tag is None:
        return etree.Element(name)

    return tag


def add_key(dictionary, key, value):
    """Add key to dictionary.

    :param dictionary: dictionary
    :type dictionary: Dict[Union[str, bytes], Union[str, bytes]]
    :param key: new key to be inserted
    :type key: str
    :param value: new value to be inserted
    :type value: Any
    :returns: updated dictionary
    :rtype: Dict[Union[str, bytes], Any]
    """
    if key in dictionary:
        log('key already exists and will be rewrite: {}'.format(key), WARNING)

    dictionary[key] = value
    return dictionary


def crm_mon_version():
    """Get `crm_mon` version.

    Parses the output of `crm_mon --version`.

    :returns: crm_mon version
    :rtype: distutils.version.StrictVersion
    :raises: ValueError version could not be parsed
    :raises: subprocess.CalledProcessError if the check_output fails
    """
    ver = subprocess.check_output(["crm_mon", "--version"],
                                  universal_newlines=True)
    return parse_version(ver)


def cluster_status(resources=True, history=False):
    """Parse the cluster status from `crm_mon`.

    The `crm_mon` provides a summary of cluster's current state in XML format.

    :param resources: flag for parsing resources from status, default is True
    :type: boolean
    :param history: flag for parsing history from status, default is False
    :type: boolean
    :returns: converted cluster status to the Dict
    :rtype: Dict[str, Any]]
    """
    status = {}
    crm_mon_ver = crm_mon_version()

    if crm_mon_ver >= StrictVersion("2.0.0"):
        cmd = ["crm_mon", "--output-as=xml", "--inactive"]
    else:
        # NOTE (rgildein): The `--as-xml` option is deprecated.
        cmd = ["crm_mon", "--as-xml", "--inactive"]

    xml = subprocess.check_output(cmd).decode('utf-8')
    root = etree.fromstring(xml)

    # version
    status["crm_mon_version"] = str(crm_mon_ver)

    # summary
    summary = get_tag(root, "summary")
    status["summary"] = {element.tag: element.attrib for element in summary}

    # nodes
    nodes = get_tag(root, "nodes")
    status["nodes"] = {
        node.get("name"): node.attrib for node in nodes.findall("node")
    }

    # resources
    if resources:
        cluster_resources = get_tag(root, "resources")
        resources_groups = {
            group.get("id"): [
                add_key(resource.attrib, "nodes",
                        [node.attrib for node in resource.findall("node")])
                for resource in group.findall("resource")
            ] for group in cluster_resources.findall("group")
        }
        resources_clones = {
            clone.get("id"): add_key(clone.attrib, "resources", [
                add_key(resource.attrib, "nodes",
                        [node.attrib for node in resource.findall("node")])
                for resource in clone.findall("resource")
            ]) for clone in cluster_resources.findall("clone")
        }
        status["resources"] = {"groups": resources_groups,
                               "clones": resources_clones}

    # history
    if history:
        node_history = get_tag(root, "node_history")
        status["history"] = {
            node.get("name"): {
                resource.get("id"): [
                    operation.attrib
                    for operation in resource.findall("operation_history")
                ] for resource in node.findall("resource_history")
            } for node in node_history.findall("node")
        }

    return status
