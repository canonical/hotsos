#!/usr/bin/env python3
import contextlib
import os
import subprocess
import sys
import threading
from importlib import metadata, resources

import click
import distro
from progress.spinner import Spinner
from hotsos.core import plugintools
from hotsos.core.root_manager import DataRootManager
from hotsos.core.config import HotSOSConfig
from hotsos.core.log import log, LoggingManager
from hotsos.client import (
    HotSOSClient,
    OutputManager,
)

SNAP_ERROR_MSG = """ERROR: hotsos is installed as a snap which only supports
running against a sosreport due to access restrictions.

If you want to analyse a host you need to use an alternative installation
method e.g. debian package - see https://hotsos.readthedocs.io/en/latest/install/index.html for more information."
""" # noqa


def is_snap():
    return os.environ.get('SNAP_NAME', '') == 'hotsos'


def get_os_id():
    return distro.id()


def get_os_version():
    return float(distro.version())


def get_hotsos_root():
    return os.path.dirname(sys.argv[0])


def get_version():
    ver = os.environ.get('SNAP_REVISION')
    if ver is None:
        try:
            ver = metadata.version('hotsos')
        except metadata.PackageNotFoundError:
            pass

    if ver is not None:
        return ver

    return 'development'


def get_repo_info():
    repo_info = os.environ.get('REPO_INFO_PATH')
    if repo_info and os.path.exists(repo_info):
        with open(repo_info) as fd:
            return fd.read().strip()

    # pypi
    # NOTE: The pylint warning is suppressed for W4902 because the
    # alternative (i.e. resources.files) is not available for python
    # 3.8, which is a supported environment for hotsos.
    # pylint: disable-next=W4902
    with resources.path('hotsos', '.repo-info') as repo_info:
        if repo_info and os.path.exists(repo_info):
            with open(repo_info) as fd:
                return fd.read().strip()

    try:
        out = subprocess.check_output(['git', '-C', get_hotsos_root(),
                                       'rev-parse', '--short', 'HEAD'],
                                      stderr=subprocess.DEVNULL)
        if not out:
            return "unknown"
    # We really do want to catch all here since we don't care why it failed
    # but don't want to fail hard if it does.
    except Exception:  # pylint: disable=W0718
        return "unknown"

    return out.decode().strip()


def set_plugin_options(f):
    for plugin in plugintools.PLUGINS:
        click.option('--{}'.format(plugin), default=False, is_flag=True,
                     help='Run the {} plugin.'.format(plugin))(f)

    return f


def get_defs_path():
    # source
    defs = os.path.join(get_hotsos_root(), 'defs')
    if not os.path.isdir(defs):
        # pypi
        with resources.path('hotsos', 'defs') as path:  # pylint: disable=W4902
            defs = path

    if not os.path.isdir(defs):
        # snap
        root = os.environ.get('SNAP', '/')
        defs = os.path.join(root, 'etc/hotsos/defs')

    if not os.path.exists(defs):
        raise Exception("defs path {} not found".format(defs))

    return defs


def get_templates_path():
    # source
    templates = os.path.join(get_hotsos_root(), 'templates')
    if not os.path.isdir(templates):
        # pypi
        # pylint: disable-next=W4902
        with resources.path('hotsos', 'templates') as path:
            templates = path

    if not os.path.isdir(templates):
        # snap
        root = os.environ.get('SNAP', '/')
        templates = os.path.join(root, 'etc/hotsos/templates')

    if not os.path.exists(templates):
        raise Exception("templates path {} not found".format(templates))

    return templates


def spinner(msg, done):
    cli_spinner = Spinner(msg)
    while not done.is_set():
        cli_spinner.next()
        done.wait(timeout=0.1)
    cli_spinner.finish()


@contextlib.contextmanager
def progress_spinner(show_spinner, path):
    if not show_spinner:
        yield
        return

    sys.stdout.write(
        'INFO: analysing {}\n'.format(path))
    spinner_msg = 'INFO: analysing '

    done = threading.Event()
    thread = threading.Thread(target=spinner, args=(spinner_msg, done))
    thread.start()
    try:
        yield thread
    finally:
        done.set()
        thread.join()


