# Copyright 2019-2021 Canonical Ltd
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

import collections
import contextlib
import os
import six
import shutil
import yaml
import zipfile

import charmhelpers
import charmhelpers.core.hookenv as hookenv
import charmhelpers.core.host as ch_host

# Features provided by this module:

"""
Policy.d helper functions
=========================

The functions in this module are designed, as a set, to provide an easy-to-use
set of hooks for classic charms to add in /etc/<service-name>/policy.d/
directory override YAML files.

(For charms.openstack charms, a mixin class is provided for this
functionality).

In order to "hook" this functionality into a (classic) charm, two functions are
provided:

    maybe_do_policyd_overrides(openstack_release,
                               service,
                               blacklist_paths=none,
                               blacklist_keys=none,
                               template_function=none,
                               restart_handler=none)

    maybe_do_policyd_overrides_on_config_changed(openstack_release,
                                                 service,
                                                 blacklist_paths=None,
                                                 blacklist_keys=None,
                                                 template_function=None,
                                                 restart_handler=None

(See the docstrings for details on the parameters)

The functions should be called from the install and upgrade hooks in the charm.
The `maybe_do_policyd_overrides_on_config_changed` function is designed to be
called on the config-changed hook, in that it does an additional check to
ensure that an already overridden policy.d in an upgrade or install hooks isn't
repeated.

In order the *enable* this functionality, the charm's install, config_changed,
and upgrade_charm hooks need to be modified, and a new config option (see
below) needs to be added.  The README for the charm should also be updated.

Examples from the keystone charm are:

@hooks.hook('install.real')
@harden()
def install():
    ...
    # call the policy overrides handler which will install any policy overrides
    maybe_do_policyd_overrides(os_release('keystone'), 'keystone')


@hooks.hook('config-changed')
@restart_on_change(restart_map(), restart_functions=restart_function_map())
@harden()
def config_changed():
    ...
    # call the policy overrides handler which will install any policy overrides
    maybe_do_policyd_overrides_on_config_changed(os_release('keystone'),
                                                 'keystone')

@hooks.hook('upgrade-charm')
@restart_on_change(restart_map(), stopstart=True)
@harden()
def upgrade_charm():
    ...
    # call the policy overrides handler which will install any policy overrides
    maybe_do_policyd_overrides(os_release('keystone'), 'keystone')

Status Line
===========

The workload status code in charm-helpers has been modified to detect if
policy.d override code has been incorporated into the charm by checking for the
new config variable (in the config.yaml).  If it has been, then the workload
status line will automatically show "PO:" at the beginning of the workload
status for that unit/service if the config option is set.  If the policy
override is broken, the "PO (broken):" will be shown.  No changes to the charm
(apart from those already mentioned) are needed to enable this functionality.
(charms.openstack charms also get this functionality, but please see that
library for further details).
"""

# The config.yaml for the charm should contain the following for the config
# option:

"""
  use-policyd-override:
    type: boolean
    default: False
    description: |
      If True then use the resource file named 'policyd-override' to install
      override YAML files in the service's policy.d directory.  The resource
      file should be a ZIP file containing at least one yaml file with a .yaml
      or .yml extension.  If False then remove the overrides.
"""

# The metadata.yaml for the charm should contain the following:
"""
resources:
  policyd-override:
    type: file
    filename: policyd-override.zip
    description: The policy.d overrides file
"""

