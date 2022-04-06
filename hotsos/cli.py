#!/usr/bin/env python3
import click
import contextlib
import os
import sys
import subprocess
import threading
import yaml

from progress.spinner import Spinner

from hotsos.core.config import setup_config
from hotsos.core.log import setup_logging, log
from hotsos.core import output_filter
from hotsos.core.cli_helpers import CLIHelper
from hotsos.client import HotSOSClient, PLUGIN_CATALOG


def get_hotsos_root():
    return os.path.dirname(sys.argv[0])


def get_version():
    return os.environ.get('SNAP_REVISION', 'development')


def get_repo_info():
    repo_info = os.environ.get('REPO_INFO_PATH')
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
    defs = os.path.join(get_hotsos_root(), '../defs')
    if not os.path.isdir(defs):
        root = os.environ.get('SNAP', '/')
        defs = os.path.join(root, 'etc/hotsos/defs')

    if not os.path.exists(defs):
        raise Exception("defs path {} not found".format(defs))

    return defs


def spinner(msg, done):
    spinner = Spinner(msg)
    while not done.is_set():
        spinner.next()
        done.wait(timeout=0.1)
    spinner.finish()


@contextlib.contextmanager
def progress_spinner(show_spinner, spinner_msg):
    done = threading.Event()
    if not show_spinner:
        done.set()
    thread = threading.Thread(target=spinner, args=(spinner_msg, done))
    thread.start()
    try:
        yield thread
    finally:
        done.set()
        thread.join()

    # Need this to ensure any following output starts on a new line
    sys.stderr.write('\n')
    sys.stderr.flush()


def main():
    @click.command(name='hotsos')
    @click.option('--machine-readable', default=False, is_flag=True,
                  help=("Don't format output for humans."))
    @click.option('--list-plugins', default=False, is_flag=True,
                  help=('Show available plugins.'))
    @click.option('--max-parallel-tasks', default=8,
                  help=('The searchtools module will execute searches across '
                        'files in parallel. By default the number of cores '
                        'used is limited to a max of 8. You can '
                        'override that value with this option.'))
    @click.option('--max-logrotate-depth', default=7,
                  help=('Searching all available logrotate history for a '
                        'given log file can be costly so we cap the history '
                        'to this value. Only applies when --all-logs is '
                        'provided.'))
    @click.option('--agent-error-key-by-time', default=False, is_flag=True,
                  help=('When displaying agent error counts, they will be '
                        'grouped by date. This option will result in '
                        'grouping by date and time which may be more useful '
                        'for cross-referencing with other logs.'))
    @click.option('--full', default=False, is_flag=True,
                  help=('This is the default and tells hotsos to generate a '
                        'full summary. If you want to save both a short and '
                        'full summary you can specifiy this option '
                        'when doing --short.'))
    @click.option('--very-short', default=False, is_flag=True,
                  help=('Minimal version of --short where only issue types or '
                        'bug ids are displayed with count of each (issues '
                        'only).'))
    @click.option('--short', default=False, is_flag=True,
                  help=('Filters the full summary so that it only includes '
                        'plugin known-bugs and potential-issues sections.'))
    @click.option('--user-summary', default=False, is_flag=True,
                  help=('Provide an existing summary so that it can be '
                        'post-procesed e.g. --format json.'))
    @click.option('--html-escape', default=False, is_flag=True,
                  help=('Apply html escaping to the output so that it is safe '
                        'to display in html.'))
    @click.option('--format', default='yaml',
                  help=('Output format. Default is yaml.'))
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
    @click.option('--version', '-v', default=False, is_flag=True,
                  help=('Show the version.'))
    @set_plugin_options
    @click.argument('data_root', required=False, type=click.Path(exists=True))
    def cli(data_root, version, defs_path, all_logs, quiet, debug, save,
            format, html_escape, user_summary, short, very_short,
            full, agent_error_key_by_time, max_logrotate_depth,
            max_parallel_tasks, list_plugins, machine_readable, **kwargs):
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

        \b
        DATA_ROOT
            Path to an unpacked sosreport. If none provided, will run against
            local host.
        """  # noqa

        full_mode_explicit = full
        minimal_mode = None
        if short:
            minimal_mode = 'short'
        elif very_short:
            minimal_mode = 'very-short'

        repo_info = get_repo_info()
        if repo_info:
            setup_config(REPO_INFO=repo_info)

        _version = get_version()
        setup_config(HOTSOS_VERSION=_version)

        if version:
            print(_version)
            return

        if not user_summary:
            if not data_root or data_root == '/':
                data_root = '/'
            elif data_root[-1] != '/':
                # Ensure trailing slash
                data_root += '/'

        setup_config(USE_ALL_LOGS=all_logs, PLUGIN_YAML_DEFS=defs_path,
                     DATA_ROOT=data_root,
                     AGENT_ERROR_KEY_BY_TIME=agent_error_key_by_time,
                     MAX_LOGROTATE_DEPTH=max_logrotate_depth,
                     MAX_PARALLEL_TASKS=max_parallel_tasks,
                     MACHINE_READABLE=machine_readable)

        if debug and quiet:
            sys.stderr.write('ERROR: cannot use both --debug and --quiet\n')
            return

        if debug:
            setup_logging(debug)

        if list_plugins:
            sys.stdout.write('\n'.join(PLUGIN_CATALOG.keys()))
            sys.stdout.write('\n')
            return

        if data_root == '/':
            analysis_target = 'localhost'
        else:
            analysis_target = 'sosreport {}'.format(data_root)

        if quiet:
            show_spinner = False
            spinner_msg = ''
        else:
            show_spinner = not debug
            spinner_msg = 'INFO: analysing {} '.format(analysis_target)

        with progress_spinner(show_spinner, spinner_msg):
            if user_summary:
                log.debug("User summary provided in %s", data_root)
                with open(data_root) as fd:
                    summary = yaml.safe_load(fd)
            else:
                plugins = []
                for k, v in kwargs.items():
                    if v is True:
                        plugins.append(k)

                if plugins:
                    # always run these
                    plugins.append('hotsos')
                    if 'system' not in plugins:
                        plugins.append('system')

                summary = HotSOSClient().run(plugins)

        formatted = output_filter.apply_output_formatting(summary,
                                                          format, html_escape,
                                                          minimal_mode)
        if save:
            if user_summary:
                output_name = os.path.basename(data_root)
                output_name = output_name.rpartition('.')[0]
            else:
                if data_root != '/':
                    if data_root.endswith('/'):
                        data_root = data_root.rpartition('/')[0]

                    output_name = os.path.basename(data_root)
                else:
                    output_name = "hotsos-{}".format(CLIHelper().hostname())

            if minimal_mode:
                if formatted:
                    out = "{}.short.summary".format(output_name)
                    with open(out, 'w', encoding='utf-8') as fd:
                        fd.write(formatted)
                        fd.write('\n')

                    sys.stdout.write("INFO: short summary written to {}\n".
                                     format(out))
                if full_mode_explicit:
                    formatted = output_filter.apply_output_formatting(
                                                          summary, format,
                                                          html_escape)

            if not minimal_mode or full_mode_explicit:
                if formatted:
                    out = "{}.summary".format(output_name)
                    with open(out, 'w', encoding='utf-8') as fd:
                        fd.write(formatted)
                        fd.write('\n')

                    sys.stdout.write("INFO: full summary written to {}\n".
                                     format(out))

        else:
            if debug:
                sys.stderr.write('Results:\n')

            if formatted:
                sys.stdout.write("{}\n".format(formatted))

    cli(prog_name='hotsos')


if __name__ == '__main__':
    main()
