#!/usr/bin/env python3
import click
import contextlib
import os
import sys
import subprocess
import threading

from importlib import metadata, resources
from progress.spinner import Spinner

from hotsos.core.config import HotSOSConfig
from hotsos.core.log import setup_logging, log
from hotsos.core.host_helpers import CLIHelper
from hotsos.client import (
    HotSOSClient,
    OutputManager,
    PLUGIN_CATALOG,
)


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
    with resources.path('hotsos', '.repo-info') as repo_info:
        if repo_info and os.path.exists(repo_info):
            with open(repo_info) as fd:
                return fd.read().strip()

    try:
        out = subprocess.check_output(['git', '-C',  get_hotsos_root(),
                                       'rev-parse', '--short', 'HEAD'],
                                      stderr=subprocess.DEVNULL)
        if not out:
            return "unknown"
    except Exception:
        return "unknown"

    return out.decode().strip()


def set_plugin_options(f):
    for plugin in PLUGIN_CATALOG:
        click.option('--{}'.format(plugin), default=False, is_flag=True,
                     help=('Run the {} plugin.'.format(plugin)))(f)

    return f


def get_defs_path():
    # source
    defs = os.path.join(get_hotsos_root(), 'defs')
    if not os.path.isdir(defs):
        # pypi
        with resources.path('hotsos', 'defs') as path:
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
    spinner = Spinner(msg)
    while not done.is_set():
        spinner.next()
        done.wait(timeout=0.1)
    spinner.finish()


@contextlib.contextmanager
def progress_spinner(show_spinner, spinner_msg):
    if not show_spinner:
        yield
        return

    done = threading.Event()
    thread = threading.Thread(target=spinner, args=(spinner_msg, done))
    thread.start()
    try:
        yield thread
    finally:
        done.set()
        thread.join()


def fix_data_root(data_root):
    if not data_root:
        data_root = '/'
    elif data_root[-1] != '/':
        # Ensure trailing slash
        data_root += '/'
    return data_root


def get_analysis_target(data_root):
    if data_root == '/':
        analysis_target = 'localhost'
    else:
        analysis_target = 'sosreport {}'.format(data_root)
    return analysis_target


def get_prefix(data_root):
    if data_root != '/':
        if data_root.endswith('/'):
            data_root = data_root.rpartition('/')[0]

        return os.path.basename(data_root)

    return CLIHelper().hostname()