# The README for the charm should contain the following:
"""
Policy Overrides
----------------

This feature allows for policy overrides using the `policy.d` directory.  This
is an **advanced** feature and the policies that the OpenStack service supports
should be clearly and unambiguously understood before trying to override, or
add to, the default policies that the service uses.  The charm also has some
policy defaults.  They should also be understood before being overridden.

> **Caution**: It is possible to break the system (for tenants and other
  services) if policies are incorrectly applied to the service.

Policy overrides are YAML files that contain rules that will add to, or
override, existing policy rules in the service.  The `policy.d` directory is
a place to put the YAML override files.  This charm owns the
`/etc/keystone/policy.d` directory, and as such, any manual changes to it will
be overwritten on charm upgrades.

Overrides are provided to the charm using a Juju resource called
`policyd-override`.  The resource is a ZIP file.  This file, say
`overrides.zip`, is attached to the charm by:


    juju attach-resource <charm-name> policyd-override=overrides.zip

The policy override is enabled in the charm using:

    juju config <charm-name> use-policyd-override=true

When `use-policyd-override` is `True` the status line of the charm will be
prefixed with `PO:` indicating that policies have been overridden.  If the
installation of the policy override YAML files failed for any reason then the
status line will be prefixed with `PO (broken):`.  The log file for the charm
will indicate the reason.  No policy override files are installed if the `PO
(broken):` is shown.  The status line indicates that the overrides are broken,
not that the policy for the service has failed. The policy will be the defaults
for the charm and service.

Policy overrides on one service may affect the functionality of another
service. Therefore, it may be necessary to provide policy overrides for
multiple service charms to achieve a consistent set of policies across the
OpenStack system.  The charms for the other services that may need overrides
should be checked to ensure that they support overrides before proceeding.
"""

POLICYD_VALID_EXTS = ['.yaml', '.yml', '.j2', '.tmpl', '.tpl']
POLICYD_TEMPLATE_EXTS = ['.j2', '.tmpl', '.tpl']
POLICYD_RESOURCE_NAME = "policyd-override"
POLICYD_CONFIG_NAME = "use-policyd-override"
POLICYD_SUCCESS_FILENAME = "policyd-override-success"
POLICYD_LOG_LEVEL_DEFAULT = hookenv.INFO
POLICYD_ALWAYS_BLACKLISTED_KEYS = ("admin_required", "cloud_admin")


class BadPolicyZipFile(Exception):

    def __init__(self, log_message):
        self.log_message = log_message

    def __str__(self):
        return self.log_message


class BadPolicyYamlFile(Exception):

    def __init__(self, log_message):
        self.log_message = log_message

    def __str__(self):
        return self.log_message


if six.PY2:
    BadZipFile = zipfile.BadZipfile
else:
    BadZipFile = zipfile.BadZipFile


def is_policyd_override_valid_on_this_release(openstack_release):
    """Check that the charm is running on at least Ubuntu Xenial, and at
    least the queens release.

    :param openstack_release: the release codename that is installed.
    :type openstack_release: str
    :returns: True if okay
    :rtype: bool
    """
    # NOTE(ajkavanagh) circular import!  This is because the status message
    # generation code in utils has to call into this module, but this function
    # needs the CompareOpenStackReleases() function.  The only way to solve
    # this is either to put ALL of this module into utils, or refactor one or
    # other of the CompareOpenStackReleases or status message generation code
    # into a 3rd module.
    import charmhelpers.contrib.openstack.utils as ch_utils
    return ch_utils.CompareOpenStackReleases(openstack_release) >= 'queens'