def main():  # pylint: disable=R0915
    @click.command(name='hotsos')
    @click.option('--event', default='',
                  help=('Filter a particular event name. Useful for '
                        'testing/debugging. Format is '
                        '<plugin name>.<group>.<event>'))
    @click.option('--scenario', default='',
                  help=('Filter a particular scenario name. Useful for '
                        'testing/debugging. Format is '
                        '<plugin name>.<group>.<scenario>'))
    @click.option('--sos-unpack-dir', default=None,
                  help=('Location used to unpack sosreports. Useful if you '
                        'want to cache the unpacked sosreport for subsequent '
                        'use. The provided path must exist.'))
    @click.option('--command-timeout', default=HotSOSConfig.command_timeout,
                  help=('Amount of time command execution will wait before '
                        'timing out and moving on.'))
    @click.option('--output-path', default=None,
                  help=('Optional path to use for saving output (with '
                        '--save).'))
    @click.option('--machine-readable', default=False, is_flag=True,
                  help="Don't format output for humans.")
    @click.option('--list-plugins', default=False, is_flag=True,
                  help='Show available plugins.')
    @click.option('--max-parallel-tasks', default=8,
                  help=('The search module will execute searches across '
                        'files in parallel. By default the number of cores '
                        'used is limited to a max of 8. You can '
                        'override that value with this option.'))
    @click.option('--max-logrotate-depth', default=7,
                  help=('Searching all available logrotate history for a '
                        'given log file can be costly so we cap the history '
                        'to this value. Only applies when --all-logs is '
                        'provided.'))
    @click.option('--event-tally-granularity', default='date',
                  help=('By default event tallies will be grouped by date, '
                        'for example when tallying occurrences of an event '
                        'in a file and displaying them in the summary. If '
                        'finer granularity is required this can be set to '
                        '"time".'))
    @click.option('--force', default=False, is_flag=True,
                  help=('By default plugins will only run if their '
                        'pre-requisites are met (i.e. they are "runnable").'
                        'It might sometimes be the case that not all '
                        'pre-requisites are available but we still want to '
                        'try running plugins. An example would be where an '
                        "application is not installed but we have it's logs. "
                        'Using this option can obviously produce '
                        'unexpected results so should be used with caution.'))
    @click.option('--very-short', default=False, is_flag=True,
                  help=('Minimal version of --short where only issue types or '
                        'bug ids are displayed with count of each (issues '
                        'only).'))
    @click.option('--short', default=False, is_flag=True,
                  help=('Filters the full summary so that it only includes '
                        'plugin known-bugs and potential-issues sections.'))
    @click.option('--html-escape', default=False, is_flag=True,
                  help=('Apply html escaping to the output so that it is safe '
                        'to display in html.'))
    @click.option('--format', '--output-format', 'output_format',
                  type=click.Choice(OutputManager.SUMMARY_FORMATS),
                  default='yaml',
                  show_default=True,
                  help='Summary output format.')
    @click.option('--save', '-s', default=False, is_flag=True,
                  help='Save output to a file.')
    @click.option('--quiet', default=False, is_flag=True,
                  help=('Suppress normal stderr output, only errors will be '
                        'printed.'))
    @click.option('--debug', default=False, is_flag=True,
                  help=('Provide some debug output. Logs will be printed to '
                        'stderr.'))
    @click.option('--all-logs', default=False, is_flag=True,
                  help=('Some plugins may choose to only analyse the most '
                        'recent version of a log file by default since '
                        'parsing the full history could take a lot '
                        'longer. This tells plugins that we wish to analyse '
                        'all available log history (see --max-logrotate-depth '
                        'for limits).'))
    @click.option('--templates-path', default=get_templates_path(),
                  help='Path to Jinja templates.')
    @click.option('--defs-path', default=get_defs_path(),
                  help='Path to yaml definitions (ydefs).')
    @click.option('--version', '-v', default=False, is_flag=True,
                  help='Show the version.')
    @set_plugin_options
    @click.argument('data_root', required=False, type=click.Path(exists=True))
    def cli(data_root, version, defs_path, templates_path, all_logs, debug,
            quiet, save, output_format, html_escape, short, very_short,
            force, event_tally_granularity, max_logrotate_depth,
            max_parallel_tasks, list_plugins, machine_readable, output_path,
            command_timeout, sos_unpack_dir, scenario, event, **kwargs):
        """
        Run this tool on a host or against a sosreport to perform
        analysis of specific applications and the host itself. A summary of
        information is generated along with any issues or known bugs detected.
        Applications are defined as plugins and support currently includes
        Openstack, Kubernetes, Ceph and more (see --list-plugins). The
        standard output format is yaml to allow easy visual inspection and
        post-processing by other tools. Other formats are also supported.

        There a three main components to this tool; the core python library,
        plugin extensions and a library of checks written in a high level
        yaml-based language.

        By default the output is printed to standard output. If saving to disk
        (--save) a directory called "hotsos-output" is created beneath which
        output is saved in all available formats e.g. yaml, json, short

        \b
        DATA_ROOT
            Path to an sosreport. If none provided, will run against local
            host.
        """  # noqa

        _version = get_version()
        if version:
            print(_version)
            return

        config = {'repo_info': get_repo_info(),
                  'force_mode': force,
                  'hotsos_version': _version,
                  'command_timeout': command_timeout,
                  'use_all_logs': all_logs,
                  'plugin_yaml_defs': defs_path,
                  'templates_path': templates_path,
                  'event_tally_granularity': event_tally_granularity,
                  'max_logrotate_depth': max_logrotate_depth,
                  'max_parallel_tasks': max_parallel_tasks,
                  'machine_readable': machine_readable,
                  'debug_mode': debug,
                  'scenario_filter': scenario,
                  'event_filter': event}
        HotSOSConfig.set(**config)

        with LoggingManager() as logmanager:
            with DataRootManager(data_root,
                                 sos_unpack_dir=sos_unpack_dir) as drm:
                HotSOSConfig.data_root = drm.data_root
                if is_snap() and drm.data_root == '/':
                    print(SNAP_ERROR_MSG)
                    sys.exit(1)

                if debug and quiet:
                    sys.stderr.write('ERROR: cannot use both --debug and '
                                     '--quiet\n')
                    return

                # Set a name so that logs have this until real plugins are run.
                log.name = 'hotsos.cli'

                if list_plugins:
                    sys.stdout.write('\n'.join(plugintools.PLUGINS.keys()))
                    sys.stdout.write('\n')
                    return

                with progress_spinner(not quiet and not debug, drm.name):
                    plugins = []
                    for k, v in kwargs.items():
                        if v is True:
                            plugins.append(k)

                    if plugins:
                        # always run these
                        plugins.append('hotsos')
                        if 'system' not in plugins:
                            plugins.append('system')

                    client = HotSOSClient(plugins)
                    try:
                        client.run()
                    except Exception as exc:
                        log.exception("An exception occurred while running "
                                      "plugins")
                        print('\nException running plugins:', exc)
                        print('See temp log file for possible details:',
                              logmanager.temp_log_path)
                        logmanager.delete_temp_file = False
                        raise

                    summary = client.summary

                if save:
                    path = summary.save(drm.basename, html_escape=html_escape,
                                        output_path=output_path)
                    sys.stdout.write("INFO: output saved to {}\n".format(path))
                else:
                    if short:
                        minimal_mode = 'short'
                    elif very_short:
                        minimal_mode = 'very-short'
                    else:
                        minimal_mode = None

                    out = summary.get(fmt=output_format,
                                      html_escape=html_escape,
                                      minimal_mode=minimal_mode)
                    if out:
                        sys.stdout.write("{}\n".format(out))

    cli(prog_name='hotsos')


def exit_if_os_version_not_supported_in_snap():
    if is_snap():
        if get_os_id() != 'ubuntu':
            print("This snap has only been verified to run on Ubuntu")
            sys.exit(1)
        if get_os_version() < 20.04:
            print("This snap has only been verified to run on Focal and above")
            sys.exit(2)


if __name__ == '__main__':
    exit_if_os_version_not_supported_in_snap()
    main()