def main():
    @click.command(name='hotsos')
    @click.option('--command-timeout', default=HotSOSConfig.command_timeout,
                  help=('Amount of time command execution will wait before '
                        'timing out and moving on.'))
    @click.option('--allow-constraints-for-unverifiable-logs', default=False,
                  is_flag=True)
    @click.option('--output-path', default=None,
                  help=('Optional path to use for saving output (with '
                        '--save).'))
    @click.option('--machine-readable', default=False, is_flag=True,
                  help=("Don't format output for humans."))
    @click.option('--list-plugins', default=False, is_flag=True,
                  help=('Show available plugins.'))
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
    @click.option('--agent-error-key-by-time', default=False, is_flag=True,
                  help=('DEPRECATED: use --event-tally-granularity'))
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
    @click.option('--full', default=False, is_flag=True,
                  help=('[DEPRECATED] This is the default and tells hotsos to '
                        'generate a full summary. If you want to save both a '
                        'short and full summary you can specifiy this option '
                        'when doing --short.'))
    @click.option('--very-short', default=False, is_flag=True,
                  help=('Minimal version of --short where only issue types or '
                        'bug ids are displayed with count of each (issues '
                        'only).'))
    @click.option('--short', default=False, is_flag=True,
                  help=('Filters the full summary so that it only includes '
                        'plugin known-bugs and potential-issues sections.'))
    @click.option('--user-summary', default=None,
                  help=('[DEPRECATED] Provide an existing summary so that it '
                        'can be post-processed e.g. --format json. This '
                        'option is deprecated and no longer does anything'))
    @click.option('--html-escape', default=False, is_flag=True,
                  help=('Apply html escaping to the output so that it is safe '
                        'to display in html.'))
    @click.option('--format',
                  type=click.Choice(OutputManager.SUMMARY_FORMATS),
                  default='yaml',
                  show_default=True,
                  help=('Summary output format.'))
    @click.option('--save', '-s', default=False, is_flag=True,
                  help=('Save output to a file.'))
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
    @click.option('--defs-path', default=get_defs_path(),
                  help=('Path to yaml definitions (ydefs).'))
    @click.option('--templates-path', default=get_templates_path(),
                  help=('Path to Jinja templates.'))
    @click.option('--version', '-v', default=False, is_flag=True,
                  help=('Show the version.'))
    @set_plugin_options
    @click.argument('data_root', required=False, type=click.Path(exists=True))
    def cli(data_root, version, defs_path, templates_path, all_logs, quiet,
            debug, save, format, html_escape, short, very_short,
            force, full, agent_error_key_by_time, event_tally_granularity,
            max_logrotate_depth, max_parallel_tasks, list_plugins,
            machine_readable, output_path,
            allow_constraints_for_unverifiable_logs, command_timeout,
            **kwargs):
        """
        Run this tool on a host or against an unpacked sosreport to perform
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
            Path to an unpacked sosreport. If none provided, will run against
            local host.
        """  # noqa

        if full:
            # deprecated
            pass

        minimal_mode = None
        if short:
            minimal_mode = 'short'
        elif very_short:
            minimal_mode = 'very-short'

        HotSOSConfig.force_mode = force
        repo_info = get_repo_info()
        if repo_info:
            HotSOSConfig.repo_info = repo_info

        _version = get_version()
        HotSOSConfig.hotsos_version = _version
        HotSOSConfig.command_timeout = command_timeout

        if version:
            print(_version)
            return

        data_root = fix_data_root(data_root)
        if agent_error_key_by_time:
            print("WARNING: option --agent-error-key-by-time is DEPRECATED "
                  "and longer has any effect. Use --event-tally-granularity "
                  "instead.")

        HotSOSConfig.set(use_all_logs=all_logs, plugin_yaml_defs=defs_path,
                         templates_path=templates_path, data_root=data_root,
                         event_tally_granularity=event_tally_granularity,
                         max_logrotate_depth=max_logrotate_depth,
                         max_parallel_tasks=max_parallel_tasks,
                         machine_readable=machine_readable)
        HotSOSConfig.allow_constraints_for_unverifiable_logs = \
            allow_constraints_for_unverifiable_logs

        if debug and quiet:
            sys.stderr.write('ERROR: cannot use both --debug and --quiet\n')
            return

        HotSOSConfig.debug_mode = debug

        setup_logging()
        # Set a name so that logs have this until real plugins are run.
        log.name = 'hotsos.cli'

        if list_plugins:
            sys.stdout.write('\n'.join(PLUGIN_CATALOG.keys()))
            sys.stdout.write('\n')
            return

        analysis_target = get_analysis_target(data_root)

        if quiet:
            show_spinner = False
            spinner_msg = ''
        else:
            show_spinner = not debug
            spinner_msg = 'INFO: analysing {} '.format(analysis_target)

        with progress_spinner(show_spinner, spinner_msg):
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
            client.run()
            summary = client.summary

        if save:
            prefix = get_prefix(data_root)
            path = summary.save(prefix, html_escape=html_escape,
                                output_path=output_path)
            sys.stdout.write("INFO: output saved to {}\n".format(path))
        else:
            out = summary.get(format=format, html_escape=html_escape,
                              minimal_mode=minimal_mode)
            if out:
                sys.stdout.write("{}\n".format(out))

    cli(prog_name='hotsos')


if __name__ == '__main__':
    main()