def maybe_do_policyd_overrides(openstack_release,
                               service,
                               blacklist_paths=None,
                               blacklist_keys=None,
                               template_function=None,
                               restart_handler=None,
                               user=None,
                               group=None,
                               config_changed=False):
    """If the config option is set, get the resource file and process it to
    enable the policy.d overrides for the service passed.

    The param `openstack_release` is required as the policyd overrides feature
    is only supported on openstack_release "queens" or later, and on ubuntu
    "xenial" or later.  Prior to these versions, this feature is a NOP.

    The optional template_function is a function that accepts a string and has
    an opportunity to modify the loaded file prior to it being read by
    yaml.safe_load().  This allows the charm to perform "templating" using
    charm derived data.

    The param blacklist_paths are paths (that are in the service's policy.d
    directory that should not be touched).

    The param blacklist_keys are keys that must not appear in the yaml file.
    If they do, then the whole policy.d file fails.

    The yaml file extracted from the resource_file (which is a zipped file) has
    its file path reconstructed.  This, also, must not match any path in the
    black list.

    The param restart_handler is an optional Callable that is called to perform
    the service restart if the policy.d file is changed.  This should normally
    be None as oslo.policy automatically picks up changes in the policy.d
    directory.  However, for any services where this is buggy then a
    restart_handler can be used to force the policy.d files to be read.

    If the config_changed param is True, then the handling is slightly
    different: It will only perform the policyd overrides if the config is True
    and the success file doesn't exist.  Otherwise, it does nothing as the
    resource file has already been processed.

    :param openstack_release: The openstack release that is installed.
    :type openstack_release: str
    :param service: the service name to construct the policy.d directory for.
    :type service: str
    :param blacklist_paths: optional list of paths to leave alone
    :type blacklist_paths: Union[None, List[str]]
    :param blacklist_keys: optional list of keys that mustn't appear in the
                           yaml file's
    :type blacklist_keys: Union[None, List[str]]
    :param template_function: Optional function that can modify the string
                              prior to being processed as a Yaml document.
    :type template_function: Union[None, Callable[[str], str]]
    :param restart_handler: The function to call if the service should be
                            restarted.
    :type restart_handler: Union[None, Callable[]]
    :param user: The user to create/write files/directories as
    :type user: Union[None, str]
    :param group: the group to create/write files/directories as
    :type group: Union[None, str]
    :param config_changed: Set to True for config_changed hook.
    :type config_changed: bool
    """
    _user = service if user is None else user
    _group = service if group is None else group
    if not is_policyd_override_valid_on_this_release(openstack_release):
        return
    hookenv.log("Running maybe_do_policyd_overrides",
                level=POLICYD_LOG_LEVEL_DEFAULT)
    config = hookenv.config()
    try:
        if not config.get(POLICYD_CONFIG_NAME, False):
            clean_policyd_dir_for(service,
                                  blacklist_paths,
                                  user=_user,
                                  group=_group)
            if (os.path.isfile(_policy_success_file()) and
                    restart_handler is not None and
                    callable(restart_handler)):
                restart_handler()
            remove_policy_success_file()
            return
    except Exception as e:
        hookenv.log("... ERROR: Exception is: {}".format(str(e)),
                    level=POLICYD_CONFIG_NAME)
        import traceback
        hookenv.log(traceback.format_exc(), level=POLICYD_LOG_LEVEL_DEFAULT)
        return
    # if the policyd overrides have been performed when doing config_changed
    # just return
    if config_changed and is_policy_success_file_set():
        hookenv.log("... already setup, so skipping.",
                    level=POLICYD_LOG_LEVEL_DEFAULT)
        return
    # from now on it should succeed; if it doesn't then status line will show
    # broken.
    resource_filename = get_policy_resource_filename()
    restart = process_policy_resource_file(
        resource_filename, service, blacklist_paths, blacklist_keys,
        template_function)
    if restart and restart_handler is not None and callable(restart_handler):
        restart_handler()


@charmhelpers.deprecate("Use maybe_do_policyd_overrides instead")
def maybe_do_policyd_overrides_on_config_changed(*args, **kwargs):
    """This function is designed to be called from the config changed hook.

    DEPRECATED: please use maybe_do_policyd_overrides() with the param
    `config_changed` as `True`.

    See maybe_do_policyd_overrides() for more details on the params.
    """
    if 'config_changed' not in kwargs.keys():
        kwargs['config_changed'] = True
    return maybe_do_policyd_overrides(*args, **kwargs)


def get_policy_resource_filename():
    """Function to extract the policy resource filename

    :returns: The filename of the resource, if set, otherwise, if an error
               occurs, then None is returned.
    :rtype: Union[str, None]
    """
    try:
        return hookenv.resource_get(POLICYD_RESOURCE_NAME)
    except Exception:
        return None


@contextlib.contextmanager
def open_and_filter_yaml_files(filepath, has_subdirs=False):
    """Validate that the filepath provided is a zip file and contains at least
    one (.yaml|.yml) file, and that the files are not duplicated when the zip
    file is flattened.  Note that the yaml files are not checked.  This is the
    first stage in validating the policy zipfile; individual yaml files are not
    checked for validity or black listed keys.

    If the has_subdirs param is True, then the files are flattened to the first
    directory, and the files in the root are ignored.

    An example of use is:

        with open_and_filter_yaml_files(some_path) as zfp, g:
            for zipinfo in g:
                # do something with zipinfo ...

    :param filepath: a filepath object that can be opened by zipfile
    :type filepath: Union[AnyStr, os.PathLike[AntStr]]
    :param has_subdirs: Keep first level of subdirectories in yaml file.
    :type has_subdirs: bool
    :returns: (zfp handle,
               a generator of the (name, filename, ZipInfo object) tuples) as a
               tuple.
    :rtype: ContextManager[(zipfile.ZipFile,
                            Generator[(name, str, str, zipfile.ZipInfo)])]
    :raises: zipfile.BadZipFile
    :raises: BadPolicyZipFile if duplicated yaml or missing
    :raises: IOError if the filepath is not found
    """
    with zipfile.ZipFile(filepath, 'r') as zfp:
        # first pass through; check for duplicates and at least one yaml file.
        names = collections.defaultdict(int)
        yamlfiles = _yamlfiles(zfp, has_subdirs)
        for name, _, _, _ in yamlfiles:
            names[name] += 1
        # There must be at least 1 yaml file.
        if len(names.keys()) == 0:
            raise BadPolicyZipFile("contains no yaml files with {} extensions."
                                   .format(", ".join(POLICYD_VALID_EXTS)))
        # There must be no duplicates
        duplicates = [n for n, c in names.items() if c > 1]
        if duplicates:
            raise BadPolicyZipFile("{} have duplicates in the zip file."
                                   .format(", ".join(duplicates)))
        # Finally, let's yield the generator
        yield (zfp, yamlfiles)


def _yamlfiles(zipfile, has_subdirs=False):
    """Helper to get a yaml file (according to POLICYD_VALID_EXTS extensions)
    and the infolist item from a zipfile.

    If the `has_subdirs` param is True, the the only yaml files that have a
    directory component are read, and then first part of the directory
    component is kept, along with the filename in the name.  e.g. an entry with
    a filename of:

        compute/someotherdir/override.yaml

    is returned as:

        compute/override, yaml, override.yaml, <ZipInfo object>

    This is to help with the special, additional, processing that the dashboard
    charm requires.

    :param zipfile: the zipfile to read zipinfo items from
    :type zipfile: zipfile.ZipFile
    :param has_subdirs: Keep first level of subdirectories in yaml file.
    :type has_subdirs: bool
    :returns: generator of (name, ext, filename, info item) for each
              self-identified yaml file.
    :rtype: List[(str, str, str, zipfile.ZipInfo)]
    """
    files = []
    for infolist_item in zipfile.infolist():
        try:
            if infolist_item.is_dir():
                continue
        except AttributeError:
            # fallback to "old" way to determine dir entry for pre-py36
            if infolist_item.filename.endswith('/'):
                continue
        _dir, name_ext = os.path.split(infolist_item.filename)
        name, ext = os.path.splitext(name_ext)
        if has_subdirs and _dir != "":
            name = os.path.join(_dir.split(os.path.sep)[0], name)
        ext = ext.lower()
        if ext and ext in POLICYD_VALID_EXTS:
            files.append((name, ext, name_ext, infolist_item))
    return files


def read_and_validate_yaml(stream_or_doc, blacklist_keys=None):
    """Read, validate and return the (first) yaml document from the stream.

    The doc is read, and checked for a yaml file.  The the top-level keys are
    checked against the blacklist_keys provided.  If there are problems then an
    Exception is raised.  Otherwise the yaml document is returned as a Python
    object that can be dumped back as a yaml file on the system.

    The yaml file must only consist of a str:str mapping, and if not then the
    yaml file is rejected.

    :param stream_or_doc: the file object to read the yaml from
    :type stream_or_doc: Union[AnyStr, IO[AnyStr]]
    :param blacklist_keys: Any keys, which if in the yaml file, should cause
        and error.
    :type blacklisted_keys: Union[None, List[str]]
    :returns: the yaml file as a python document
    :rtype: Dict[str, str]
    :raises: yaml.YAMLError if there is a problem with the document
    :raises: BadPolicyYamlFile if file doesn't look right or there are
             blacklisted keys in the file.
    """
    blacklist_keys = blacklist_keys or []
    blacklist_keys.append(POLICYD_ALWAYS_BLACKLISTED_KEYS)
    doc = yaml.safe_load(stream_or_doc)
    if not isinstance(doc, dict):
        raise BadPolicyYamlFile("doesn't look like a policy file?")
    keys = set(doc.keys())
    blacklisted_keys_present = keys.intersection(blacklist_keys)
    if blacklisted_keys_present:
        raise BadPolicyYamlFile("blacklisted keys {} present."
                                .format(", ".join(blacklisted_keys_present)))
    if not all(isinstance(k, six.string_types) for k in keys):
        raise BadPolicyYamlFile("keys in yaml aren't all strings?")
    # check that the dictionary looks like a mapping of str to str
    if not all(isinstance(v, six.string_types) for v in doc.values()):
        raise BadPolicyYamlFile("values in yaml aren't all strings?")
    return doc


def policyd_dir_for(service):
    """Return the policy directory for the named service.

    :param service: str
    :returns: the policy.d override directory.
    :rtype: os.PathLike[str]
    """
    return os.path.join("/", "etc", service, "policy.d")


def clean_policyd_dir_for(service, keep_paths=None, user=None, group=None):
    """Clean out the policyd directory except for items that should be kept.

    The keep_paths, if used, should be set to the full path of the files that
    should be kept in the policyd directory for the service.  Note that the
    service name is passed in, and then the policyd_dir_for() function is used.
    This is so that a coding error doesn't result in a sudden deletion of the
    charm (say).

    :param service: the service name to use to construct the policy.d dir.
    :type service: str
    :param keep_paths: optional list of paths to not delete.
    :type keep_paths: Union[None, List[str]]
    :param user: The user to create/write files/directories as
    :type user: Union[None, str]
    :param group: the group to create/write files/directories as
    :type group: Union[None, str]
    """
    _user = service if user is None else user
    _group = service if group is None else group
    keep_paths = keep_paths or []
    path = policyd_dir_for(service)
    hookenv.log("Cleaning path: {}".format(path), level=hookenv.DEBUG)
    if not os.path.exists(path):
        ch_host.mkdir(path, owner=_user, group=_group, perms=0o775)
    _scanner = os.scandir if hasattr(os, 'scandir') else _fallback_scandir
    for direntry in _scanner(path):
        # see if the path should be kept.
        if direntry.path in keep_paths:
            continue
        # we remove any directories; it's ours and there shouldn't be any
        if direntry.is_dir():
            shutil.rmtree(direntry.path)
        else:
            os.remove(direntry.path)


def maybe_create_directory_for(path, user, group):
    """For the filename 'path', ensure that the directory for that path exists.

    Note that if the directory already exists then the permissions are NOT
    changed.

    :param path: the filename including the path to it.
    :type path: str
    :param user: the user to create the directory as
    :param group: the group to create the directory as
    """
    _dir, _ = os.path.split(path)
    if not os.path.exists(_dir):
        ch_host.mkdir(_dir, owner=user, group=group, perms=0o775)


@contextlib.contextmanager
def _fallback_scandir(path):
    """Fallback os.scandir implementation.

    provide a fallback implementation of os.scandir if this module ever gets
    used in a py2 or py34 charm. Uses os.listdir() to get the names in the path,
    and then mocks the is_dir() function using os.path.isdir() to check for
    directory.

    :param path: the path to list the directories for
    :type path: str
    :returns: Generator that provides _FBDirectory objects
    :rtype: ContextManager[_FBDirectory]
    """
    for f in os.listdir(path):
        yield _FBDirectory(f)


class _FBDirectory(object):
    """Mock a scandir Directory object with enough to use in
    clean_policyd_dir_for
    """

    def __init__(self, path):
        self.path = path

    def is_dir(self):
        return os.path.isdir(self.path)


def path_for_policy_file(service, name):
    """Return the full path for a policy.d file that will be written to the
    service's policy.d directory.

    It is constructed using policyd_dir_for(), the name and the ".yaml"
    extension.

    For horizon, for example, it's a bit more complicated.  The name param is
    actually "override_service_dir/a_name", where target_service needs to be
    one the allowed horizon override services.  This translation and check is
    done in the _yamlfiles() function.

    :param service: the service name
    :type service: str
    :param name: the name for the policy override
    :type name: str
    :returns: the full path name for the file
    :rtype: os.PathLike[str]
    """
    return os.path.join(policyd_dir_for(service), name + ".yaml")


def _policy_success_file():
    """Return the file name for a successful drop of policy.d overrides

    :returns: the path name for the file.
    :rtype: str
    """
    return os.path.join(hookenv.charm_dir(), POLICYD_SUCCESS_FILENAME)


def remove_policy_success_file():
    """Remove the file that indicates successful policyd override."""
    try:
        os.remove(_policy_success_file())
    except Exception:
        pass


def set_policy_success_file():
    """Set the file that indicates successful policyd override."""
    open(_policy_success_file(), "w").close()


def is_policy_success_file_set():
    """Returns True if the policy success file has been set.

    This indicates that policies are overridden and working properly.

    :returns: True if the policy file is set
    :rtype: bool
    """
    return os.path.isfile(_policy_success_file())


def policyd_status_message_prefix():
    """Return the prefix str for the status line.

    "PO:" indicating that the policy overrides are in place, or "PO (broken):"
    if the policy is supposed to be working but there is no success file.

    :returns: the prefix
    :rtype: str
    """
    if is_policy_success_file_set():
        return "PO:"
    return "PO (broken):"


def process_policy_resource_file(resource_file,
                                 service,
                                 blacklist_paths=None,
                                 blacklist_keys=None,
                                 template_function=None,
                                 preserve_topdir=False,
                                 preprocess_filename=None,
                                 user=None,
                                 group=None):
    """Process the resource file (which should contain at least one yaml file)
    and write those files to the service's policy.d directory.

    The optional template_function is a function that accepts a python
    string and has an opportunity to modify the document
    prior to it being read by the yaml.safe_load() function and written to
    disk. Note that this function does *not* say how the templating is done -
    this is up to the charm to implement its chosen method.

    The param blacklist_paths are paths (that are in the service's policy.d
    directory that should not be touched).

    The param blacklist_keys are keys that must not appear in the yaml file.
    If they do, then the whole policy.d file fails.

    The yaml file extracted from the resource_file (which is a zipped file) has
    its file path reconstructed.  This, also, must not match any path in the
    black list.

    The yaml filename can be modified in two ways.  If the `preserve_topdir`
    param is True, then files will be flattened to the top dir.  This allows
    for creating sets of files that can be grouped into a single level tree
    structure.

    Secondly, if the `preprocess_filename` param is not None and callable()
    then the name is passed to that function for preprocessing before being
    converted to the end location.  This is to allow munging of the filename
    prior to being tested for a blacklist path.

    If any error occurs, then the policy.d directory is cleared, the error is
    written to the log, and the status line will eventually show as failed.

    :param resource_file: The zipped file to open and extract yaml files form.
    :type resource_file: Union[AnyStr, os.PathLike[AnyStr]]
    :param service: the service name to construct the policy.d directory for.
    :type service: str
    :param blacklist_paths: optional list of paths to leave alone
    :type blacklist_paths: Union[None, List[str]]
    :param blacklist_keys: optional list of keys that mustn't appear in the
                           yaml file's
    :type blacklist_keys: Union[None, List[str]]
    :param template_function: Optional function that can modify the yaml
                              document.
    :type template_function: Union[None, Callable[[AnyStr], AnyStr]]
    :param preserve_topdir: Keep the toplevel subdir
    :type preserve_topdir: bool
    :param preprocess_filename: Optional function to use to process filenames
                                extracted from the resource file.
    :type preprocess_filename: Union[None, Callable[[AnyStr]. AnyStr]]
    :param user: The user to create/write files/directories as
    :type user: Union[None, str]
    :param group: the group to create/write files/directories as
    :type group: Union[None, str]
    :returns: True if the processing was successful, False if not.
    :rtype: boolean
    """
    hookenv.log("Running process_policy_resource_file", level=hookenv.DEBUG)
    blacklist_paths = blacklist_paths or []
    completed = False
    _preprocess = None
    if preprocess_filename is not None and callable(preprocess_filename):
        _preprocess = preprocess_filename
    _user = service if user is None else user
    _group = service if group is None else group
    try:
        with open_and_filter_yaml_files(
                resource_file, preserve_topdir) as (zfp, gen):
            # first clear out the policy.d directory and clear success
            remove_policy_success_file()
            clean_policyd_dir_for(service,
                                  blacklist_paths,
                                  user=_user,
                                  group=_group)
            for name, ext, filename, zipinfo in gen:
                # See if the name should be preprocessed.
                if _preprocess is not None:
                    name = _preprocess(name)
                # construct a name for the output file.
                yaml_filename = path_for_policy_file(service, name)
                if yaml_filename in blacklist_paths:
                    raise BadPolicyZipFile("policy.d name {} is blacklisted"
                                           .format(yaml_filename))
                with zfp.open(zipinfo) as fp:
                    doc = fp.read()
                    # if template_function is not None, then offer the document
                    # to the template function
                    if ext in POLICYD_TEMPLATE_EXTS:
                        if (template_function is None or not
                                callable(template_function)):
                            raise BadPolicyZipFile(
                                "Template {} but no template_function is "
                                "available".format(filename))
                        doc = template_function(doc)
                    yaml_doc = read_and_validate_yaml(doc, blacklist_keys)
                # we may have to create the directory
                maybe_create_directory_for(yaml_filename, _user, _group)
                ch_host.write_file(yaml_filename,
                                   yaml.dump(yaml_doc).encode('utf-8'),
                                   _user,
                                   _group)
        # Every thing worked, so we mark up a success.
        completed = True
    except (BadZipFile, BadPolicyZipFile, BadPolicyYamlFile) as e:
        hookenv.log("Processing {} failed: {}".format(resource_file, str(e)),
                    level=POLICYD_LOG_LEVEL_DEFAULT)
    except IOError as e:
        # technically this shouldn't happen; it would be a programming error as
        # the filename comes from Juju and thus, should exist.
        hookenv.log(
            "File {} failed with IOError.  This really shouldn't happen"
            " -- error: {}".format(resource_file, str(e)),
            level=POLICYD_LOG_LEVEL_DEFAULT)
    except Exception as e:
        import traceback
        hookenv.log("General Exception({}) during policyd processing"
                    .format(str(e)),
                    level=POLICYD_LOG_LEVEL_DEFAULT)
        hookenv.log(traceback.format_exc())
    finally:
        if not completed:
            hookenv.log("Processing {} failed: cleaning policy.d directory"
                        .format(resource_file),
                        level=POLICYD_LOG_LEVEL_DEFAULT)
            clean_policyd_dir_for(service,
                                  blacklist_paths,
                                  user=_user,
                                  group=_group)
        else:
            # touch the success filename
            hookenv.log("policy.d overrides installed.",
                        level=POLICYD_LOG_LEVEL_DEFAULT)
            set_policy_success_file()
        return completed
